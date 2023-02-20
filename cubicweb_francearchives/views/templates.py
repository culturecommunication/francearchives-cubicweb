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

"""pnia_content views/templates"""

from collections import defaultdict
from random import randint

from logilab.common.decorators import monkeypatch, cachedproperty
from logilab.mtconverter import xml_escape

from cubicweb.utils import HTMLStream, json_dumps, HTMLHead
from cubicweb.web.views import basetemplates

from cubicweb_francearchives import FEATURE_ADVANCED_SEARCH
from cubicweb_francearchives.utils import find_card, build_faq_url, reveal_glossary
from cubicweb_francearchives.entities import entity2schemaorg, entity2meta, entity2opengraph
from cubicweb_francearchives.views import (
    JinjaViewMixin,
    top_sections_desc,
    get_template,
    load_portal_config,
)
from cubicweb_francearchives.views.xiti import pagename_from_chapters


# HACK: bypass HTMLStream doctype / head generation: they're managed
# directly by our jinja templates. We only need the body
HTMLStream.getvalue = lambda self: self.body.getvalue()


@monkeypatch(HTMLHead)
def add_onload(self, jscode):
    """original `add_onload` implementation use `$(cw)`
    but `cw` variable is not available
    in francearchive, use `$` instead"""
    self.add_post_inline_script(
        """$(function() {
  %s
});"""
        % jscode
    )


def picklabel(labels, lang):
    return labels.get(lang) or labels.get("fr")


class PniaMainTemplate(JinjaViewMixin, basetemplates.TheMainTemplate):
    template = get_template("maintemplate.jinja2")

    def _handle_added_resources(self, tmpl_context):
        """fetch all resources added with add_{js,css}, etc.

        and backport them into ``tmpl_context`` to feed the main jinja template
        """
        # handle define_var() calls
        var_stmts = [
            (var, json_dumps(value)) for var, value, override in self._cw.html_headers.jsvars
        ]
        tmpl_context["js_vars"] = var_stmts
        # handle add_js() calls
        current_jsfiles = tmpl_context["jsfiles"]
        for jsfile in self._cw.html_headers.jsfiles:
            if jsfile["src"] not in current_jsfiles:
                current_jsfiles.append(jsfile["src"])
        # handle add_onload() calls
        tmpl_context["inline_scripts"] = self._cw.html_headers.post_inlined_scripts
        # handle add_css() calls
        current_cssfiles = tmpl_context["cssfiles"]
        for cssfile, media in self._cw.html_headers.cssfiles:
            if cssfile not in current_cssfiles:
                current_cssfiles.append(cssfile)

    def call(self, view):
        self.set_request_content_type()
        self._cw.html_headers.define_var("BASE_URL", self._cw.build_url(""))
        context = self.template_context(view)
        page_content = view.render()
        context.update(getattr(view, "template_context", lambda: {})())
        self._handle_added_resources(context)
        context["page_content"] = page_content
        self.call_template(**context)

    @cachedproperty
    def portal_config(self):
        return load_portal_config(self._cw.vreg.config)

    @cachedproperty
    def site_links(self):
        rset = self._cw.execute(
            """ Any X, C, U, LF, LE, LS, LD, O ORDERBY C, O WHERE
            X is SiteLink, X link U, X order O,
            X label_fr LF, X label_en LE,  X label_es LS, X label_de LD,
            X context C
            """
        )
        links = defaultdict(list)
        for eid, context, link, lf, le, ls, ld, order in rset:
            css = "d-none d-md-block" if link in ("annuaire/departements") else ""
            link = link if link.startswith("http") else f"%(base_url)s{link}"
            links[context].append(
                {
                    "url": link,
                    "css": css,
                    "labels": {"fr": lf, "en": le or lf, "es": ls or lf, "de": ld or lf},
                }
            )
        return links

    def heroimage_desc(self):
        res = self._cw.execute(
            "Any I, N WHERE  X is CssImage, "
            'X cssid LIKE "hero-%%", X cssid I, '
            "X cssimage_of S, S name N"
        ).rows
        build_url = self._cw.build_url
        if res:
            hcls, section_name = res[randint(0, len(res) - 1)]
        else:
            hcls, section_name = "", ""
        return {
            "hero_src": build_url("static/css/hero-{}-lr.jpg".format(section_name)),
            "hero_xl_src": build_url("static/css/hero-{}-xl.jpg".format(section_name)),
            "hero_lg_src": build_url("static/css/hero-{}-lg.jpg".format(section_name)),
            "hero_md_src": build_url("static/css/hero-{}-md.jpg".format(section_name)),
            "hero_sm_src": build_url("static/css/hero-{}-sm.jpg".format(section_name)),
            "hero_xs_src": build_url("static/css/hero-{}-xs.jpg".format(section_name)),
            "hero_class": hcls,
        }

    def alert(self):
        alert = find_card(self._cw, "alert")
        if alert is not None and alert.content.strip():
            return alert.content

    def heroimage(self, view):
        if view and view.__regid__ == "index":
            return {
                "alert": self.alert(),
                "image": self.heroimage_desc(),
            }
        else:
            return None

    def sn_data(self):
        sn_data = self.portal_config.get("sn", {})
        if not sn_data:
            self.error('could not find "sn" section in portal config')
        return sn_data

    def footer_sections(self):
        return [
            {
                "labels": {"fr": self._cw._(section.split("footer_")[1])},
                "links": self.site_links.get(section, []),
            }
            for section in (
                "footer_public_sites",
                "footer_archives_sites",
                "footer_search_notebooks",
                "footer_usefull_links",
            )
        ]

    def footer_links(self):
        return self.site_links.get("footer_links", [])

    def footer_ministries(self):
        return self.site_links.get("footer_ministries", [])

    def mission_link(self):
        link = self.site_links.get("foundout_link")
        return link[0] if link else None

    def display_top_button(self, view):
        notop_views = ("esearch",)
        if view.__regid__ in notop_views or "search" in self._cw.form:
            return False
        if getattr(view, "notop", False):
            return False
        return True

    def top_sections_desc(self):
        cnx = self._cw
        topsections = top_sections_desc(self._cw)
        # add quick links
        _ = self._cw._
        title, desc, label, name = _("Quick access"), None, None, "quick_access"
        children = []
        for eid, link, child_label, child_desc in cnx.execute(
            """ Any X, U, L, S ORDERBY O WHERE
                X is SiteLink, X context "main_menu_links",
                X order O, X link U,
                X label_{lang} L, X description_{lang} S""".format(
                lang=cnx.lang
            )
        ):
            children.append(
                (
                    eid,
                    link if link.startswith("http") else self._cw.build_url(link),
                    child_label,
                    child_desc or "",
                )
            )
        if children:
            topsections.append((title.upper(), label, name, name, desc or "", children))
        return topsections

    def template_context(self, view):
        archives_label = self._cw._("###in archives###")
        siteres_label = self._cw._("###site resources###")
        lang = self._cw.lang
        if lang == "fr":
            archives_label = reveal_glossary(self._cw, archives_label)
            siteres_label = reveal_glossary(self._cw, siteres_label, cached=True)
        heroimage = self.heroimage(view)
        ctx = {
            "header_row": None,
            "title": view.page_title(),
            "xml_escaped_title": xml_escape(view.page_title()),
            "lang": lang,
            "picklabel": picklabel,
            "base_url": self._cw.build_url("").rstrip("/"),
            "data_url": self._cw.datadir_url,
            "page_url": xml_escape(self._cw.url()),
            "search_info_url": build_faq_url(self._cw, "02_faq_search"),
            "archives_label": archives_label,
            "siteres_label": siteres_label,
            "advanced_search_url": self._cw.build_url("advancedSearch"),
            "cssfiles": self._cw.uiprops["STYLESHEETS"][:],
            "jsfiles": self._cw.uiprops["PNIA_JAVASCRIPTS"][:],
            "homepage": bool(heroimage),
            "mission_link": self.mission_link(),
            "page_id": "homepage" if heroimage else "page",
            "display_totop": self.display_top_button(view),
            "_": self._cw._,
            "topsections": self.top_sections_desc(),
            "heroimage": heroimage,
            "sn": self.sn_data(),
            "cms": self._cw.vreg.config.get("instance-type") == "cms",
            "footer": {
                "ministries": self.footer_ministries(),
                "sections": self.footer_sections(),
                "footer_links": self.footer_links(),
            },
            "query": self._cw.form.get("q", ""),
            "default_picto_src": self._cw.uiprops["DOCUMENT_IMG"],
            "display_professional_access": True,
            "display_search_bar": True,
            "display_advanced_search": FEATURE_ADVANCED_SEARCH,
        }
        # XXX fix breadcrumbs implementation (listview, etc.) later
        breadcrumbs = []
        xiti_chapters = getattr(view, "xiti_chapters", ())
        if self.cw_rset and len(self.cw_rset) == 1:
            entity = self.cw_rset.one()
            ibc = entity.cw_adapt_to("IBreadCrumbs")
            if ibc is not None:
                for bc_element in ibc.breadcrumbs():
                    if isinstance(bc_element, (list, tuple)):
                        breadcrumbs.append(bc_element)
                    elif isinstance(bc_element, str):
                        breadcrumbs.append((None, bc_element))
                    else:
                        breadcrumbs.append((bc_element.absolute_url(), bc_element.dc_title()))
                ctx["breadcrumbs"] = breadcrumbs
            graph = entity2schemaorg(entity)
            if graph is not None:
                ctx["jsonld_graph"] = graph
            ctx["meta"] = entity2meta(entity)
            ctx["open_graph"] = entity2opengraph(entity)
            # if the view explicitly defines some chapters, use them
            # otherwise we would have no way to distinguish chapters for
            # primary and other views for a single entity (e.g. commemo index)
            if not xiti_chapters:
                ixiti = entity.cw_adapt_to("IXiti")
                if ixiti is not None:
                    xiti_chapters = ixiti.chapters
        elif hasattr(view, "breadcrumbs"):
            ctx["breadcrumbs"] = view.breadcrumbs
        xiti_site = self._cw.vreg.config.get("xiti_site")
        if xiti_site:  # cms shouldn't have xiti config
            ctx["xiti"] = {
                "site": xiti_site,
                "n2": self._cw.vreg.config.get("xiti_n2", ""),
                "pagename": pagename_from_chapters(xiti_chapters),
            }
        langswitch_comp = self._cw.vreg["components"].select(
            "pnia.langswitch.component", self._cw, rset=self.cw_rset
        )
        ctx["langswitch"] = list(langswitch_comp.lang_urls())
        return ctx


def registration_callback(vreg):
    vreg.register_and_replace(PniaMainTemplate, basetemplates.TheMainTemplate)
