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

"""pnia_content views/homepage views and components"""

from logilab.common.decorators import cachedproperty

from cubicweb.web.component import CtxComponent
from cubicweb.web.views.startup import IndexView

from cubicweb_francearchives.views import JinjaViewMixin, format_number, get_template
from cubicweb_francearchives.utils import (
    get_hp_articles,
    number_of_archives,
    number_of_qualified_authorities,
)


class HomePageAbstractComponent(CtxComponent):
    __abstract__ = True
    context = "homepage"


class OnHomePageComponent(JinjaViewMixin, HomePageAbstractComponent):
    __regid__ = "onhomepage"
    template = get_template("onhomepage.jinja2")
    order = 1

    def call_template(self, w, **ctx):
        w(self.template.render(**ctx))

    def render(self, w):
        req = self._cw
        return self.call_template(
            w,
            _=req._,
            entities=get_hp_articles(req, "onhp_hp"),
            default_picto_src=self._cw.uiprops["DOCUMENT_IMG"],
        )


class HomePageBottomLinks(JinjaViewMixin, HomePageAbstractComponent):
    __regid__ = "homepage-bottom-links"
    template = get_template("bottom-links.jinja2")
    order = 2

    def call_template(self, w, **ctx):
        w(self.template.render(**ctx))

    def render(self, w):
        req = self._cw
        archives = format_number(number_of_archives(req), req)
        agents = format_number(number_of_qualified_authorities(req, "AgentAuthority"), req)
        subjects = format_number(number_of_qualified_authorities(req, "SubjectAuthority"), req)
        locations = format_number(number_of_qualified_authorities(req, "LocationAuthority"), req)
        return self.call_template(
            w,
            req=req,
            homepage=True,
            archives_label=req._("See {} archives").format(archives),
            subjects_label=req._("{} Subjects").format(subjects),
            agents_label=req._("{} Agents").format(agents),
            locations_label=req._("{} Locations").format(locations),
        )


class PniaIndexView(IndexView):
    needs_css = ()

    @cachedproperty
    def xiti_chapters(self):
        return ["Home"]

    def template_context(self):
        req = self._cw
        meta = req.vreg["adapters"].select("IMeta", req, homepage=True)
        og = req.vreg["adapters"].select("IOpenGraph", req, homepage=True)
        return {"open_graph": og.og_data(), "meta": meta.meta_data()}

    def call(self):
        self._cw.add_css(self.needs_css)
        comps = self._cw.vreg["ctxcomponents"].poss_visible_objects(
            self._cw, context="homepage", rset=self.cw_rset
        )
        for comp in comps:
            comp.render(w=self.w)


def registration_callback(vreg):
    vreg.unregister(IndexView)
    vreg.register_all(list(globals().values()), __name__)
