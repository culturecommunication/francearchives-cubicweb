# -*- coding: utf-8 -*-
#
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2019
# Contact http://www.logilab.fr -- mailto:contact@logilab.fr
#
# This software is governed by the CeCILL-C license under French law and
# abiding by the rules of distribution of free software. You can use,
# modify and/ or redistribute the software under the terms of the CeCILL-C
# license as circulated by CEA, CNRS and INRIA at the following URL
# "http://www.cecill.info".
#
# As a counterpart to the access to the source code and rights to copy,
# modify and redistribute granted by the license, users are provided only
# with a limited warranty and the software's author, the holder of the
# economic rights, and the successive licensors have only limited liability.
#
# In this respect, the user's attention is drawn to the risks associated
# with loading, using, modifying and/or developing or reproducing the
# software by the user in light of its specific status of free software,
# that may mean that it is complicated to manipulate, and that also
# therefore means that it is reserved for developers and experienced
# professionals having in-depth computer knowledge. Users are therefore
# encouraged to load and test the software's suitability as regards their
# requirements in conditions enabling the security of their systemsand/or
# data to be ensured and, more generally, to use and operate it in the
# same conditions as regards security.
#
# The fact that you are presently reading this means that you have had
# knowledge of the CeCILL-C license and that you accept its terms.
#
import datetime

from StringIO import StringIO

from pyramid.renderers import JSON
from cubicweb.uilib import UnicodeCSVWriter


class CSVRenderer(object):
    def __init__(self, csv_options=None, encoding=None, **kw):
        self.kw = kw
        self.encoding = encoding
        if csv_options:
            self.csv_options = csv_options
        else:
            self.csv_options = {'delimiter': ',',
                                'quotechar': '"',
                                'lineterminator': '\n'}

    def __call__(self, info):
        def _render(value, system):
            """CSV-encoded string with content-type ``text/csv``."""
            request = system.get('request')
            if request is not None:
                if self.encoding is None:
                    self.encoding = request.cw_request.encoding
                response = request.response
                ct = response.content_type
                if ct == response.default_content_type:
                    response.content_type = 'text/comma-separated-values;charset=%s' % self.encoding
            stream = StringIO()
            writer = UnicodeCSVWriter(stream.write,
                                      encoding=self.encoding,
                                      **self.csv_options)
            headers = value.get('headers')
            if headers:
                writer.writerow(headers)
            writer.writerows(value.get('rows', []))
            return stream.getvalue()

        return _render


class PrettyJSON(JSON):

    def __call__(self, info):
        """ Returns a pretty JSON-encoded string if ``pretty``
        is present in ``request.params``"""
        def _render(value, system):
            request = system.get('request')
            if request is not None:
                response = request.response
                ct = response.content_type
                if ct == response.default_content_type:
                    response.content_type = 'application/json'
                if 'pretty' in request.params:
                    self.kw['indent'] = 2
            default = self._make_default(request)
            result = self.serializer(value, default=default, **self.kw)
            self.kw.pop('indent', None)
            return result
        return _render


def includeme(config):
    json_renderer = PrettyJSON()
    csv_renderer = CSVRenderer()

    def datetime_isoformat(obj, request):
        return obj.replace(microsecond=0).isoformat()

    def date_isoformat(obj, request):
        return obj.isoformat()

    csv_renderer = CSVRenderer()
    json_renderer.add_adapter(datetime.datetime, datetime_isoformat)
    json_renderer.add_adapter(datetime.date, date_isoformat)
    config.add_renderer('json', json_renderer)
    config.add_renderer('csv', csv_renderer)
