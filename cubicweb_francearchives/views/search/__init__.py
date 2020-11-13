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
import math

from logilab.common.decorators import cachedproperty
from logilab.mtconverter import xml_escape

from elasticsearch.exceptions import ConnectionError, RequestError

from elasticsearch_dsl.response import Response

from pyramid.httpexceptions import HTTPSeeOther

from cubicweb_elasticsearch.views import ElasticSearchView

from cwtags import tag as T

from cubicweb import _
from cubicweb.predicates import is_instance, match_form_params
from cubicweb.schema import display_name
from cubicweb.uilib import cut
from cubicweb.rset import ResultSet
from cubicweb.web.views.baseviews import InContextView
from cubicweb.web.views.primary import PrimaryView

from cubes.skos.views import ConceptPrimaryView

from cubicweb_francearchives.entities import DOC_CATEGORY_ETYPES
from cubicweb_francearchives.views import get_template, rebuild_url, format_number, FaqMixin
from cubicweb_francearchives.views.search.facets import (
    FACETED_SEARCHES,
    PniaCWFacetedSearch,
    FACET_RENDERERS,
)

ETYPES_MAP = {
    "Virtual_exhibit": "ExternRef",
    "Blog": "ExternRef",
    "Other": "ExternRef",
    "Publication": "BaseContent",
}


class PniaElasticSearchView(FaqMixin, ElasticSearchView):
    no_term_msg = _("Contenu")
    title_count_templates = (_("No result"), _("1 result"), _("{count} results"))
    display_results_info = True
    template = get_template("searchlist.jinja2")
    document_categories = (
        ("", _("All documents")),
        ("archives", _("Archives")),
        ("circulars", _("Circulars")),
        ("edito", _("edito")),
        ("commemorations", _("Commemorations")),
        ("services", _("archive-services-label")),
    )
    faq_category = "02_faq_search"

    @cachedproperty
    def cached_search_response(self):
        query_string = self._cw.form.get("q", self._cw.form.get("search", ""))
        if hasattr(self, "_esresponse"):
            return self._esresponse, query_string
        # TODO - remove _cw.form.get('search') when URL transition is over
        self._esresponse = self.do_search(query_string)
        return self._esresponse, query_string

    def search_etype_label(self):
        _ = self._cw._
        etype = self._cw.form.get("es_cw_etype")
        bc_label = None
        if etype:
            if etype == "Service":
                bc_label = _("Service Directory")
            else:
                bc_label = display_name(self._cw, etype, "plural")
        return bc_label

    def search_title(self):
        _ = self._cw._
        try:
            response, query_string = self.cached_search_response
        except ConnectionError:
            response = None
        title = []
        form = self._cw.form
        search_term = form.get("q", form.get("fulltext_facet"))
        title.append(_("Search results"))
        if search_term:
            title.append(_('on term "%s"') % search_term)
        etype_label = self.search_etype_label()
        if etype_label:
            title.append(_('for "%s"') % etype_label)
        if not title:
            title.append(self._cw._(self.title))
        if response:
            number_of_pages = self.number_of_pages(response.hits.total.value)
            if number_of_pages:
                page = form.get("page", 1)
                title.append("[{}]".format(_("page %s on %s") % (page, number_of_pages)))
        title.append("({})".format(self._cw.property_value("ui.site-title")))
        return xml_escape(" ".join(title))

    def page_title(self):
        """returns a title according to the result set - used for the
        title in the HTML header. Add"""
        title = self.search_title()
        return "{} ({})".format(title, self._cw.property_value("ui.site-title"))

    def breadcrumbs(self):
        _ = self._cw._
        bc_label = self.search_etype_label()
        if not bc_label:
            bc_label = _("search-breadcrumb-label")
        return [
            (self._cw.build_url(""), _("Home")),
            # don't use dc_title() to avoid displaying wikiid
            (None, bc_label),
        ]

    @cachedproperty
    def xiti_chapters(self):
        req = self._cw
        query = req.form.get("q", req.relative_path(False).rstrip("/"))
        # handcrafted URLs can contain more than one "q" parameter. In that
        # case, pick the first one arbitrarily, it won't make sense anyway
        if isinstance(query, list):
            query = query[0]
        chapters = ["Search", query]
        if req.form.get("es_publisher"):
            publisher = req.form["es_publisher"]
            if isinstance(publisher, list):
                publisher = publisher[0]
            chapters.append(publisher)
        return chapters

    def template_context(self):
        return {
            "heroimages": False,
            "breadcrumbs": self.breadcrumbs(),
            "meta": [("robots", "noindex")],
            "faqs": self.faqs_attrs(),
        }

    def format_results_title(self, response):
        count = response.hits.total.value if response is not None else 0
        if count == 0:
            tmpl = self.title_count_templates[0]
        elif count == 1:
            tmpl = self.title_count_templates[1]
        else:
            tmpl = self.title_count_templates[2]
        return self._cw._(tmpl).format(count=format_number(count, self._cw))

    def call(self, context=None, **kwargs):
        self._cw.add_css("css/font-awesome.css")
        try:
            response, query_string = self.cached_search_response
        except ConnectionError:
            self.w(
                T.div(
                    self._cw._("failed to connect to elasticsearch"),
                    Class="alert alert-info",
                    role="alert",
                )
            )
            return
        except RequestError:
            self.exception("ES search failed")
            self.w(
                T.div(
                    self._cw._("there was a problem with the elasticsearch request"),
                    Class="alert alert-info",
                    role="alert",
                )
            )
            return
        except KeyError:
            self.exception(
                "Key error on do_search "
                "(probably some query params are not consistent "
                "with selected `FACETED_SEARCHES`)"
            )
            response = Response({"hits": {"hits": [], "total": 0}, "facets": {}})
            query_string = self._cw.form.get("q", self._cw.form.get("search", ""))
            self._cw.form["fuzzy"] = True
        if len(response) == 0 and "fuzzy" not in self._cw.form:
            msg = self._cw._(
                "You search did not find any results, "
                "the search has been made with fuzzy options for more results."
            )
            url_params = self._cw.form.copy()
            url_params["fuzzy"] = True
            if "indexentry" in self._cw.form:
                del url_params["indexentry"]
            url_params["__message"] = msg
            raise HTTPSeeOther(location=self._cw.build_url(**url_params))

        fulltext_params = self._cw.form.copy()
        fulltext_value = fulltext_params.pop("fulltext_facet", "")
        fulltext_params.pop("page", None)
        extra_link = {}
        if len(response) <= 6 and "fuzzy" not in self._cw.form:
            url_params = self._cw.form.copy()
            url_params["fuzzy"] = True
            extra_link = {
                "href": self._cw.build_url(**url_params),
                "title": self._cw._("fuzzy search activation"),
                "text": self._cw._("For more results, try a fuzzy search"),
            }
        self.w(
            self.template.render(
                req=self._cw,
                _=self._cw._,
                response=response,
                results_title=self.format_results_title(response),
                query_string=query_string,
                document_category_facets=self.build_document_category_facets(response, context),
                fulltext_form_action=self._cw.build_url(
                    self._cw.relative_path(includeparams=False)
                ),
                fulltext_params=fulltext_params,
                fulltext_value=fulltext_value,
                facets=self.build_facets(response, context),
                search_title=self._cw._(self.no_term_msg),
                search_results=self.build_results(response),
                pagination=self.pagination(response.hits.total.value),
                restrict_to_single_etype=self._cw.form.get("restrict_to_single_etype", False),
                extra_link=extra_link,
            )
        )

    def build_document_category_facets(self, response, context):
        if response is None or len(response) == 0:
            return ()
        category_facet = response.facets.escategory
        counts_by_etype = {etype: count for etype, count, __ in category_facet}
        # NOTE: fallback on 'all' category if es_escategory query paremeter is
        # None or empty
        counts_by_etype[""] = response.aggregations._filter_escategory.doc_count
        document_category_facets = []
        for escategory, facet_label in self.document_categories:
            facet_url = rebuild_url(self._cw, es_escategory=escategory or None, page=None, vid=None)
            document_category_facets.append(
                {
                    "category": escategory or "all",
                    "selected": self._cw.form.get("es_escategory", "") == escategory,
                    "count": counts_by_etype.get(escategory, 0),
                    "label": self._cw._(facet_label),
                    "url": facet_url,
                }
            )
        return document_category_facets

    def rset_from_response(self, response):
        """transform an ES response into a CubicWeb rset

        This consists in iterating on current panigated response and
        inspect the ``cw_etype`` and ``eid`` document fields.

        NOTE: some etypes used for the ES indexation are not part of the
        actual CubicWeb schema and therefore require to be mapped on a
        valid entity type (e.g. ExternRef's reftypes)
        """
        req = self._cw
        descr, rows = [], []
        for idx, result in enumerate(response):
            # safety belt, in v0.6.0, PDF are indexed without a cw_etype field
            cw_etype = getattr(result, "cw_etype", "FindingAid")
            # safety belt for import-ead with esonly=True: in that case,
            # ES documents don't have eids
            if not result.eid:
                ir_rset = self._cw.execute(
                    "Any X WHERE X is {}, X stable_id %(s)s".format(cw_etype),
                    {"s": result.stable_id},
                )
                if ir_rset:
                    eid = ir_rset[0][0]
                else:
                    continue
            else:
                eid = result.eid
            descr.append((ETYPES_MAP.get(cw_etype, cw_etype), "String"))
            if hasattr(result, "stable_id"):
                rows.append([eid, result.stable_id])
            else:
                rows.append([eid, "foo"])
        rset = ResultSet(rows, "Any X", description=descr)
        rset.req = req
        return rset

    def build_results(self, response):
        rset = self.rset_from_response(response)
        if not rset:
            return []
        results = []
        for entity, item_response in zip(rset.entities(), response):
            try:
                entity.complete()
            except Exception:
                self.exception(
                    "failed to build entity with eid %s (ES says etype is %s)",
                    entity.eid,
                    getattr(item_response, "cw_etype", "?FindingAid?"),
                )
                continue
            results.append(entity.view("pniasearch-item", es_response=item_response))
        return results

    def number_of_pages(self, number_of_items=10, items_per_page=10, max_pages=1000):
        number_of_pages = int(math.ceil(number_of_items / float(items_per_page)))
        return min(number_of_pages, max_pages)

    # FIXME: where does 10 come from?!
    # pagination should expect "number_of_pages", not "items_per_page"
    def pagination(
        self, number_of_items, items_per_page=10, max_pages=1000, max_pagination_links=6
    ):
        """
        Pagination structure generation
        """
        pagination = []
        if number_of_items <= items_per_page:
            return pagination

        url_params = self._cw.form.copy()
        try:
            current_page = int(url_params.get("page", 1))
        except ValueError:
            current_page = 1

        number_of_pages = self.number_of_pages(
            number_of_items, items_per_page=items_per_page, max_pages=max_pages
        )
        if current_page < 1 or current_page > number_of_pages:
            return pagination

        text_previous = " &lt; "
        text_next = " &gt; "
        text_spacer = " &middot; " * 3
        _ = self._cw._
        # Link to previous page
        if current_page > 1:
            url_params["page"] = current_page - 1
            pagination.append(
                {
                    "name": text_previous,
                    "hidden_label": _("Previous page"),
                    "link": xml_escape(self._cw.build_url(**url_params)),
                    "title": xml_escape(_("Go to previous the page")),
                }
            )

        # Substract 2 because we will always display first and last
        pages_to_show = self.get_pagination_range(
            current_page, number_of_pages, max_pagination_links - 2
        )
        if len(pages_to_show) == 0:
            return pagination

        # Get rid of the first page (1) and the last page as they will
        # always be shown
        if pages_to_show[0] == 1:
            pages_to_show.pop(0)
            # After removing one from the start, add one to the end?
            if len(pages_to_show) != 0 and pages_to_show[-1] < number_of_pages - 1:
                pages_to_show.append(pages_to_show[-1] + 1)
        if pages_to_show[-1] == number_of_pages:
            pages_to_show.pop()
            # After removing one from the end, add one to the start?
            if len(pages_to_show) != 0 and pages_to_show[0] > 2:
                pages_to_show.insert(0, pages_to_show[0] - 1)

        # Always show link to first page
        pagination.append(self.page_link(url_params, 1, current_page))

        # Add spacer
        if len(pages_to_show) == 0:
            pass
        elif pages_to_show[0] == 3:
            pagination.append(self.page_link(url_params, 2, current_page))
        elif pages_to_show[0] > 3:
            pagination.append({"name": text_spacer})

        # Links to pages
        for page_number in pages_to_show:
            pagination.append(self.page_link(url_params, page_number, current_page))

        # Add spacer after
        if len(pages_to_show) == 0:
            pass
        elif pages_to_show[-1] == number_of_pages - 2:
            pagination.append(self.page_link(url_params, number_of_pages - 1, current_page))
        elif pages_to_show[-1] < number_of_pages - 1:
            pagination.append({"name": text_spacer})

        # Always show link to last page
        pagination.append(self.page_link(url_params, number_of_pages, current_page))

        # Link to next page
        if current_page < number_of_pages:
            url_params["page"] = current_page + 1
            pagination.append(
                {
                    "name": text_next,
                    "hidden_label": _("Next page"),
                    "link": xml_escape(self._cw.build_url(**url_params)),
                    "title": xml_escape(_("Go to the next page")),
                }
            )

        return pagination

    def get_pagination_range(self, current_page, number_of_pages, window):
        """
        Return the range of pages to show
        """
        # Fix abberant current_page
        if current_page < 1:
            current_page = 1
        if current_page > number_of_pages:
            current_page = number_of_pages

        # Fix abberant window
        if window > number_of_pages:
            window = number_of_pages

        pages = [current_page]
        previous_length = 0

        while True:
            # If page list does not grow anymore or has reached maximum size
            if len(pages) == previous_length or len(pages) >= window:
                return pages

            previous_length = len(pages)

            if pages[0] > 1:
                pages.insert(0, pages[0] - 1)

            if len(pages) >= window:
                return pages

            if pages[-1] < number_of_pages:
                pages.append(pages[-1] + 1)

    def page_link(self, url_params, page, current_page):
        """
        Return info on a given page number
        """
        url_params["page"] = page
        url = self._cw.build_url(**url_params)
        page_link = {
            "name": page,
            "link": xml_escape(url),
            "title": xml_escape("{} {}".format(self._cw._("Go to the page"), page)),
        }
        if page == current_page:
            page_link["current"] = True
        return page_link

    def customize_search(self, query_string, facet_selections, start=0, stop=10, **kwargs):
        """
        Customized search with :

        * cote:unittid
        """
        if query_string.startswith("cote:"):
            query_string = query_string.split(":")[1]
            facet_selections["unitid"] = query_string
        doc_types = ["_doc"]
        # use .get() instead of "key in" to ensure we have a non-empty value
        if facet_selections.get("cw_etype"):
            etype = facet_selections["cw_etype"]
            search_class = FACETED_SEARCHES.get(etype.lower(), PniaCWFacetedSearch)
        elif facet_selections.get("escategory"):
            category = facet_selections.get("escategory")
            # if category corresponds to a single etype and if this etype
            # has a specific facet definition, use it
            if category in DOC_CATEGORY_ETYPES and len(DOC_CATEGORY_ETYPES[category]) == 1:
                etype = DOC_CATEGORY_ETYPES[category][0]
                search_class = FACETED_SEARCHES.get(etype.lower(), PniaCWFacetedSearch)
            else:
                search_class = PniaCWFacetedSearch
        else:
            search_class = PniaCWFacetedSearch
        if "indexentry" in self._cw.form:
            search_class = FACETED_SEARCHES.get("indexentry")
        default_index_name = "{}_all".format(self._cw.vreg.config.get("index-name"))
        # remove selected items not available in facet eg : select FAComponent,
        # then select digitized, then deselected FAComponent digitized is then
        # not available anymore - should that deselect not be shown ?  should
        # the deselect link take that into account and remove that item from the
        # url_params ? (more difficult) - this avoids having a confusing param
        # in URL
        for facet_searched in list(facet_selections.keys()):
            if facet_searched not in list(search_class.facets.keys()):
                del facet_selections[facet_searched]
        kwargs["fulltext_facet"] = self._cw.form.get("fulltext_facet")
        return search_class(
            query_string,
            facet_selections,
            doc_types=doc_types,
            index=default_index_name,
            form=self._cw.form,
            **kwargs
        )[start:stop]

    def build_facets(self, response, context):
        """
        Generate HTML for facets
        """
        req = self._cw
        facets = []
        hide_cw_facet = self._cw.form.get("restrict_to_single_etype", False)
        for facetid, facetlabel in self.facets_to_display:
            if facetid == "cw_etype" and hide_cw_facet:
                continue
            # response.facets is an instance of AttrDict
            facet = getattr(response.facets, facetid, ())
            if len(facet) == 0:
                continue
            facet_render = FACET_RENDERERS.get(facetid) or FACET_RENDERERS["default"]
            facet_html = facet_render(req, facet, facetid, facetlabel, context)
            if facet_html:
                facets.append(facet_html)
        return facets

    def customize_infos(self, infos):
        """
        This is where one can customize the infos being displayed

        For example : set the title according to your rules and data set
        """
        infos.setdefault(
            "title", infos.get("name", infos.get("reference", infos.get("unittitle", "n/a")))
        )

    @property
    def facets_to_display(self):
        """
        Method to list facets to display (can be customized)
        """
        _ = self._cw._
        return (
            ("publisher", _("publishers_facet")),
            ("cw_etype", _("document_type_facet")),
            ("digitized", _("digitized_facet")),
            ("originators", _("originators_facet")),
            ("status", _("status_facet")),
            ("ancestors", _("ancestors_facet")),
            ("year", _("time_period_facet")),
            ("level", _("service_level_facet")),
        )


class PniaElasticSearchWithContextView(PniaElasticSearchView):
    __abstract__ = True

    def display_contextual_info(self):
        w, _ = self.w, self._cw._
        with T.div(w, id="section-article-header"):
            w(T.h2(_("contexte de le recherche"), Class="sr-title"))
            for info in self.get_infos():
                with T.div(w, Class="documents-fonds"):
                    w(info)

    def call(self, **kwargs):
        self.display_contextual_info()
        super(PniaElasticSearchWithContextView, self).call(**kwargs)


circular_facet_active = match_form_params(es_escategory="circulars") | match_form_params(
    es_cw_etype="Circular"
)

service_facet_active = match_form_params(es_escategory="services") | match_form_params(
    es_cw_etype="Service"
)


class SearchCmsChildrenView(PniaElasticSearchWithContextView):
    __select__ = (
        PniaElasticSearchView.__select__
        & match_form_params("ancestors")
        & ~circular_facet_active
        & ~service_facet_active
    )
    display_results_info = False
    title_count_templates = (
        _("No documents in this section"),
        _("1 document in this section"),
        _("{count} documents in this section"),
    )

    def write_content(self, entity):
        self.w(entity.printable_value("content"))
        children = self._cw.execute(
            "Any Y, T ORDERBY O WHERE X children Y,  Y is Section, "
            "EXISTS(Y children Z), Y title T, Y order O, "
            "X eid %(e)s",
            {"e": entity.eid},
        )
        if children:
            with (T.nav(self.w, Class="section-context__list", role="navigation")):
                with T.ul(self.w):
                    for c in children.entities():
                        self.w(T.li(c.view("outofcontext")))

    def display_contextual_info(self):
        w = self.w
        entity = self._cw.find("Section", eid=self._cw.form["ancestors"]).one()
        with T.div(w, Class="section-context"):
            entity = entity.cw_adapt_to("ITemplatable").entity_param()
            with T.h1(self.w):
                self.w(T.span(entity.title, Class="section-title"))
                subtitle = entity.printable_value("subtitle")
                if subtitle:
                    self.w(T.span(subtitle, Class="section-subtitle"))
            image = entity.image
            if image:
                with T.div(w, Class="row"):
                    src = image.image_file[0].cw_adapt_to("IDownloadable").download_url()
                    with T.div(w, Class="col-sm-4"):
                        w(T.img(Class="img-responsive thumbnail", src=src, alt=image.alt))
                    with T.div(w, Class="col-sm-8"):
                        self.write_content(entity)
            else:
                self.write_content(entity)

    def customize_search(self, query_string, facet_selections, start=0, stop=10, **kwargs):
        req = self._cw
        query_string = req.form.pop("ancestors")
        etype = facet_selections.get("cw_etype", "section")
        search_class = FACETED_SEARCHES.get(etype.lower(), PniaCWFacetedSearch)
        default_index_name = "{}_all".format(self._cw.vreg.config.get("index-name"))
        kwargs["ancestors-query"] = True
        kwargs["fulltext_facet"] = req.form.get("fulltext_facet")
        return search_class(
            query_string,
            facet_selections,
            doc_types=["_doc"],
            index=default_index_name,
            form=self._cw.form,
            **kwargs
        )[start:stop]


class PniaElasticSearchService(PniaElasticSearchView):
    __select__ = PniaElasticSearchView.__select__ & service_facet_active

    @property
    def facets_to_display(self):
        _ = self._cw._
        return (("level", _("service_level_facet")),)


class PniaElasticSearchCirculaires(PniaElasticSearchView):
    __select__ = PniaElasticSearchView.__select__ & circular_facet_active
    title_count_templates = (_("No result"), _("1 circulaire"), _("{count} circulaires"))
    template = get_template("searchlist-circular.jinja2")

    @property
    def facets_to_display(self):
        _ = self._cw._
        return (
            ("status", _("status")),
            ("business_field", _("business_field_facet")),
            ("siaf_daf_signing_year", _("siaf_daf_signing_year")),
            ("archival_field", _("archival_field_facet")),
            ("historical_context", _("historical_context")),
            ("action", _("action")),
        )


class PniaConceptPrimaryView(PniaElasticSearchCirculaires):
    __regid__ = "primary"
    __select__ = PrimaryView.__select__ & is_instance("Concept")
    title_count_templates = (_("No result"), _("1 circulaire"), _("{count} circulaires"))

    def call(self, **kwargs):
        self.display_contextual_info()
        super(PniaConceptPrimaryView, self).call(**kwargs)

    def display_contextual_info(self):
        w = self.w
        entity = self.cw_rset.get_entity(0, 0)
        with T.div(w, Class="section-context"):
            w(T.h1(entity.dc_title()))

    def customize_search(self, query_string, facet_selections, start=0, stop=10, **kwargs):
        entity = self.cw_rset.get_entity(0, 0)
        req = self._cw
        search_class = FACETED_SEARCHES.get("circular", PniaCWFacetedSearch)
        default_index_name = "{}_all".format(self._cw.vreg.config.get("index-name"))
        kwargs["fulltext_facet"] = req.form.get("fulltext_facet")
        req.form["restrict_to_single_etype"] = True
        title = entity.dc_title()
        for facet_field in ("business_field", "historical_context", "action"):
            if facet_field not in facet_selections:
                if entity.related(facet_field, role="object"):
                    facet_selections[facet_field] = title
        return search_class(
            query_string,
            facet_selections,
            doc_types=["_doc"],  # XXX
            index=default_index_name,
            **kwargs
        )[start:stop]


class FAInContextView(InContextView):
    __regid__ = "incontext"
    __select__ = InContextView.__select__ & is_instance("FindingAid", "FAComponent")

    max_title_size = 140

    def cell_call(self, row, col, es_response=None, **kwargs):
        entity = self.cw_rset.get_entity(row, col)
        full_title = entity.dc_title()
        cut_title = cut(full_title, self.max_title_size)
        self.es_response = es_response if es_response else None
        if cut_title != full_title:
            self.w(
                '<a href="%s" title="%s">%s</a>'
                % (xml_escape(entity.absolute_url()), xml_escape(full_title), xml_escape(cut_title))
            )
        else:
            self.w(
                '<a href="%s">%s</a>' % (xml_escape(entity.absolute_url()), xml_escape(cut_title))
            )


class ServiceInContextView(InContextView):
    __select__ = InContextView.__select__ & is_instance("Service")

    def cell_call(self, row, col, es_response=None, **kwargs):
        entity = self.cw_rset.get_entity(row, col)
        self.w(
            "<a href={}>{}</a>".format(xml_escape(entity.url_anchor), xml_escape(entity.dc_title()))
        )


def registration_callback(vreg):
    components = (
        (PniaElasticSearchView, ElasticSearchView),
        (PniaConceptPrimaryView, ConceptPrimaryView),
    )
    vreg.register_all(list(globals().values()), __name__, [new for (new, old) in components])
    for new, old in components:
        vreg.register_and_replace(new, old)
