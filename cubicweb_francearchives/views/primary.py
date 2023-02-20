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

from collections import defaultdict, OrderedDict
from cubicweb_elasticsearch.es import get_connection

from cwtags import tag as T
from elasticsearch_dsl.query import Q, Bool
from elasticsearch_dsl.search import Search

from logilab.mtconverter import xml_escape
from logilab.common.decorators import cachedproperty
from logilab.common.registry import objectify_predicate

from cubicweb import _
from cubicweb.predicates import is_instance, score_entity, relation_possible

from cubicweb.schema import display_name
from cubicweb.web.views.primary import PrimaryView, URLAttributeView
from cubicweb.view import View, EntityView, StartupView
from cubicweb.web.views.baseviews import InContextView
from cubicweb.web.views.idownloadable import DownloadView, BINARY_ENCODINGS
from cubicweb.uilib import cut, remove_html_tags

from cubicweb_card.views import CardPrimaryView
from cubicweb_francearchives.entities.rdf import RDF_FORMAT_EXTENSIONS
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
from cubicweb_francearchives.views import FaqMixin, SiteTourMixin, format_number
from cubicweb_francearchives.utils import find_card
from cubicweb_francearchives.utils import is_external_link, number_of_archives
from cubicweb_francearchives.utils import get_hp_articles


class ShareLinksMixin:
    def sharelinks(self, entity):
        url = entity.absolute_url()
        return {
            "facebook": f"https://www.facebook.com/sharer/sharer.php?u={url}",
            "twitter": f"http://www.twitter.com/share?url={url}",
            "mail": f"mailto:?subject=&body={url}",
            "title": _("Share"),
            "copyurl": url,
            "_": self._cw._,
        }


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


class SectionTreeView(EntityView, JinjaViewMixin):
    __regid__ = "section-tree"
    template = get_template("section-tree.jinja2")

    def get_content_for_tree(self, entity):
        data = []
        tree = entity.cw_adapt_to("ISectionTree")
        if tree:
            data = tree.retrieve_subsections(section_mode="mode_tree")
        return data

    def call_template(self, w, **ctx):
        w(self.template.render(**ctx))

    def cell_call(self, row, col):
        self._cw.add_js("cubes.pnia_section_tree.js")
        self._cw.add_js("bundle-pnia-sectiontree.js")
        self._cw.add_css("css/font-awesome.css")
        entity = self.cw_rset.get_entity(row, col)
        data = self.get_content_for_tree(entity) if entity.display_tree else None
        return self.call_template(
            self.w,
            has_sections=any([s["children"] for s in data]),
            data=data,
            _=self._cw._,
        )


class SectionThemesView(EntityView, JinjaViewMixin):
    __regid__ = "section-themes"
    template = get_template("section-themes.jinja2")

    def call_template(self, w, **ctx):
        w(self.template.render(**ctx))

    def cell_call(self, row, col, themes):
        self._cw.add_css("css/font-awesome.css")
        return self.call_template(
            self.w,
            entities=themes,
            _=self._cw._,
        )


class SectionInfoView(EntityView, JinjaViewMixin):
    __regid__ = "section-info"
    template = get_template("section-info.jinja2")
    __select__ = EntityView.__select__ & is_instance("Section")

    def call_template(self, w, **ctx):
        w(self.template.render(**ctx))

    def cell_call(self, row, col):
        entity = self.cw_rset.get_entity(row, col)
        return self.call_template(
            self.w,
            entity=entity.cw_adapt_to("ITemplatable").entity_param(),
            img_src=entity.illustration_url,
            img_alt=entity.illustration_alt,
            _=self._cw._,
        )


class SectionPrimaryView(PrimaryView):
    __select__ = PrimaryView.__select__ & is_instance("Section")

    def entity_call(self, entity, **kw):
        self.w(entity.view("section-info"))
        display_mode = entity.display_mode
        if display_mode != "mode_tree":
            # display results results for default and themes mode
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
        else:
            self.w(entity.view("section-tree"))


class MiradorEmbedPageView(StartupView, JinjaViewMixin):
    __regid__ = "mirador"
    template = get_template("mirador.jinja2")

    def page_title(self):
        return self._cw._("Mirador Viewer")

    def call(self, **kwargs):
        return self.call_template(**self.template_context())

    def template_context(self):
        return {
            "_": self._cw._,
            "data_url": self._cw.datadir_url,
            "lang": self._cw.lang,
            "pagetitle": self.page_title(),
            "iiif_manifest": self._cw.form.get("manifest", ""),
        }


@objectify_predicate
def is_gerer_section(cls, req, rset, row=0, col=0, **kwargs):
    return rset.get_entity(0, 0).name == "gerer"


class GererPrimaryView(SectionPrimaryView, JinjaViewMixin):
    __select__ = SectionPrimaryView.__select__ & is_gerer_section()
    template = get_template("homepage_archivists.jinja2")

    def page_title(self):
        entity = self._cw.execute("Any X WHERE X is Section, X name 'gerer'").one()
        entity = entity.cw_adapt_to("ITemplatable").entity_param()
        return f'{entity.title} ({self._cw.property_value("ui.site-title")})'

    def retrieve_quick_access(self):
        links = []
        for link, title in self._cw.execute(
            """ Any L, T ORDERBY O WHERE
                X is SiteLink, X context "archiviste_hp_links",
                X order O, X link L,
                X label_{lang} T""".format(
                lang=self._cw.lang
            )
        ):
            url = link if link.startswith("http") else self._cw.build_url(link)
            links.append((url, title, is_external_link(url, self._cw.base_url())))
        return links

    def template_context(self):
        return {"display_professional_access": False}

    def entity_call(self, entity, **kw):
        self._cw.add_js("cubes.pnia_section_tree.js")
        self._cw.add_js("bundle-pnia-sectiontree.js")
        self._cw.add_css("css/font-awesome.css")
        self._cw.form["ancestors"] = str(entity.eid)
        self._cw.form.pop("rql", None)  # remove rql form param which comes from url_rewriter
        _ = self._cw._
        news_url = self._cw.build_url(
            "search", **{"ancestors": entity.eid, "es_cw_etype": "NewsContent"}
        )
        archives = format_number(number_of_archives(self._cw), self._cw)
        tree = entity.cw_adapt_to("ISectionTree")
        attrs = {
            "_": _,
            "req": self._cw,
            "sections": tree.retrieve_subsections(),
            "quick_links": self.retrieve_quick_access(),
            "news_url": news_url,
            "archives_url": self._cw.build_url("inventaires"),
            "archives_label": _("See {} archives").format(archives),
            "entities": get_hp_articles(self._cw, "onhp_arch"),
        }

        self.call_template(**attrs)


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


class RecentDataPrimaryView(ShareLinksMixin, ContentPrimaryView):
    __abstract__ = True
    needs_js = ("cubes.pnia_sharelinks.js",)
    template = get_template("article.jinja2")
    recent_label = _("Similar documents")

    def template_attrs(self, entity):
        attrs = super(RecentDataPrimaryView, self).template_attrs(entity)
        attrs["data_url"] = self._cw.data_url("/").rstrip("/")
        main_attrs = self.main_attrs(entity)
        recents = []
        from cubicweb_francearchives.utils import remove_html_tags, title_for_link

        for related in self.related_content(entity):
            related = related.cw_adapt_to("ITemplatable").entity_param()
            title = related.title
            recents.append(
                {
                    "url": related.absolute_url(),
                    "title": title,
                    "plain_title": remove_html_tags(title),
                    "header": related.abstract,
                    "link_title": title_for_link(self._cw, title),
                    "etype": self._cw._(getattr(related, "etype", related.cw_etype)),
                    "dates": self.entity_date(related),
                    "image": related.image,
                    "default_picto_srcs": self._cw.uiprops["DOCUMENT_IMG"],
                }
            )
        if recents:
            attrs["entities"] = recents
        attrs.update(main_attrs)
        attrs["sharelinks_data"] = self.sharelinks(entity)
        attrs["metadata"] = self.metadata(entity)
        return attrs

    def metadata(self, entity):
        metadata = (("Date", self.entity_date(entity)),)
        return [entry for entry in metadata if entry[-1]]

    def main_attrs(self, entity):
        _ = self._cw._
        return {
            "_": _,
            "default_picto_src": self._cw.uiprops["DOCUMENT_IMG"],
            "images": self.entity_images(entity),
            "recent_label": _(self.recent_label),
            "all_links": {
                "url": self._cw.build_url(self.all_link_url),
                "label": _(self.all_link_label),
            },
        }

    def entity_date(self, entity):
        return entity.dates

    def related_content(self, entity):
        # if entity has an explicit relation towards related_content_suggestion
        # send the objects of this relation
        if entity.related_content_suggestion:
            related_content = entity.related_content_suggestion
            if len(related_content) >= 3:
                return related_content[0:3]
            else:
                return related_content

        # else if this entity is the object of a relation_content_suggestion
        # send the subjects of these relations
        if entity.reverse_related_content_suggestion:
            related_content = entity.reverse_related_content_suggestion
            if len(related_content) >= 3:
                return related_content[0:3]
            else:
                return related_content

        related_subjects = self._cw.execute(
            "Any A WHERE X eid %(eid)s, X related_authority A, A is SubjectAuthority",
            {"eid": entity.eid},
        ).rows
        # else if this entity has no subject, return no related content
        if len(related_subjects) == 0:
            return []

        # else, retrieve automatic suggestions only if entity has subjects
        # Query more like this based on authority eid
        es = get_connection(self._cw.vreg.config)
        if not es:
            self._cw.error("[related_content]: no elastisearch connection available")
            return []
        index_name = self._cw.vreg.config["index-name"]
        search = Search(index="{}_all".format(index_name))

        # "must" condition to ensure that related content are of the right types
        related_content_etypes = [
            "BaseContent",
            "ExternRef",
            "CommemorationItem",
        ]
        etypes_clauses = []
        for etype in related_content_etypes:
            etypes_clauses.append(Q("term", estype=etype))
        must_etypes = Bool(should=etypes_clauses, minimum_should_match=1)

        # "should" condition to select similar entities based on subjects indexes
        should = []
        for subject in related_subjects:
            should.append(Q({"term": {"index_entries.authority": subject[0]}}))
        # do not include same document in results
        same_document = [Q("term", eid=entity.eid)]
        search.query = Bool(should=should, minimum_should_match=1)
        search = search.filter(Bool(must=must_etypes, must_not=same_document))
        search = search[0:3]
        search = search.source(["eid"])  # only return eids

        response = search.execute()
        related_content = []
        for hit in response:
            try:
                related = self._cw.entity_from_eid(hit["eid"])
            except Exception:
                self._cw.error(f'[related_content]: entity {hit["eid"]} not found')
                continue
            related_content.append(related)

        return related_content


class RelatedAutorityIndexablePrimaryMixIn:
    def authority_props(self, entity):
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
        return [entry for entry in main_props if entry[-1]]


class BaseContentPrimaryView(FaqMixin, RelatedAutorityIndexablePrimaryMixIn, RecentDataPrimaryView):
    __select__ = RecentDataPrimaryView.__select__ & is_instance("BaseContent")
    all_link_url = "articles"
    all_link_label = _("See all articles")

    def main_props(self, entity):
        main_props = self.authority_props(entity)
        service = entity.basecontent_service
        if service:
            main_props.insert(
                0, (self._cw._("service_label"), ", ".join(e.view("incontext") for e in service))
            )
        return main_props

    def entity_call(self, entity):
        self._cw.add_js("bundle-pnia-toc.js")
        super(BaseContentPrimaryView, self).entity_call(entity)

    @cachedproperty
    def faq_category(self):
        entity = self.cw_rset.complete_entity(self.cw_row or 0, self.cw_col or 0)
        return entity.cw_adapt_to("IFaq").faq_category

    def template_attrs(self, entity):
        """Build the dictionary for the jinja template by
        merging all required data from the BaseContent entity"""
        attrs = super(BaseContentPrimaryView, self).template_attrs(entity)
        attrs.update(
            {
                "faqs": self.faqs_attrs(),
                "main_props": self.main_props(entity),
                "i18n_links": entity.i18n_links(),
            }
        )
        return attrs

    def entity_images(self, entity):
        return entity.basecontent_image


class NewsContentPrimaryView(RecentDataPrimaryView):
    __select__ = RecentDataPrimaryView.__select__ & is_instance("NewsContent")
    all_link_url = "actualites"
    all_link_label = _("See all news")
    recent_label = _("###Recent News###")

    def related_content(self, entity):
        return self._cw.execute(
            """Any X ORDERBY X DESC LIMIT 3
               WHERE X is NewsContent,
               NOT X identity S, S eid %(e)s""",
            {"e": entity.eid},
        ).entities()

    def entity_images(self, entity):
        return entity.news_image

    def entity_date(self, entity):
        return entity.dates or format_date(entity.modification_date, self._cw, fmt="d MMMM y")


class CommemorationItemPrimaryView(RelatedAutorityIndexablePrimaryMixIn, RecentDataPrimaryView):
    __select__ = ContentPrimaryView.__select__ & is_instance("CommemorationItem")
    all_link_url = "pages_histoire"
    all_link_label = _("See all commemorations")

    def main_props(self, entity):
        main_props = self.authority_props(entity)
        return main_props

    def entity_call(self, entity):
        self._cw.add_js("bundle-pnia-toc.js")
        super(CommemorationItemPrimaryView, self).entity_call(entity)

    def template_attrs(self, entity):
        attrs = super(CommemorationItemPrimaryView, self).template_attrs(entity)
        attrs.update(
            {
                "main_props": self.main_props(entity),
                "default_picto_src": self._cw.uiprops["DOCUMENT_IMG"],
            }
        )
        return attrs

    def metadata(self, entity):
        metadata = super(CommemorationItemPrimaryView, self).metadata(entity)
        authors = self.authors(entity)
        if authors:
            metadata.append(authors)
        return metadata

    def authors(self, entity):
        _ = self._cw._
        authors = entity.cw_adapt_to("IMeta").author()
        if authors:
            title = _("Text author") if len(authors) == 1 else _("Text authors")
            data = _("###list_separator###").join(authors)
            return (title, data)

    def entity_images(self, entity):
        return entity.commemoration_image


class AuthorityRecordPrimaryView(FaqMixin, ShareLinksMixin, ContentPrimaryView):
    __select__ = ContentPrimaryView.__select__ & is_instance("AuthorityRecord")
    need_css = ("css/font-awsome.css",)
    needs_js = ("cubes.pnia_sharelinks.js",)
    template = get_template("authorityrecord.jinja2")
    faq_category = "06_faq_eac"

    def metadata(self, entity):
        if entity.main_date:
            return (("Date", entity.main_date),)
        return ()

    def template_attrs(self, entity):
        """Build the dictionary for the jinja template by
        merging all required data from the AuthorithyRecord entity"""
        attrs = super(AuthorityRecordPrimaryView, self).template_attrs(entity)
        attrs.update(
            {
                "_": self._cw._,
                "faqs": self.faqs_attrs(),
                "main_props": [],
                "metadata": self.metadata(entity),
                "rdf_formats": [
                    (f"{entity.absolute_url()}/rdf.{extension}", name)
                    for extension, name in RDF_FORMAT_EXTENSIONS.items()
                ],
            }
        )
        adapter = entity.cw_adapt_to("entity.main_props")
        attrs["main_props"] = adapter.properties()
        if entity.related_service:
            attrs.update({"publisher": entity.cw_adapt_to("IPublisherInfo").serialize()})
        attrs["csv_props"] = adapter.csv_export_props()
        attrs["sharelinks_data"] = self.sharelinks(entity)
        return attrs


class FindingAidPrimaryView(FaqMixin, ShareLinksMixin, SiteTourMixin, ContentPrimaryView):
    __select__ = ContentPrimaryView.__select__ & is_instance("FindingAid", "FAComponent")
    needs_css = ("css/font-awesome.css",)
    needs_js = ("cubes.pnia_sharelinks.js",)

    template = get_template("findingaid.jinja2")
    faq_category = "03_faq_ir"

    def render_content(self, entity):
        self.call_template(**self.template_attrs(entity))
        self.content_navigation_components("related-top-main-content")
        attrs = {"sharelinks": self.sharelinks(entity), "css_class": "fi", "_": self._cw._}
        self.w(get_template("sharelinks.jinja2").render(attrs))

    def template_attrs(self, entity):
        attrs = super(FindingAidPrimaryView, self).template_attrs(entity)
        adapter = entity.cw_adapt_to("entity.main_props")
        service = entity.related_service
        default_picto_src = [self._cw.uiprops["DIGITIZED_IMG"]]
        if service and service.illustration_url:
            default_picto_src.append(service.illustration_url)
        digitized_urls = adapter.digitized_urls()
        illustation_src = entity.illustration_url
        if not illustation_src and digitized_urls:
            illustation_src = self._cw.uiprops["DIGITIZED_IMG"]
        attrs.update(
            {
                "publisher": entity.cw_adapt_to("IPublisherInfo").serialize(),
                "date": adapter.formatted_dates,
                "title": adapter.shortened_title(),
                "main_props": adapter.properties(),
                "indexes_props": adapter.indexes(),
                "illustation_src": illustation_src,
                "default_picto_src": ";".join(default_picto_src),
                "faqs": self.faqs_attrs(),
                "cms": self._cw.vreg.config.get("instance-type") == "cms",
                "_": self._cw._,
                "csv_props": adapter.csv_export_props(),
                "site_tour_url": self._cw.build_url(f"{entity.cw_etype.lower()}-tour.json"),
                "iiif_manifest": entity.iiif_manifest,
                "data_url": self._cw.datadir_url,
                "lang": self._cw.lang,
                "rdf_formats": [
                    (f"{entity.absolute_url()}/rdf.{extension}", name)
                    for extension, name in RDF_FORMAT_EXTENSIONS.items()
                ],
            }
        )
        inventory_source = adapter.inventory_source()
        if inventory_source:
            attrs["inventory_source"] = inventory_source
        if digitized_urls:
            attrs["digitized_urls"] = digitized_urls
        return attrs


class MapPrimaryView(PrimaryView):
    __select__ = PrimaryView.__select__ & is_instance("Map")
    template = get_template("map-page.jinja2")
    needs_js = ("bundle-glossary.js",)

    def entity_call(self, entity):
        legends, options = {}, {"urls": {}, "colors": {}}
        items = defaultdict(list)
        services = list(all_services(self._cw))
        services_map = OrderedDict([(s.dpt_code.lower(), s.name) for s in services])
        for v in entity.data():
            url = v.get("url")
            if not url:
                continue
            if v["legend"]:
                legend = v["legend"]
                if legend.lower() == "legende":
                    continue
                items[v["color"]].append((services_map.get(v["code"], url), url))
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


class CircularPrimaryView(FaqMixin, ContentPrimaryView):
    __select__ = ContentPrimaryView.__select__ & is_instance("Circular")
    needs_css = ("css/font-awesome.css",)
    template = get_template("circular.jinja2")
    faq_category = "04_faq_circular"

    def get_related_cirular(self, circ_id):
        if circ_id:
            rset = self._cw.execute("Any X WHERE X is Circular, X circ_id %(c)s", {"c": circ_id})
            if rset:
                return rset.one().view("incontext")
        return circ_id

    def metadata(self, entity):
        if entity.signing_date:
            return (("Date", format_date(entity.signing_date, self._cw)),)
        return ()

    def template_attrs(self, entity):
        attrs = super(CircularPrimaryView, self).template_attrs(entity)
        _ = self._cw._
        attrs.update({"_": _, "faqs": self.faqs_attrs(), "metadata": self.metadata(entity)})
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
        date = circular.sortdate()
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


class UrLBasedAttributeView(URLAttributeView):
    """open the url in a new tab"""

    __select__ = URLAttributeView.__select__ & is_instance("ExternRef", "Link", "ExternalUri")

    def entity_call(self, entity, rtype="subject", **kwargs):
        url = entity.printable_value(rtype)
        if url:
            self.w(exturl_link(self._cw, url))


class IndexURLAttributeView(URLAttributeView):
    """open the url in a new tab"""

    __select__ = URLAttributeView.__select__ & is_instance(
        "Concept",
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


class ExternRefPrimaryMixIn(RelatedAutorityIndexablePrimaryMixIn):
    def main_props(self, entity):
        main_props = self.authority_props(entity)
        _ = self._cw._
        service = entity.exref_service
        if service:
            main_props.append((_("service_label"), ", ".join(e.view("incontext") for e in service)))
        return main_props


class ExternRefPrimaryView(ExternRefPrimaryMixIn, ContentPrimaryView):
    __select__ = (
        PrimaryView.__select__
        & is_instance("ExternRef")
        & ~score_entity(lambda e: is_virtual_exhibit(e))
    )
    template = get_template("externref.jinja2")

    def template_attrs(self, entity):
        attrs = super(ExternRefPrimaryView, self).template_attrs(entity)
        attrs["years"] = entity.dates
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

    def template_attrs(self, entity):
        attrs = super(VirtualExhibitExternRefPrimaryView, self).template_attrs(entity)
        attrs["main_props"] = self.main_props(entity)
        attrs["website_url"] = entity.url
        return attrs

    def entity_images(self, entity):
        return entity.externref_image


class NominaRecordPrimaryView(ContentPrimaryView):
    __regid__ = "primary"
    __select__ = ContentPrimaryView.__select__ & is_instance("NominaRecord")
    template = get_template("nominarecord.jinja2")

    def template_context(self):
        return {
            "nomina": True,
            "display_nomina_search": False,
        }

    def template_attrs(self, entity):
        attrs = super(NominaRecordPrimaryView, self).template_attrs(entity)
        adapter = entity.cw_adapt_to("entity.main_props")
        attrs.update(
            {
                "_": self._cw._,
                "main_props": adapter.properties(),
            }
        )
        attrs.update({"publisher": entity.cw_adapt_to("IPublisherInfo").serialize()})
        source_url = adapter.source_url()
        if source_url:
            attrs["source_url"] = source_url
        return attrs


class PniaCardPrimaryView(ContentPrimaryView):
    __select__ = ContentPrimaryView.__select__ & is_instance("Card")
    template = get_template("card.jinja2")

    def render_content(self, entity):
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
                if lang in ("fr", entity.language):
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
                    trad = self._cw._("no translation yet exists")
                trads.append((self._cw._(lang), trad))
        return trads

    def metadata(self, entity):
        return [(_("Language"), self._cw._(entity.language))]

    def main_props(self, entity):
        _ = self._cw._
        main_props = []
        original = entity.original_entity
        for attr in original.i18nfields:
            main_props.append((_(attr), entity.printable_value(attr)))
        return main_props

    def template_attrs(self, entity):
        attrs = super(PniaTranslationsPrimaryView, self).template_attrs(entity)
        original = entity.original_entity
        attrs.update(
            {
                "_": self._cw._,
                "editable": self.editable,
                "original": original.view("incontext"),
                "metadata": self.metadata(entity),
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
            faq_url = self._cw.build_url("faqitem/{}".format(eid))
            faqs[category].append((eid, faq_url, remove_html_tags(question), answer))
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


class SiteLinkPrimaryView(ContentPrimaryView):
    __select__ = ContentPrimaryView.__select__ & is_instance("SiteLink")
    template = get_template("sitelink.jinja2")

    def content_meta_props(self, entity):
        return None

    def main_props(self, entity):
        return []

    def template_attrs(self, entity):
        attrs = super(SiteLinkPrimaryView, self).template_attrs(entity)
        attrs["_"] = self._cw._
        attrs["content_meta"] = self.content_meta_props(entity)
        attrs["main_props"] = self.main_props(entity)
        return attrs


def registration_callback(vreg):
    vreg.register_all(list(globals().values()), __name__, (PniaDownloadView, PniaCardPrimaryView))
    vreg.register_and_replace(PniaDownloadView, DownloadView)
    vreg.register_and_replace(PniaCardPrimaryView, CardPrimaryView)
