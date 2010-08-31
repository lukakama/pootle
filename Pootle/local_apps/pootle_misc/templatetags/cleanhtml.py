#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2008-2009 Zuza Software Foundation
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


from django import template
from django.template.defaultfilters import stringfilter
from django.utils.safestring import mark_safe

try:
    from lxml.html.clean import clean_html
except ImportError:
    clean_html = lambda text: text

def clean_wrapper(text):
    """wrapper around lxml's html cleaner that returns SafeStrings for
    immediate rendering in templates"""
    return mark_safe(clean_html(text))

register = template.Library()
register.filter('clean', stringfilter(clean_wrapper))
