# -*- coding: utf-8 -*-
#
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2023
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

from cwtags import tag as T

from logilab.common.decorators import cachedproperty

from cubicweb import _
from cubicweb.view import StartupView

from cubicweb_francearchives.views import JinjaViewMixin, get_template, add_js_translations
from cubicweb_francearchives.views import FaqMixin


class SparqlYasguiView(FaqMixin, JinjaViewMixin, StartupView):
    __regid__ = "sparql-yasgui"
    template = get_template("sparql-yasgui.jinja2")
    title = _("SPARQL Editor")

    def add_js(self):
        self._cw.add_js("bundle-yasgui.js")
        self._cw.add_css("yasgui.css")

    @cachedproperty
    def breadcrumbs(self):
        return [
            (self._cw.build_url(""), self._cw._("Home")),
            (None, self._cw._("SPARQL Editor")),
        ]

    def call(self):
        self.add_js()
        add_js_translations(self._cw)
        sparql_endpoint = self._cw.vreg.config.get("sparql_endpoint")
        if not sparql_endpoint:
            with T.section(self.w, klass="document-view"):
                self.w(T.h1(self._cw._(self.title)))
                with T.div(self.w, self.w, klass="alert alert-danger"):
                    self.w(self._cw._("No sparql endpoint declared"))
        else:
            self._cw.html_headers.define_var("SPARQL_ENDPOINT", sparql_endpoint)
            self.call_template(**self.template_context())

    def template_context(self):
        return {
            "display_search_bar": True,
        }

    @cachedproperty
    def xiti_chapters(self):
        return ["sparql"]
