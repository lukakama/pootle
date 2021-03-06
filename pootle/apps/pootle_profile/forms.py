#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2012 Zuza Software Foundation
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

from django import forms
from django.contrib import auth
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.utils.translation import ugettext as _

from pootle_profile.models import PootleProfile


def language_list():
    """Returns the list of localised language names, with 'default'."""
    tr_default = _("Default")

    if tr_default != "Default":
        tr_default = u"%s | \u202dDefault" % tr_default

    from pootle.i18n.override import lang_choices

    choices = lang_choices()
    choices.insert(0, ('', tr_default))

    return choices


class LangAuthenticationForm(AuthenticationForm):

    language = forms.ChoiceField(label=_('Interface Language'),
                                 choices=language_list(),
                                 initial="", required=False)


    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username and password:
            self.user_cache = auth.authenticate(username=username,
                                                password=password)

            if self.user_cache is None:
                raise forms.ValidationError(
                    _("Please enter a correct username and password. "
                      "Note that both fields are case-sensitive.")
                )
            elif not self.user_cache.is_active:
                raise forms.ValidationError(_("This account is inactive."))

        return self.cleaned_data


class UserForm(forms.ModelForm):

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email')


class PootleProfileForm(forms.ModelForm):

    class Meta:
        model = PootleProfile


    def __init__(self, *args, **kwargs):
        self.exclude_fields = kwargs.pop('exclude_fields', ())
        super(PootleProfileForm, self).__init__(*args, **kwargs)

        # Delete the fields the user can't edit
        for field in self.exclude_fields:
            del self.fields[field]
