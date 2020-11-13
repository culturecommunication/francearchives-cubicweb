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
import string

from collections import defaultdict

from datetime import date


from cwtags import tag as T

from logilab.mtconverter import xml_escape
from logilab.common.decorators import cachedproperty

from cubicweb import _
from cubicweb.predicates import is_instance, score_entity, relation_possible

from cubicweb.schema import display_name
from cubicweb.web.views.primary import PrimaryView, URLAttributeView
from cubicweb.view import View, EntityView
from cubicweb.web.views.baseviews import InContextView

from cubicweb.web.views.idownloadable import DownloadView, BINARY_ENCODINGS
from cubicweb.uilib import cut

from cubicweb_card.views import CardPrimaryView
from cubicweb_francearchives.views import (
    JinjaViewMixin,
    get_template,
    format_date,
    exturl_link,
    blank_link_title,
)

from cubicweb_francearchives import SUPPORTED_LANGS
from cubicweb_francearchives.views.service import DeptMapForm, all_services
from cubicweb_francearchives.entities.cms import section
from cubicweb_francearchives.views import html_link, FaqMixin
from cubicweb_francearchives.utils import format_entity_attributes, find_card


class SitemapView(View, JinjaViewMixin):
    __regid__ = "sitemap"
    title = _("Plan du site")
    template = get_template("sitemap.jinja2")

    @cachedproperty
    def xiti_chapters(self):
        return ["sitemap"]

    def get_roots_rset(self):
        cnx = self._cw
        return cnx.execute(
            "Any S, T ORDERBY O WHERE S is Section, NOT EXISTS(X children S), S title T, S order O"
        )

    def call(self, **kw):
        req = self._cw
        roots = self.get_roots_rset()
        sections = []
        req.add_css("css/font-awesome.css")
        for idx, sect in enumerate(roots.entities()):
            sections.append(
                dict(
                    url=sect.absolute_url(),
                    etype="Section",
                    title=sect.title,
                    children=section.get_children(req, sect.eid),
                )
            )
        self.call_template(title=req._(self.title), sections=sections)


class SectionPrimaryView(PrimaryView):
    __select__ = PrimaryView.__select__ & is_instance("Section")

    def entity_call(self, entity, **kw):
        self._cw.form["ancestors"] = str(entity.eid)
        self._cw.form.pop("rql", None)  # remove rql form param which comes from url_rewriter
        path = [entity.eid]
        parents = entity.reverse_children
        while parents:
            parent = parents[0]
            path.append(parent.eid)
            parents = parent.reverse_children
        self.wview(
            "esearch",
            context={
                "section": entity,
                "path": list(reversed(path)),
            },
        )


class ContentPrimaryView(PrimaryView, JinjaViewMixin):
    __abstract__ = True
    template = None
    needs_css = ("css/font-awesome.css",)
    needs_js = ("bundle-glossary.js",)

    def add_css(self):
        for css in self.needs_css:
            self._cw.add_css(css)

    def add_js(self):
        for js in self.needs_js:
            self._cw.add_js(js)

    def template_attrs(self, entity):
        return {"entity": entity.cw_adapt_to("ITemplatable").entity_param()}

    def entity_call(self, entity, **kw):
        self.add_css()
        self.add_js()
        self.render_content(entity)

    def render_content(self, entity):
        self.call_template(**self.template_attrs(entity))


class RecentDataPrimaryView(ContentPrimaryView):
    __abstract__ = True
    template = get_template("newsarticle.jinja2")

    def template_attrs(self, entity):
        attrs = super(RecentDataPrimaryView, self).template_attrs(entity)
        attrs["data_url"] = self._cw.data_url("/").rstrip("/")
        main_attrs = self.main_attrs(entity)
        recents = []
        for _recent in self.related_content(entity).entities():
            if hasattr(_recent, "header"):
                header = _recent.header
            else:
                header = None
            recents.append(
                {
                    "title": _recent.dc_title(),
                    "header": header,
                    "href": _recent.absolute_url(),
                    "date": self.entity_date(_recent),
                    "img_src": _recent.illustration_url,
                    "img_alt": _recent.illustration_alt,
                }
            )
        if recents:
            attrs["recents"] = recents
            main_attrs.update({"recents": recents})
        attrs.update(main_attrs)
        return attrs

    def main_attrs(self, entity):
        _ = self._cw._
        return {
            "_": _,
            "date": self.entity_date(entity),
            "default_picto_src": self._cw.uiprops["DOCUMENT_IMG"],
            "images": self.entity_images(entity),
            "recent_label": _(self.recent_label),
            "all_link": {
                "url": self._cw.build_url(self.all_link_url),
                "label": _(self.all_link_label),
            },
        }


class BaseContentPrimaryView(RecentDataPrimaryView):
    __select__ = RecentDataPrimaryView.__select__ & is_instance("BaseContent")
    template = get_template("article.jinja2")
    all_link_url = "articles"
    all_link_label = _("See all articles")
    recent_label = _("###Recent Articles###")

    def entity_call(self, entity):
        self._cw.add_js("bundle-pnia-toc.js")
        self._cw.add_js("ResizeSensor.js")
        self._cw.add_js("sticky-sidebar.min.js")
        super(BaseContentPrimaryView, self).entity_call(entity)

    def related_content(self, entity):
        return self._cw.execute(
            "Any X ORDERBY X DESC LIMIT 3 "
            "WHERE X is BaseContent, NOT C manif_prog X, "
            "NOT X identity S, S eid %(e)s",
            {"e": entity.eid},
        )

    def entity_images(self, entity):
        return entity.basecontent_image

    def entity_date(self, entity):
        return format_date(entity.modification_date, self._cw)


class NewsContentPrimaryView(RecentDataPrimaryView):
    __select__ = RecentDataPrimaryView.__select__ & is_instance("NewsContent")
    all_link_url = "actualites"
    all_link_label = _("See all news")
    recent_label = _("###Recent News###")

    def related_content(self, entity):
        return self._cw.execute(
            "Any X ORDERBY D DESC LIMIT 3 "
            "WHERE X is NewsContent, X news_image N, "
            "X start_date D, "
            "(X stop_date NULL OR X stop_date >= %(t)s), "
            "NOT X identity S, S eid %(e)s",
            {"e": entity.eid, "t": date.today()},
        )

    def entity_images(self, entity):
        return entity.news_image

    def entity_date(self, entity):
        return format_date(entity.start_date, self._cw)


class CommemoMixin(object):
    template = get_template("commemorationitem.jinja2")

    def template_context(self):
        title = self._cw._("commemo-section-title %s") % self.collection.year
        html = []
        w = html.append
        with T.div(w, id="section-article-header", Class="center"):
            w(T.h1(title))
            html.extend(self.vtimeline_link(self.collection))
        return {
            "default_picto_src": self._cw.uiprops["DOCUMENT_IMG"],
            "header_row": "\n".join(str(c) for c in html),
        }

    def timeline(self, this_year):
        self._cw.add_css("lightslider-master/css/lightslider.min.css")
        self._cw.add_js("lightslider-master/js/lightslider.min.js")
        rset = self._cw.execute("DISTINCT Any CY WHERE C commemoration_year CY")
        min_year = min([year for year, in rset])
        max_year = max([year for year, in rset])
        _ = self._cw._
        with T.nav(self.w, id="timeline", Class="hidden-print", role="navigation"):
            with T.div(self.w, Class="col-xs-2 col-sm-1"):
                alt = _("Display previous years")
                self.w(
                    T.img(
                        src=self._cw.data_url("images/icon_nav_scrollleft.svg"),
                        Class="timeline-control control-left",
                        alt=alt,
                    )
                )
            with T.div(self.w, id="slider-dates", Class="col-xs-8 col-sm-10"):
                with T.ul(self.w, id="light-slider"):
                    for year in range(min_year, max_year + 1):
                        url = self._cw.build_url("commemo/recueil-%s/" % year)
                        if year == this_year:
                            self.w(
                                T.li(
                                    T.span(_("Selected year"), Class="sr-only"),
                                    T.span(str(year), Class="active"),
                                )
                            )
                        else:
                            title = _("Go to commemorations %s") % year
                            self.w(T.li(T.span(T.a(str(year), href=url, title=title))))
            with T.div(self.w, Class="col-xs-2 col-sm-1"):
                alt = _("Display next years")
                self.w(
                    T.img(
                        src=self._cw.data_url("images/icon_nav_scrollright.svg"),
                        Class="timeline-control control-right",
                        alt=alt,
                    )
                )

    def render_left_block(self, title, children):
        _ = self._cw._
        with T.section(self.w, Class="commemoration-side-content"):
            with T.div(
                self.w,
                Class="commemoration-side-content-header",
                title="{} {}".format(_("Display the section: "), title),
            ):
                self.w(T.h2(title, Class="no-style header-title"))
            with T.div(self.w, Class="commemoration-side-content-item"):
                with T.ul(self.w):
                    for child in children:
                        if hasattr(child, "cw_etype"):
                            self.w(
                                T.li(
                                    T.h3(
                                        T.a(child.title, href=child.absolute_url()),
                                        Class="no-style",
                                    )
                                )
                            )
                        else:
                            title, url = child
                            self.w(T.li(T.h3(T.a(title, href=url), Class="no-style")))

    def render_left_block_with_date(self, subsection, children):
        with T.section(self.w, Class="commemoration-side-content"):
            title = subsection.title or ""
            with T.div(
                self.w,
                Class="commemoration-side-content-header",
                title="{} {}".format(_("Display the section: "), title),
            ):
                self.w(T.h2(xml_escape(title), Class="no-style header-title"))
            with T.div(self.w, Class="commemoration-side-content-item"):
                for rset in children:
                    with T.div(self.w, Class="event-item"):
                        with T.div(self.w, Class="event-timeline"):
                            self.w(T.span(str(rset[0][-1] or ""), Class="date"))
                            self.w(T.span(Class="line"))
                        with T.div(self.w, Class="event-title no-style"):
                            with T.ul(self.w):
                                for child in rset.entities():
                                    self.w(
                                        T.li(
                                            T.h3(
                                                T.a(child.title, href=child.absolute_url()),
                                                Class="no-style",
                                            )
                                        )
                                    )

    def template_attrs(self, entity):
        attrs = super(CommemoMixin, self).template_attrs(entity)
        _ = self._cw._
        attrs["_"] = _
        attrs["i18n"] = {"year": _("year")}
        return attrs

    def render_collection(self, collection):
        with T.div(self.w, Class="row"):
            self.timeline(collection.year)
        pres_children, subsections = [], []
        rset = self._cw.execute(
            "Any X, T ORDERBY O WHERE "
            "S is CommemoCollection, S eid %(e)s, "
            "S children X, "
            "X title T, "
            "X order O",
            {"e": collection.eid},
        )
        for c in rset.entities():
            if c.cw_etype == "Section":
                subsections.append(c)
            else:
                pres_children.append(c)
        with T.div(self.w, Class="col-lg-4"):
            with T.nav(self.w, id="commemoration-side", role="navigation"):
                self.render_left_block(self._cw._("###Presentation###"), pres_children)
                for subsection in subsections:
                    rset = self._cw.execute(
                        "Any X, T, Y ORDERBY Y WHERE "
                        "S is Section, S eid %(e)s, "
                        "S children X, "
                        "X title T, "
                        "X year Y",
                        {"e": subsection.eid},
                    )
                    self.render_left_block_with_date(subsection, rset.split_rset(col=2))

    def vtimeline_link(self, collection):
        html = []
        w = html.append
        data = self._cw.execute(
            ("Any COUNT(X) WHERE X collection_top CC, " "X commemo_dates D, CC eid %(eid)s"),
            {"eid": collection.eid},
        )[0][0]
        if data:
            url = self._cw.build_url("%s/timeline" % collection.rest_path().rstrip("/"))
            with T.a(
                w,
                Class="timeline-link hidden-print",
                href=xml_escape(url),
                target="_blank",
                rel="nofollow noopener noreferrer",
                title=blank_link_title(self._cw, url),
            ):
                w(self._cw._("See the timeline"))
                w(T.i(Class="fa fa-external-link-square", aria_hidden="true"))
        return html


class CommemorationItemPrimaryView(CommemoMixin, ContentPrimaryView):
    __select__ = ContentPrimaryView.__select__ & is_instance("CommemorationItem")

    def template_attrs(self, entity):
        attrs = super(CommemorationItemPrimaryView, self).template_attrs(entity)
        _ = self._cw._
        attrs.update({"_": _, "i18n": {"year": _("year")}})
        authors = entity.cw_adapt_to("IMeta").author()
        if authors:
            title = _("Text author:") if len(authors) == 1 else _("Text authors:")
            data = _("###list_separator###").join(authors)
            attrs["authors"] = [title, data]
        return attrs

    @cachedproperty
    def collection(self):
        return self.cw_rset.get_entity(0, 0).collection

    def render_content(self, entity):
        self.render_collection(entity.collection_top[0])
        self.call_template(**self.template_attrs(entity))

    def render_collection(self, collection):
        self.timeline(collection.year)


class CommemoCollectionPrimaryView(CommemoMixin, ContentPrimaryView):
    __select__ = ContentPrimaryView.__select__ & is_instance("CommemoCollection")

    @cachedproperty
    def collection(self):
        return self.cw_rset.get_entity(0, 0)

    def render_content(self, entity):
        self.render_collection(entity)
        rset = self._cw.execute(
            "Any X ORDERBY O LIMIT 1 WHERE "
            "C is CommemoCollection, C eid %(e)s, C children X, X order O",
            {"e": entity.eid},
        )
        if not rset:  # empty commemo collection, probably just created
            self.w(self._cw._("empty-commemocollection"))
            return
        else:
            first_child = rset.one().cw_adapt_to("ITemplatable").entity_param()
        with T.div(self.w, Class="col-lg-8"):
            self.call_template(**self.template_attrs(first_child))


class AuthorityRecordPrimaryView(ContentPrimaryView):
    __select__ = ContentPrimaryView.__select__ & is_instance("AuthorityRecord")
    need_css = ("css/font-awsome.css",)
    template = get_template("authorityrecord.jinja2")

    def template_attrs(self, entity):
        """Build the dictionnary for the jinja template by
        merging all required data from the AuthorithyRecord entity"""
        attrs = super(AuthorityRecordPrimaryView, self).template_attrs(entity)
        attrs["_"] = self._cw._
        attrs["main_props"] = []
        for data in (
            entity.name_entry(),
            entity.places,
            entity.functions,
            entity.function_relations,
            entity.occupations,
            entity.legal_statuses,
            entity.language_used,
            entity.history,
            entity.general_context,
            entity.structure,
            entity.mandates,
            entity.source_entry,
            entity.main_infos,
            entity.maintenance_events,
            entity.cpf_relations,
            entity.resource_relations,
            entity.authorities,
        ):
            for label, values in data.items():
                values = format_entity_attributes(values, "")
                if values:
                    attrs["main_props"].append((label, values))
        if entity.related_service:
            attrs.update({"publisher": entity.cw_adapt_to("IPublisherInfo").serialize()})
        return attrs


class FindingAidPrimaryView(FaqMixin, ContentPrimaryView):
    __select__ = ContentPrimaryView.__select__ & is_instance("FindingAid", "FAComponent")
    needs_css = ("css/font-awesome.css",)
    template = get_template("findingaid.jinja2")
    faq_category = "03_faq_ir"

    def render_content(self, entity):
        self.call_template(**self.template_attrs(entity))
        self.content_navigation_components("related-top-main-content")

    def template_attrs(self, entity):
        attrs = super(FindingAidPrimaryView, self).template_attrs(entity)
        adapter = entity.cw_adapt_to("entity.main_props")
        service = entity.related_service
        default_picto_src = []
        if service and service.illustration_url:
            default_picto_src = [service.illustration_url]
        default_picto_src.append(self._cw.uiprops["DOCUMENT_IMG"])
        attrs.update(
            {
                "publisher": entity.cw_adapt_to("IPublisherInfo").serialize(),
                "date": adapter.formatted_dates,
                "title": adapter.shortened_title(),
                "main_props": adapter.properties(),
                "default_picto_src": ";".join(default_picto_src),
                "faqs": self.faqs_attrs(),
                "cms": self._cw.vreg.config.get("instance-type") == "cms",
                "_": self._cw._,
            }
        )
        attachements = adapter.downloadable_attachements()
        if attachements:
            attrs["attachments"] = attachements
        return attrs


class MapPrimaryView(PrimaryView):
    __select__ = PrimaryView.__select__ & is_instance("Map")
    template = get_template("map-page.jinja2")
    needs_js = ("bundle-glossary.js",)

    def entity_call(self, entity):
        legends, options = {}, {"urls": {}, "colors": {}}
        items = defaultdict(list)
        services = list(all_services(self._cw))
        services_map = dict([(s.dpt_code.lower(), s.name) for s in services])
        for v in entity.data():
            if v["legend"]:
                legend = v["legend"]
                if legend.lower() == "legende":
                    continue
                items[v["color"]].append((services_map.get(v["code"], ""), v.get("url")))
                legends[v["color"]] = legend
            if v["url"]:
                options["urls"][v["code"]] = v["url"]
            if v["color"]:
                options["colors"][v["code"]] = v["color"].lower()
        dept_map_form = DeptMapForm(options)
        legends = [(c, l, items.get(c, [])) for c, l in legends.items()]
        self.w(
            self.template.render(
                _=self._cw._,
                map=entity,
                map_form=dept_map_form.render(self._cw, services),
                legends=legends,
            )
        )


class PniaDownloadView(DownloadView):
    def set_request_content_type(self):
        """don not set disposition='attachment' in content_type"""
        entity = self.cw_rset.complete_entity(self.cw_row or 0, self.cw_col or 0)
        adapter = entity.cw_adapt_to("IDownloadable")
        encoding = adapter.download_encoding()
        if encoding in BINARY_ENCODINGS:
            contenttype = "application/%s" % encoding
            encoding = None
        else:
            contenttype = adapter.download_content_type()
        self._cw.set_content_type(
            contenttype or self.content_type,
            filename=adapter.download_file_name(),
            encoding=encoding,
        )

    def entity_call(self, entity):
        adapter = entity.cw_adapt_to("IDownloadable")
        self.w(adapter.download_data())


class FilePrimaryView(PniaDownloadView):
    __regid__ = "primary"
    __select__ = PrimaryView.__select__ & is_instance("File")


class CircularPrimaryView(ContentPrimaryView):
    __select__ = ContentPrimaryView.__select__ & is_instance("Circular")
    needs_css = ("css/font-awesome.css",)
    template = get_template("circular.jinja2")

    def get_related_cirular(self, circ_id):
        if circ_id:
            rset = self._cw.execute("Any X WHERE X is Circular, X circ_id %(c)s", {"c": circ_id})
            if rset:
                return rset.one().view("incontext")
        return circ_id

    def template_attrs(self, entity):
        attrs = super(CircularPrimaryView, self).template_attrs(entity)
        _ = self._cw._
        attrs["_"] = _
        if entity.signing_date:
            attrs["date"] = format_date(entity.signing_date, self._cw)
        main_props = []
        circular_link = exturl_link(self._cw, entity.link) if entity.link else None
        for attr, value in (
            (_("circular_kind_label"), entity.kind),
            (_("circular_code_label"), entity.code),
            (_("circular_nor_label"), entity.nor),
            (_("circular_status_label"), _(entity.status)),
            (_("circular_link_label"), circular_link),
            (
                _("circular_additional_link_label"),
                ", ".join(e.view("urlattr", rtype="url") for e in entity.additional_link),
            ),
            (
                _("circular_attachment_label"),
                ", ".join(e.view("incontext") for e in entity.attachment),
            ),
            (
                _("circular_additional_attachment_label"),
                ", ".join(e.view("incontext") for e in entity.additional_attachment),
            ),
            (_("circular_signing_date_label"), format_date(entity.signing_date, self._cw)),
            (_("circular_siaf_daf_kind_label"), entity.siaf_daf_kind),
            (_("circular_siaf_daf_code_label"), entity.siaf_daf_code),
            (
                _("circular_siaf_daf_signing_date_label"),
                format_date(entity.siaf_daf_signing_date, self._cw),
            ),
            (_("circular_producer_label"), entity.producer),
            (_("circular_producer_acronym_label"), entity.producer_acronym),
            (
                _("circular_modification_date_label"),
                format_date(entity.circular_modification_date, self._cw),
            ),
            (_("circular_abrogation_date_label"), format_date(entity.abrogation_date, self._cw)),
            (_("circular_abrogation_text_label"), self.get_related_cirular(entity.abrogation_text)),
            (_("circular_archival_field_label"), entity.archival_field),
            (
                _("circular_historical_context_label"),
                ", ".join(e.view("incontext") for e in entity.historical_context),
            ),
            (
                _("circular_business_field_label"),
                ", ".join(e.view("incontext") for e in entity.business_field),
            ),
            (
                _("circular_document_type_label"),
                ", ".join(e.view("incontext") for e in entity.document_type),
            ),
            (_("circular_action_label"), ", ".join(e.view("incontext") for e in entity.action)),
            (
                _("circular_modified_text_label"),
                ", ".join(e.view("incontext") for e in entity.modified_text),
            ),
            (
                _("circular_modifying_text_label"),
                ", ".join(e.view("incontext") for e in entity.modifying_text),
            ),
            (
                _("circular_revoked_text_label"),
                ", ".join(e.view("incontext") for e in entity.revoked_text),
            ),
        ):
            if value:
                label = display_name(self._cw, attr, context="Circular")
                main_props.append((label, value))
        attrs["main_props"] = main_props
        return attrs


class OfficialTextInContext(InContextView):
    __select__ = InContextView.__select__ & is_instance("OfficialText")

    max_title_size = 140

    def cell_call(self, row, col):
        entity = self.cw_rset.get_entity(row, col)
        title = entity.dc_title()
        circular = entity.circular[0] if entity.circular else None
        if not circular:
            self.w(title)
            return
        date = circular.sort_date()
        if date:
            title = "{cid} {date}".format(
                date=self._cw._("on %s ") % format_date(date, self._cw), cid=title
            )
        kwargs = {"href": xml_escape(circular.absolute_url())}
        desc = cut(entity.dc_description(), 50)
        if desc:
            desc = "{} - {}".format(title, desc)
            kwargs["title"] = xml_escape(desc)
        self.w(T.a(xml_escape(title), **kwargs))


class CommemoCollectionAlphaIndexView(CommemoCollectionPrimaryView):
    __regid__ = "commemo-alpha-index"
    __select__ = EntityView.__select__ & is_instance("CommemoCollection")
    template = get_template("collectionalphaindex.jinja2")

    @cachedproperty
    def xiti_chapters(self):
        ixiti = self.cw_rset.get_entity(0, 0).cw_adapt_to("IXiti")
        chapters = ixiti.chapters
        return chapters + ["index"]

    def template_attrs(self, entity):
        attrs = super(CommemoCollectionAlphaIndexView, self).template_attrs(entity)
        rsets = {}
        uppercase = str(string.ascii_uppercase)
        for letter in uppercase:
            rset = self._cw.execute(
                "Any CI ORDERBY Y WHERE CI alphatitle CIA, "
                "CI collection_top X, CI year Y, X eid %(x)s "
                "HAVING UPPER(SUBSTRING(CIA, 1, 1)) = %(l)s",
                {"x": entity.eid, "l": letter},
            )
            rsets[letter] = rset
        attrs["uppercase"] = uppercase
        attrs["rsets"] = rsets
        return attrs

    def render_content(self, entity):
        self.render_collection(entity)
        with T.div(self.w, Class="col-lg-8"):
            self.call_template(**self.template_attrs(entity))


class UrLBasedAttributeView(URLAttributeView):
    """ open the url in a new tab"""

    __select__ = URLAttributeView.__select__ & is_instance("ExternRef", "Link", "ExternalUri")

    def entity_call(self, entity, rtype="subject", **kwargs):
        url = entity.printable_value(rtype)
        if url:
            self.w(exturl_link(self._cw, url))


class IndexURLAttributeView(URLAttributeView):
    """ open the url in a new tab"""

    __select__ = URLAttributeView.__select__ & is_instance(
        "Concept",
        "Person",
    )

    def entity_call(self, entity, rtype="subject", **kwargs):
        url = entity.printable_value(rtype)
        if url:
            title = blank_link_title(self._cw, url)
            self.w(
                T.a(
                    entity.dc_title(),
                    href=xml_escape(url),
                    title=title,
                    target="_blank",
                    rel="nofollow noopener noreferrer",
                )
            )


class DigitizedVersionUrLAttributeView(EntityView):
    __regid__ = "urlattr"
    __select__ = EntityView.__select__ & is_instance("DigitizedVersion")

    def entity_call(self, entity, rtype="subject", **kwargs):
        url = entity.printable_value(rtype)
        if url:
            self.w(exturl_link(self._cw, url, icon="file-archive-o"))


def is_virtual_exhibit(entity):
    return entity.reftype == "Virtual_exhibit"


class ExternRefPrimaryMixIn(object):
    def website_link(self, entity):
        return (self._cw._("website_label:"), entity.view("urlattr", rtype="url"))

    def main_props(self, entity):
        _ = self._cw._
        main_props = []
        # indexes
        main_props.append(
            (
                _("persname_index_label"),
                ", ".join(e.view("incontext") for e in entity.main_indexes(None).entities()),
            )
        )
        main_props.append(
            (
                _("subject_indexes_label"),
                ", ".join(e.view("incontext") for e in entity.subject_indexes().entities()),
            )
        )
        main_props.append(
            (
                _("geo_indexes_label"),
                ", ".join(e.view("incontext") for e in entity.geo_indexes().entities()),
            )
        )
        service = entity.exref_service
        if service:
            main_props.append((_("service_label"), ", ".join(e.view("incontext") for e in service)))
        if entity.url:
            main_props.append(self.website_link(entity))
        return [entry for entry in main_props if entry[-1]]


class ExternRefPrimaryView(ExternRefPrimaryMixIn, ContentPrimaryView):
    __select__ = (
        PrimaryView.__select__
        & is_instance("ExternRef")
        & ~score_entity(lambda e: is_virtual_exhibit(e))
    )
    template = get_template("externref.jinja2")

    def template_attrs(self, entity):
        attrs = super(ExternRefPrimaryView, self).template_attrs(entity)
        attrs["years"] = entity.years
        attrs["main_props"] = self.main_props(entity)
        return attrs


class VirtualExhibitExternRefPrimaryView(ExternRefPrimaryMixIn, RecentDataPrimaryView):
    __select__ = (
        PrimaryView.__select__
        & is_instance("ExternRef")
        & score_entity(lambda e: is_virtual_exhibit(e))
    )
    template = get_template("virtualexhibit.jinja2")
    all_link_url = "expositions"
    all_link_label = _("See all virtual exhibits")
    recent_label = _("Virtual_exhibit")

    def website_link(self, entity):
        label = self._cw._("Consult the virtual exhibits")
        link = str(html_link(self._cw, entity.url, label=label))
        return (None, link)

    def template_attrs(self, entity):
        attrs = super(VirtualExhibitExternRefPrimaryView, self).template_attrs(entity)
        attrs["main_props"] = self.main_props(entity)
        return attrs

    def related_content(self, entity):
        return self._cw.execute(
            "Any X ORDERBY X DESC LIMIT 3 "
            "WHERE X is ExternRef, X reftype %(r)s, "
            "NOT X identity S, S eid %(e)s",
            {"e": entity.eid, "r": entity.reftype},
        )

    def entity_date(self, entity):
        return entity.years

    def entity_images(self, entity):
        return entity.externref_image


class PniaPersonPrimaryView(ContentPrimaryView):
    __regid__ = "primary"
    __select__ = ContentPrimaryView.__select__ & is_instance("Person")
    template = get_template("person.jinja2")

    def template_attrs(self, entity):
        attrs = super(PniaPersonPrimaryView, self).template_attrs(entity)
        _ = self._cw._
        main_props = [
            (_("name_label:"), entity.name),
            (_("forenames_label:"), entity.forenames),
            (_("death_year_label:"), entity.death_year),
            (_("dates_label:"), entity.dates_description),
            (_("locations_label:"), entity.locations_description),
            (
                _("indexes_label:"),
                ", ".join(e.view("incontext") for e in entity.agent_indexes().entities()),
            ),
        ]

        if entity.document_uri:
            self._cw.add_css("css/font-awesome.css")
            url = entity.document_uri
            link = (
                '<a href="{url}" rel="nofollow noopener noreferrer" '
                'target="_blank" title="{title}">'
                "{label} "
                '<i class="fa fa-external-link-square" aria-hidden="true"> </i>'
                "</a>".format(
                    url=xml_escape(url),
                    label=self._cw._("oai-origin-website"),
                    title=blank_link_title(self._cw, url),
                )
            )
            main_props.insert(0, (_("website_label:"), link))
        main_props = [entry for entry in main_props if entry[-1]]
        attrs["main_props"] = main_props
        return attrs


class PniaCardPrimaryView(ContentPrimaryView):
    __select__ = ContentPrimaryView.__select__ & is_instance("Card")
    template = get_template("card.jinja2")

    def render_content(self, entity):
        with T.div(self.w, Class="row"):
            with T.div(self.w, Class="col-md-9"):
                self.call_template(**self.template_attrs(entity))


class PniaTranslationsPrimaryView(ContentPrimaryView):
    __select__ = ContentPrimaryView.__select__ & relation_possible("translation_of", role="subject")
    template = get_template("translation.jinja2")
    editable = False

    def get_translation(self, original, entity):
        trads = []
        if self.editable:
            translations = {}
            for res in original.i18n_rset().iter_rows_with_entities():
                trad = res[0]
                translations[trad.language] = trad
            for lang in SUPPORTED_LANGS:
                if lang == "fr":
                    continue
                trad = translations.get(lang)
                if trad:
                    state = self._cw._(trad.cw_adapt_to("IWorkflowable").state)
                    if trad.eid != entity.eid:
                        trad = trad.view("incontext")
                    else:
                        trad = trad.dc_title()
                    trad = "{} ({})".format(trad, state)
                else:
                    trad = _("no translation yet exists")
                trads.append((self._cw._(lang), trad))
        return trads

    def content_meta_props(self, entity):
        return [(self._cw._(entity.language), "language")]

    def main_props(self, entity):
        _ = self._cw._
        main_props = []
        original = entity.original_entity
        main_props.append((_("original ressource"), original.view("incontext")))
        for attr in original.i18nfields:
            main_props.append((_(attr), entity.printable_value(attr)))
        return main_props

    def template_attrs(self, entity):
        attrs = super(PniaTranslationsPrimaryView, self).template_attrs(entity)
        _ = self._cw._
        original = entity.original_entity
        attrs.update(
            {
                "_": _,
                "editable": self.editable,
                "original": original.view("incontext"),
                "content_meta": self.content_meta_props(entity),
            }
        )
        attrs["translations"] = self.get_translation(original, entity)
        attrs["main_props"] = self.main_props(entity)
        return attrs


class GlossaryTermPrimaryView(ContentPrimaryView):
    __select__ = ContentPrimaryView.__select__ & is_instance("GlossaryTerm")
    template = get_template("glossaryterm.jinja2")

    def content_meta_props(self, entity):
        link = """<a href="{url}">{title}</a>""".format(
            url=self._cw.build_url(
                "glossaire",
            ),
            title=self._cw._("Glossary"),
        )
        return [
            (link, "book"),
        ]

    def main_props(self, entity):
        return []

    def template_attrs(self, entity):
        attrs = super(GlossaryTermPrimaryView, self).template_attrs(entity)
        attrs["content_meta"] = self.content_meta_props(entity)
        attrs["main_props"] = self.main_props(entity)
        return attrs


class GlossaryView(View, JinjaViewMixin):
    __regid__ = "glossary"
    template = get_template("glossary.jinja2")
    title = _("Glossary")
    editable = False

    @property
    def breadcrumbs(self):
        b_url = self._cw.build_url
        breadcrumbs = [(b_url(""), self._cw._("Home"))]
        breadcrumbs.append((b_url("glossary"), self._cw._("Glossary")))
        return breadcrumbs

    def card(self):
        card = find_card(self._cw, "glossary-card")
        if card is not None:
            return card

    def build_glossary(self):
        rset = self._cw.execute(
            """Any X, L, T, D, A ORDERBY T WHERE X is GlossaryTerm, X term T,
            X description D, X sort_letter L, X anchor A"""
        )
        glossary = defaultdict(list)
        for eid, letter, term, description, sort_term in rset:
            glossary[letter].append((eid, term, description, sort_term))
        return glossary

    def add_js(self):
        self._cw.add_js("ResizeSensor.js")
        self._cw.add_js("sticky-sidebar.min.js")
        self._cw.add_js("cubes.pnia_glossary.js")

    def call(self, **kw):
        self.add_js()
        req = self._cw
        letters = [
            e[0]
            for e in req.execute(
                "DISTINCT Any L ORDERBY L WHERE X is GlossaryTerm, X sort_letter L"
            ).rows
        ]
        card = self.card()
        attrs = {
            "glossary": self.build_glossary(),
            "letters": letters,
            "card": card.content if card else None,
            "title": card.title if card else req._(self.title),
            "editable": self.editable,
            "base_url": self._cw.build_url("").rstrip("/"),
            "glossary_url": self._cw.build_url("glossaire"),
            "_": req._,
        }
        self.call_template(**attrs)


class FaqStartView(View, JinjaViewMixin):
    __regid__ = "faq"
    template = get_template("faq.jinja2")
    title = _("FAQ")
    editable = False

    @property
    def breadcrumbs(self):
        b_url = self._cw.build_url
        breadcrumbs = [(b_url(""), self._cw._("Home"))]
        breadcrumbs.append((b_url("glossary"), self._cw._("FAQ")))
        return breadcrumbs

    def call(self, **kw):
        self._cw.add_js("bundle-pnia-faq.js")
        req = self._cw
        rset = req.execute(
            """Any X, Q, A, C, O ORDERBY C, O WHERE X is FaqItem,
               X question Q, X answer A, X category C, X order O"""
        )
        faqs = defaultdict(list)
        for eid, question, answer, category, order in rset:
            faqs[category].append((eid, question, answer))
        faqs = sorted(faqs.items(), key=lambda e: e[0])
        attrs = {
            "editable": self.editable,
            "_": req._,
            "faqs": faqs,
            "title": req._(self.title),
        }
        self.call_template(**attrs)


class FaqItemPrimaryView(ContentPrimaryView):
    __select__ = ContentPrimaryView.__select__ & is_instance("FaqItem")
    template = get_template("faqitem.jinja2")

    def content_meta_props(self, entity):
        link = """<a href="{url}">{title}</a>""".format(
            url=self._cw.build_url(
                "faq",
            ),
            title=self._cw._("Faq"),
        )
        return [
            (link, "question"),
        ]

    def main_props(self, entity):
        return []

    def template_attrs(self, entity):
        attrs = super(FaqItemPrimaryView, self).template_attrs(entity)
        attrs["_"] = self._cw._
        attrs["content_meta"] = self.content_meta_props(entity)
        attrs["main_props"] = self.main_props(entity)
        return attrs


def registration_callback(vreg):
    vreg.register_all(list(globals().values()), __name__, (PniaDownloadView, PniaCardPrimaryView))
    vreg.register_and_replace(PniaDownloadView, DownloadView)
    vreg.register_and_replace(PniaCardPrimaryView, CardPrimaryView)
