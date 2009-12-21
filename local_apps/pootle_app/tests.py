import tempfile
import shutil
import urlparse
import os
import zipfile

from translate.misc import wStringIO

from django.conf import settings
from django.test import TestCase
from django.http import QueryDict
from django.core.management import call_command
from django.contrib.auth.models import User
from pootle_app.models.translation_project import scan_translation_projects
from pootle_store.models import fs
from pootle_app.models import Project, Language
from pootle_store.models import Store

def formset_dict(data):
    """convert human readable POST dictionary into brain dead django formset dictionary"""
    new_data = {'form-TOTAL_FORMS': len(data), 'form-INITIAL_FORMS': 0}
    for i in range(len(data)):
        for key, value in data[i].iteritems():
            new_data["form-%d-%s" % (i, key)] = value
    return new_data

class PootleTestCase(TestCase):
    """Base TestCase class, set's up a pootle environment with a
    couple of test files and projects"""


    def _setup_test_podir(self):
        self.testpodir = tempfile.mkdtemp()
        settings.PODIRECTORY = self.testpodir
        fs.location = self.testpodir
        
        gnu = os.path.join(self.testpodir, "terminology")
        os.mkdir(gnu)
        potfile = file(os.path.join(gnu, "terminology.pot"), 'w')
        potfile.write('#: test.c\nmsgid "test"\nmsgstr ""\n')
        potfile.close()
        pofile = file(os.path.join(gnu, "ar.po"), 'w')
        pofile.write('#: test.c\nmsgid "test"\nmsgstr "rest"\n')
        pofile.close()

        nongnu = os.path.join(self.testpodir, "pootle")
        os.mkdir(nongnu)
        nongnu_ar = os.path.join(nongnu, "ar")
        os.mkdir(nongnu_ar)
        nongnu_ja = os.path.join(nongnu, "ja")
        os.mkdir(nongnu_ja)
        nongnu_af = os.path.join(nongnu, "af")
        os.mkdir(nongnu_af)
        pofile = file(os.path.join(nongnu_af, "pootle.po"), 'w')
        pofile.write('''#: fish.c
msgid "fish"
msgstr ""

#: test.c
msgid "test"
msgstr "rest"

''')
        pofile.close()


    def _setup_test_users(self):
        nonpriv = User(username=u"nonpriv",
                       first_name="Non privileged test user",
                       is_active=True)
        nonpriv.set_password("nonpriv")
        nonpriv.save()

    def _teardown_test_podir(self):
        shutil.rmtree(self.testpodir)

    def setUp(self):
        self._setup_test_podir()

        #FIXME: replace initdb with a fixture
        call_command('initdb')
        
        self._setup_test_users()
        scan_translation_projects()

    def tearDown(self):
        self._teardown_test_podir()


    def follow_redirect(self, response):
        """follow a redirect chain until a non redirect response is recieved"""
        new_response = response
        while new_response.status_code in (301, 302, 303, 307):
            scheme, netloc, path, query, fragment = urlparse.urlsplit(new_response['location'])
            new_response = self.client.get(path, QueryDict(query))
        return new_response
    
class AnonTests(PootleTestCase):
    def test_login(self):
        """Checks that login works and sets cookies"""
        response = self.client.get('/')
        self.assertContains(response, "Log In")

        response = self.client.post('/accounts/login/', {'username':'admin', 'password':'admin'})
        self.assertRedirects(response, '/accounts/admin/')

    def test_admin_not_logged(self):
        """checks that admin pages are not accessible without login"""
        response = self.client.get("/admin/")
        self.assertContains(response, '', status_code=403)

        
class AdminTests(PootleTestCase):
    def setUp(self):
        super(AdminTests, self).setUp()
        self.client.login(username='admin', password='admin')

    def test_logout(self):
        """tests login and logout links"""
        response = self.client.get('/')
        self.assertContains(response, "Log Out")

        response = self.client.get("/accounts/logout/")
        self.assertRedirects(response, '/')

        response = self.client.get('/')
        self.assertContains(response, "Log In")

    def test_admin_rights(self):
        """checks that admin user can access admin pages"""
        response = self.client.get('/')
        self.assertContains(response, "<a href='/admin/'>Admin</a>")
        response = self.client.get('/admin/')
        self.assertContains(response, 'General Settings')        

    def test_add_project(self):
        """Checks that we can add a project successfully."""
    
        response = self.client.get("/admin/projects.html")
        self.assertContains(response, "<a href='/projects/pootle/admin.html'>pootle</a>")
        self.assertContains(response, "<a href='/projects/terminology/admin.html'>terminology</a>")

        add_dict = {
            "code": "testproject",                                       
            "localfiletype": "xlf",                                     
            "fullname": "Test Project",                                
            "checkstyle": "standard",
            "treestyle": "gnu",
            }
    
        response = self.client.post("/admin/projects.html", formset_dict([add_dict]))
        self.assertContains(response, "<a href='/projects/testproject/admin.html'>testproject</a>")
    
        # check for the actual model
        testproject = Project.objects.get(code="testproject")
        
        self.assertTrue(testproject)
        self.assertEqual(testproject.fullname, add_dict['fullname'])
        self.assertEqual(testproject.checkstyle, add_dict['checkstyle'])
        self.assertEqual(testproject.localfiletype, add_dict['localfiletype'])
        self.assertEqual(testproject.treestyle, add_dict['treestyle'])

    def test_add_project_language(self):
        """Tests that we can add a language to a project, then access
        its page when there are no files."""
        fish = Language(code="fish", fullname="fish")
        fish.save()
            
        response = self.client.get("/projects/pootle/admin.html")
        self.assertContains(response, "fish")

        project = Project.objects.get(code='pootle')
        add_dict = {
            "language": fish.id,
            "project": project.id,
            }
        response = self.client.post("/projects/pootle/admin.html", formset_dict([add_dict]))
        self.assertContains(response, '/fish/pootle/')
        
        response = self.client.get("/fish/")
        self.assertContains(response, '<a href="/fish/">fish</a>')
        self.assertContains(response, '<a href="/fish/pootle/">Pootle</a>')
        self.assertContains(response, "1 project, 0% translated")

    def test_upload_new_file(self):
        """Tests that we can upload a new file into a project."""
        pocontent = wStringIO.StringIO('#: test.c\nmsgid "test"\nmsgstr "rest"\n')
        pocontent.name = "test_new_upload.po"
    
        post_dict = {
            'file': pocontent,
            'overwrite': 'merge',
            'do_upload': 'upload',
            }
        response = self.client.post("/ar/pootle/", post_dict)
        
        self.assertContains(response, 'href="/ar/pootle/test_new_upload.po')
        store = Store.objects.get(pootle_path="/ar/pootle/test_new_upload.po")
        self.assertTrue(os.path.isfile(store.file.path))
        self.assertEqual(store.file.read(), pocontent.getvalue())
    
        download = self.client.get("/ar/pootle/test_new_upload.po/export/po")
        self.assertEqual(download.content, pocontent.getvalue())

    def test_upload_suggestions(self):
        """Tests that we can upload when we only have suggest rights."""
        pocontent = wStringIO.StringIO('#: test.c\nmsgid "test"\nmsgstr "samaka"\n')
        pocontent.name = "pootle.po"
    
        post_dict = {
            'file': pocontent,
            'overwrite': 'merge',
            'do_upload': 'upload',
            }
        response = self.client.post("/af/pootle/", post_dict)

        # Check that the orignal file didn't take the new suggestion.
        # We test with 'in' since the header is added
        store = Store.objects.get(pootle_path="/af/pootle/pootle.po")
        self.assertFalse('msgstr "samaka"' in store.file.read())
        self.assertTrue('msgstr "samaka"' in store.pending.read())

    def test_upload_overwrite(self):
        """Tests that we can overwrite a file in a project."""    
        pocontent = wStringIO.StringIO('#: test.c\nmsgid "fish"\nmsgstr ""\n#: test.c\nmsgid "test"\nmsgstr "barf"\n\n')
        pocontent.name = "pootle.po"
    
        post_dict = {
            'file': pocontent,
            'overwrite': 'overwrite',
            'do_upload': 'upload',
            }
        response = self.client.post("/af/pootle/", post_dict)

        # Now we only test with 'in' since the header is added
        store = Store.objects.get(pootle_path="/af/pootle/pootle.po")
        self.assertEqual(store.file.read(), pocontent.getvalue())

    def test_upload_new_archive(self):
        """Tests that we can upload a new archive of files into a project."""
        po_content_1 = '#: test.c\nmsgid "test"\nmsgstr "rest"\n'
        po_content_2 = '#: frog.c\nmsgid "tadpole"\nmsgstr "fish"\n'

        archivefile = wStringIO.StringIO()
        archivefile.name = "fish.zip"
        archive = zipfile.ZipFile(archivefile, "w", zipfile.ZIP_DEFLATED)
        archive.writestr("test_archive_1.po", po_content_1)
        archive.writestr("test_archive_2.po", po_content_2)
        archive.close()

        archivefile.seek(0)
        post_dict = {
            'file': archivefile,
            'overwrite': 'merge',
            'do_upload': 'upload',
            }
        response = self.client.post("/ar/pootle/", post_dict)

        self.assertContains(response, 'href="/ar/pootle/test_archive_1.po')
        self.assertContains(response, 'href="/ar/pootle/test_archive_2.po')

        store = Store.objects.get(pootle_path="/ar/pootle/test_archive_1.po")
        self.assertTrue(os.path.isfile(store.file.path))
        self.assertEqual(store.file.read(), po_content_1)

        download = self.client.get("/ar/pootle/test_archive_2.po/export/po")
        self.assertEqual(po_content_2, download.content)


    def test_upload_over_file(self):
        """Tests that we can upload a new version of a file into a project."""
        pocontent = wStringIO.StringIO('''#: fish.c
msgid "fish"
msgstr ""
        
#: test.c
msgid "test"
msgstr "resto"

''')
        pocontent.name = "pootle.po"
        post_dict = {
            'file': pocontent,
            'overwrite': 'overwrite',
            'do_upload': 'upload',
            }
        response = self.client.post("/af/pootle/", post_dict)
    
        pocontent = wStringIO.StringIO('#: test.c\nmsgid "test"\nmsgstr "blo3"\n\n#: fish.c\nmsgid "fish"\nmsgstr "stink"\n')
        pocontent.name = "pootle.po"

        post_dict = {
            'file': pocontent,
            'overwrite': 'merge',
            'do_upload': 'upload',
            }
        response = self.client.post("/af/pootle/", post_dict)

        # NOTE: this is what we do currently: any altered strings become suggestions.
        # It may be a good idea to change this
        mergedcontent = '#: fish.c\nmsgid "fish"\nmsgstr "stink"\n'
        suggestedcontent = '#: test.c\nmsgid ""\n"_: suggested by admin [1963585124]\\n"\n"test"\nmsgstr "blo3"\n'
        store = Store.objects.get(pootle_path="/af/pootle/pootle.po")
        self.assertTrue(store.file.read().find(mergedcontent) >= 0)
        self.assertTrue(os.path.isfile(store.pending.path))
        self.assertTrue(store.pending.read().find(suggestedcontent) >= 0)


    def test_upload_new_xliff_file(self):
        """Tests that we can upload a new XLIFF file into a project."""
        xliffcontent = wStringIO.StringIO('''<?xml version='1.0' encoding='utf-8'?>
        <xliff xmlns="urn:oasis:names:tc:xliff:document:1.1" version="1.1">
        <file original="" source-language="en-US" datatype="po">
        <body>
          <trans-unit id="1" xml:space="preserve">
            <source>test</source>
            <target state="needs-review-translation">rest</target>
            <context-group name="po-reference" purpose="location">
              <context context-type="sourcefile">test.c</context>
            </context-group>
          </trans-unit>
        </body>
        </file>
        </xliff>
''')
        xliffcontent.name = 'test_new_xliff_upload.xlf'

        post_dict = {
            'file': xliffcontent,
            'overwrite': 'overwrite',
            'do_upload': 'upload',
            }
        
        response = self.client.post("/ar/pootle/", post_dict)
        self.assertContains(response,' href="/ar/pootle/test_new_xliff_upload.po')

        #FIXME: test conversion?

    def test_upload_xliff_over_file(self):
        """Tests that we can upload a new version of a XLIFF file into a project."""
        pocontent = wStringIO.StringIO('#: test.c\nmsgid "test"\nmsgstr "rest"\n\n#: frog.c\nmsgid "tadpole"\nmsgstr "fish"\n')
        pocontent.name = "test_upload_xliff.po"
        post_dict = {
            'file': pocontent,
            'overwrite': 'overwrite',
            'do_upload': 'upload',
            }
        response = self.client.post("/ar/pootle/", post_dict)

        xlfcontent = wStringIO.StringIO('''<?xml version="1.0" encoding="utf-8"?>
        <xliff version="1.1" xmlns="urn:oasis:names:tc:xliff:document:1.1">
        <file datatype="po" original="test_existing.po" source-language="en-US">
        <body>
            <trans-unit id="test" xml:space="preserve" approved="yes">
                <source>test</source>
                <target state="translated">rested</target>
                <context-group name="po-reference" purpose="location">
                    <context context-type="sourcefile">test.c</context>
                </context-group>
            </trans-unit>
            <trans-unit id="slink" xml:space="preserve" approved="yes">
                <source>slink</source>
                <target state="translated">stink</target>
                <context-group name="po-reference" purpose="location">
                    <context context-type="sourcefile">toad.c</context>
                </context-group>
            </trans-unit>
        </body>
        </file>
        </xliff>''')
        xlfcontent.name = "test_upload_xliff.xlf"
    
        post_dict = {
            'file': xlfcontent,
            'overwrite': 'merge',
            'do_upload': 'upload',
            }
        response = self.client.post("/ar/pootle/", post_dict)

        # NOTE: this is what we do currently: any altered strings become suggestions.
        # It may be a good idea to change this
        mergedcontent = '#: test.c\nmsgid "test"\nmsgstr "rest"\n\n#~ msgid "tadpole"\n#~ msgstr "fish"\n\n#: toad.c\nmsgid "slink"\nmsgstr "stink"\n'
        suggestedcontent = '#: test.c\nmsgid ""\n"_: suggested by admin [595179475]\\n"\n"test"\nmsgstr "rested"\n'
        store = Store.objects.get(pootle_path="/ar/pootle/test_upload_xliff.po")
        
        self.assertTrue(os.path.isfile(store.file.path))
        self.assertTrue(store.file.read().find(mergedcontent) >= 0)

        self.assertTrue(os.path.isfile(store.pending.path))
        self.assertTrue(store.pending.read().find(suggestedcontent) >= 0)
        

    def test_submit_translation(self):
        """Tests that we can translate units."""

        submit_dict = {
            'trans0': 'submitted translation',
            'submit0': 'Submit',
            'store': '/af/pootle/pootle.po',
            }
        submit_dict.update(formset_dict([]))
        response = self.client.post("/af/pootle/pootle.po", submit_dict,
                                    QUERY_STRING='view_mode=translate')
    
        self.assertContains(response, 'submitted translation')

        store = Store.objects.get(pootle_path="/af/pootle/pootle.po")
        self.assertTrue(store.file.read().find('submitted translation') >= 0)

    def test_submit_plural_translation(self):
        """Tests that we can submit a translation with plurals."""
        pocontent = wStringIO.StringIO('msgid "singular"\nmsgid_plural "plural"\nmsgstr[0] ""\nmsgstr[1] ""\n')
        pocontent.name = 'test_plural_submit.po'

        post_dict = {
            'file': pocontent,
            'overwrite': 'overwrite',
            'do_upload': 'upload',
            }
        response = self.client.post("/ar/pootle/", post_dict)

        submit_dict = {
            'trans0-0': 'a fish',
            'trans0-1': 'some fish',
            'trans0-2': 'lots of fish',
            'submit0': 'Submit',
            'store': '/ar/pootle/test_plural_submit.po',
            }
        submit_dict.update(formset_dict([]))
        response = self.client.post("/ar/pootle/test_plural_submit.po", submit_dict,
                                    QUERY_STRING='view_mode=translate')

        self.assertContains(response, 'a fish')
        self.assertContains(response, 'some fish')
        self.assertContains(response, 'lots of fish')
        
    def test_submit_plural_to_singular_lang(self):
        """Tests that we can submit a translation with plurals to a language without plurals."""
        
        pocontent = wStringIO.StringIO('msgid "singular"\nmsgid_plural "plural"\nmsgstr[0] ""\nmsgstr[1] ""\n')
        pocontent.name = 'test_plural_submit.po'

        post_dict = {
            'file': pocontent,
            'overwrite': 'overwrite',
            'do_upload': 'upload',
            }
        response = self.client.post("/ja/pootle/", post_dict)

        submit_dict = {
            'trans0': 'just fish',
            'submit0': 'Submit',
            'store': '/ja/pootle/test_plural_submit.po',
            }
        submit_dict.update(formset_dict([]))
        response = self.client.post("/ja/pootle/test_plural_submit.po", submit_dict,
                                    QUERY_STRING='view_mode=translate')

        self.assertContains(response, 'just fish')

        expectedcontent = 'msgid "singular"\nmsgid_plural "plural"\nmsgstr[0] "just fish"\n'
        store = Store.objects.get(pootle_path="/ja/pootle/test_plural_submit.po")
        self.assertTrue(store.file.read().find(expectedcontent) >= 0)


    def test_submit_fuzzy(self):
        """Tests that we can mark a unit as fuzzy."""

        # Fetch the page and check that the fuzzy checkbox is NOT checked.
    
        response = self.client.get("/af/pootle/pootle.po", {'view_mode': 'translate'})
        self.assertContains(response, '<input type="checkbox"  name="fuzzy0" accesskey="f" id="fuzzy0" class="fuzzycheck" />')
    
        submit_dict = {
            'trans0': 'fuzzy translation',
            'fuzzy0': 'on',
            'submit0': 'Submit',
            'store': '/af/pootle/pootle.po',
            }
        submit_dict.update(formset_dict([]))
        response = self.client.post("/af/pootle/pootle.po", submit_dict,
                                    QUERY_STRING='view_mode=translate')
        # Fetch the page again and check that the fuzzy checkbox IS checked.
        response = self.client.get("/af/pootle/pootle.po", {'view_mode': 'translate'})
        self.assertContains(response, '<input type="checkbox" checked="checked" name="fuzzy0" accesskey="f" id="fuzzy0" class="fuzzycheck" />')

        store = Store.objects.get(pootle_path="/af/pootle/pootle.po")
        self.assertTrue(store.getitem(0).isfuzzy())

        # Submit the translation again, without the fuzzy checkbox checked
        submit_dict = {
            'trans0': 'fuzzy translation',
            'fuzzy0': '',
            'submit0': 'Submit',
            'store': '/af/pootle/pootle.po',
            }
        submit_dict.update(formset_dict([]))
        response = self.client.post("/af/pootle/pootle.po", submit_dict,
                                    QUERY_STRING='view_mode=translate')
        # Fetch the page once more and check that the fuzzy checkbox is NOT checked.
        response = self.client.get("/af/pootle/pootle.po", {'view_mode': 'translate'})
        self.assertContains(response, '<input type="checkbox"  name="fuzzy0" accesskey="f" id="fuzzy0" class="fuzzycheck" />')
        self.assertFalse(store.getitem(0).isfuzzy())
        
    def test_submit_translator_comments(self):
        """Tests that we can edit translator comments."""

        submit_dict = {
            'trans0': 'fish',
            'translator_comments0': 'goodbye\nand thanks for all the fish',
            'submit0': 'Submit',
            'store': '/af/pootle/pootle.po',
            }
        submit_dict.update(formset_dict([]))
        response = self.client.post("/af/pootle/pootle.po", submit_dict,
                                    QUERY_STRING='view_mode=translate')

        store = Store.objects.get(pootle_path='/af/pootle/pootle.po')
        self.assertEqual(store.getitem(0).getnotes(), 'goodbye\nand thanks for all the fish')


class NonprivTests(PootleTestCase):
    def setUp(self):
        super(NonprivTests, self).setUp()
        self.client.login(username='nonpriv', password='nonpriv')
        
    def test_non_admin_rights(self):
        """checks that non privileged users cannot access admin pages"""
        response = self.client.get('/admin/')
        self.assertContains(response, '', status_code=403)
        
        
