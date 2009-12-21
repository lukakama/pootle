#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2009 Zuza Software Foundation
#
# This file is part of Pootle.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, see <http://www.gnu.org/licenses/>.

"""Fields required for handling translation files"""

import logging
import shutil
import tempfile

from django.conf import settings
from django.db import models
from django.db.models.fields.files import FieldFile, FileField

from translate.storage import factory
from translate.misc.lru import LRUCachingDict
from translate.misc.multistring import multistring

from pootle_store.signals import translation_file_updated
from pootle_store.translation_file import TranslationStoreFile, StatsTuple


################# String #############################

SEPERATOR = "__%$%__%$%__%$%__"

class MultiStringField(models.Field):
    description = "a field imitating translate.misc.multistring used for plurals"
    __metaclass__ = models.SubfieldBase
    
    def __init__(self, *args, **kwargs):
        super(MultiStringField, self).__init__(*args, **kwargs)

    def get_internal_type(self):
        return "TextField"

    def to_python(self, value):
        if isinstance(value, multistring):
            return value
        if value is None:
            return None
        elif isinstance(value, basestring):
            return multistring(value.split(SEPERATOR))
        else:
            return multistring(value)
            
    def get_db_prep_value(self, value):
        #FIXME: maybe we need to override get_db_prep_save instead?
        if value is not None:
            return SEPERATOR.join(value.strings)
        else:
            return None
            
    def get_db_prep_lookup(self, lookup_type, value):
        if lookup_type in ('exact', 'iexact'):
            return self.get_db_prep_value(value)
        else:
            return value
    

################# File ###############################


class StoreTuple(object):
    """Encapsulates toolkit stores in the in memory cache, needed
    since LRUCachingDict is based on a weakref.WeakValueDictionary
    which cannot reference normal tuples"""
    def __init__(self, store, mod_info):
        self.store = store
        self.mod_info = mod_info
            

class TranslationStoreFieldFile(FieldFile, TranslationStoreFile):
    """FieldFile is the File-like object of a FileField, that is found in a
    TranslationStoreField."""

    _store_cache = LRUCachingDict(settings.PARSE_POOL_SIZE, settings.PARSE_POOL_CULL_FREQUENCY)

    # redundant redefinition of path to be the same as defined in
    # FieldFile, added here for clarity since TranslationStoreFile
    # uses a different method
    path = property(FieldFile._get_path)

    def _get_store(self):
        """Get translation store from dictionary cache, populate if store not
        already cached."""
        #FIXME: when do we detect that file changed?
        if not hasattr(self, "_store_tuple"):
            self._update_store_cache()
        return self._store_tuple.store


    def _update_store_cache(self):
        """Add translation store to dictionary cache, replace old cached
        version if needed."""
        mod_info = self.getpomtime()
        if not hasattr(self, "_store_typle") or self._store_tuple.mod_info != mod_info:
            try:
                self._store_tuple = self._store_cache[self.path]
                if self._store_tuple.mod_info != mod_info:
                    # if file is modified act as if it doesn't exist in cache
                    raise KeyError
            except KeyError:
                logging.debug("cache miss for %s", self.path)
                self._store_tuple = StoreTuple(factory.getobject(self.path, ignore=self.field.ignore), mod_info)
                self._store_cache[self.path] = self._store_tuple
                self._stats[self.path] = StatsTuple()
                translation_file_updated.send(sender=self, path=self.path)


    def _touch_store_cache(self):
        """Update stored mod_info without reparsing file."""
        if hasattr(self, "_store_tuple"):
            mod_info = self.getpomtime()
            if self._store_tuple.mod_info != mod_info:
                self._store_tuple.mod_info = mod_info
                translation_file_updated.send(sender=self, path=self.path)
        else:
            #FIXME: do we really need that?
            self._update_store_cache()


    def _delete_store_cache(self):
        """Remove translation store from cache."""
        try:
            del self._store_cache[self.path]
        except KeyError:
            pass

        try:
            del self._store_tuple
        except AttributeError:
            pass

        try:
            del self._stats[self.path]
        except KeyError:
            pass
        translation_file_updated.send(sender=self, path=self.path)
        
    store = property(_get_store)


    def savestore(self):
        """Saves to temporary file then moves over original file. This
        way we avoid the need for locking."""
        tmpfile, tmpfilename = tempfile.mkstemp(suffix=self.filename)
        #FIXME: what if the file was modified before we save
        self.store.savefile(tmpfilename)
        shutil.move(tmpfilename, self.path)
        self._touch_store_cache()

    def save(self, name, content, save=True):
        #FIXME: implement save to tmp file then move instead of directly saving
        super(TranslationStoreFieldFile, self).save(name, content, save)
        self._delete_store_cache()

    def delete(self, save=True):
        self._delete_store_cache()
        if save:
            super(TranslationStoreFieldFile, self).delete(save)


class TranslationStoreField(FileField):
    """This is the field class to represent a FileField in a model that
    represents a translation store."""

    attr_class = TranslationStoreFieldFile

    #def formfield(self, **kwargs):
    #    defaults = {'form_class': FileField}
    #    defaults.update(kwargs)
    #    return super(TranslationStoreField, self).formfield(**defaults)

    def __init__(self, ignore=None, **kwargs):
        """ignore: postfix to be stripped from filename when trying to
        determine file format for parsing, useful for .pending files"""
        self.ignore = ignore
        super(TranslationStoreField, self).__init__(**kwargs)