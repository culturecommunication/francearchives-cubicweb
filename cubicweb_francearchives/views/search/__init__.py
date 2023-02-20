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
from elasticsearch_dsl.search import Search

from cubicweb_elasticsearch.views import ElasticSearchView
from cubicweb_elasticsearch.search_helpers import is_simple_query_string

from cwtags import tag as T

from cubicweb import _, NoResultError
from cubicweb.predicates import is_instance, match_form_params
from cubicweb.schema import display_name
from cubicweb.uilib import cut
from cubicweb.rset import ResultSet
from cubicweb.web.views.baseviews import InContextView
from cubicweb.web.views.primary import PrimaryView

from cubicweb_skos.views import ConceptPrimaryView

from cubicweb_francearchives.entities import DOC_CATEGORY_ETYPES
from cubicweb_francearchives.views import get_template, rebuild_url, format_number, FaqMixin
from cubicweb_francearchives.views.search.facets import (
    FACETED_SEARCHES,
    PniaCWFacetedSearch,
    FACET_RENDERERS,
)
from cubicweb_francearchives.utils import reveal_glossary

ETYPES_MAP = {
    "Virtual_exhibit": "ExternRef",
    "Blog": "ExternRef",
    "Other": "ExternRef",
    "Publication": "BaseContent",
    "SearchHelp": "BaseContent",
    "Article": "BaseContent",
}


class FakeResponse(Response):
    def __init__(self):
        response = {"hits": {"hits": [], "total": {"value": 0, "relation": ""}}, "facets": {}}
        super(FakeResponse, self).__init__(Search(), response)


class PaginationMixin:
    items_per_page_options = [10, 25, 50]
    default_items_per_page = 10

    def items_per_page_links(self):
        """
        Returns links with the items_per_page and their label
        """
        url_params = {}
        current_items_per_page = int(
            self._cw.form.get("items_per_page", self.default_items_per_page)
        )

        links = []
        for value in self.items_per_page_options:
            if value != self.default_items_per_page:
                url_params["items_per_page"] = value
            else:
                url_params["items_per_page"] = None
            links.append(
                {"label": value, "url": rebuild_url(self._cw, replace_keys=True, **url_params)}
            )

        return {"current_label": current_items_per_page, "options_links": links}

    def page_number_params(self):
        """
        Returns a set of arguments for the page number input form
        """
        page_number_params = self._cw.form.copy()
        page_number_params.pop("page", None)
        for key, value in page_number_params.items():
            if not isinstance(value, (tuple, list)):
                page_number_params[key] = [value]
        return page_number_params

    def number_of_pages(self, number_of_items):
        url_params = self._cw.form.copy()
        items_per_page = int(url_params.get("items_per_page", self.default_items_per_page))
        number_of_pages = int(math.ceil(number_of_items / float(items_per_page)))
        max_pages = int(math.ceil(10000 / float(items_per_page)))  # elasticsearch limit
        return min(number_of_pages, max_pages)

    @cachedproperty
    def get_current_page(self):
        try:
            return int(self._cw.form.get("page", 1))
        except ValueError:
            return 1

    # pagination should expect "number_of_pages", not "items_per_page"
    def pagination(self, number_of_items, max_pagination_links=5):
        """
        return links to first, previous, next and last page
        """
        pagination_first_previous = []
        pagination_next_last = []

        url_params = self._cw.form.copy()

        # 10 is the default items_per_page value in the elasticsearch cube
        items_per_page = int(url_params.get("items_per_page", self.default_items_per_page))

        if number_of_items <= items_per_page:
            return pagination_first_previous, pagination_next_last

        current_page = self.get_current_page
        number_of_pages = self.number_of_pages(number_of_items)
        if current_page < 1 or current_page > number_of_pages:
            return pagination_first_previous, pagination_next_last

        text_previous = " &lt; "
        text_next = " &gt; "
        text_first = " &lt;&lt; "
        text_last = " &gt;&gt; "

        _ = self._cw._
        # Link to first and previous page
        if current_page > 1:
            url_params["page"] = 1
            pagination_first_previous.append(
                {
                    "name": text_first,
                    "hidden_label": _("First page"),
                    "link": xml_escape(self._cw.build_url(**url_params)),
                    "title": xml_escape(_("Go to the first page")),
                }
            )

            url_params["page"] = current_page - 1
            pagination_first_previous.append(
                {
                    "name": text_previous,
                    "hidden_label": _("Previous page"),
                    "link": xml_escape(self._cw.build_url(**url_params)),
                    "title": xml_escape(_("Go to the previous page")),
                }
            )

        # Link to next and last page
        if current_page < number_of_pages:
            url_params["page"] = current_page + 1
            pagination_next_last.append(
                {
                    "name": text_next,
                    "hidden_label": _("Next page"),
                    "link": xml_escape(self._cw.build_url(**url_params)),
                    "title": xml_escape(_("Go to the next page")),
                }
            )

            url_params["page"] = number_of_pages
            pagination_next_last.append(
                {
                    "name": text_last,
                    "hidden_label": _("Last page"),
                    "link": xml_escape(self._cw.build_url(**url_params)),
                    "title": xml_escape(_("Go to the last page")),
                }
            )

        return pagination_first_previous, pagination_next_last


class PniaElasticSearchView(FaqMixin, PaginationMixin, ElasticSearchView):
    no_term_msg = _("Contenu")
    title_count_templates = (_("No result"), _("1 result"), _("{count} results"))
    display_results_info = True
    template = get_template("searchlist.jinja2")
    document_categories = (
        ("", _("All documents")),
        ("archives", _("###in archives###")),
        ("siteres", _("###site resources###")),
    )
    faq_category = "02_faq_search"
    site_tour_url = "search-tour.json"
    display_sort_options = True
    service_facet_name = "publisher"

    @cachedproperty
    def skip_in_summary(self):
        hide_cw_facet = self._cw.form.get("restrict_to_single_etype", False)
        if hide_cw_facet:
            return ("es_cw_etype",)
        return ()

    @cachedproperty
    def cached_search_response(self):
        query_string = self._cw.form.get("q", self._cw.form.get("search", ""))
        if hasattr(self, "_esresponse"):
            return self._esresponse, query_string
        # TODO - remove _cw.form.get('search') when URL transition is over
        try:
            self._esresponse = self.do_search(query_string)
        except Exception as err:
            self.exception(err)
            self._esresponse = FakeResponse()

        return self._esresponse, query_string

    def search_etype_label(self):
        _ = self._cw._
        etype = self._cw.form.get("es_cw_etype")
        bc_label = None
        if etype:
            if etype == "Service":
                bc_label = _("Service Directory")
            elif not isinstance(etype, list):
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
                page = page if str(page).isdigit() else 1
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
        if not bc_label or len(bc_label) > 1:
            bc_label = _("search-breadcrumb-label")
        return [
            (self._cw.build_url(""), _("Home")),
            # don't use dc_title() to avoid displaying wikiid
            (None, bc_label),
        ]

    @cachedproperty
    def get_selected_services_names(self):
        value = self._cw.form.get(f"es_{self.service_facet_name}", None)
        if not isinstance(value, (list, tuple)):
            value = [value]
        try:
            return {
                eid: name
                for eid, name in self._cw.execute(
                    """Any X, SN WHERE X is Service, X eid IN (%(s)s), X short_name SN"""
                    % {"s": ", ".join([str(v) for v in value])},
                )
            }
        except Exception:
            return {}

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
            services = self.get_selected_services_names
            if services:
                publisher = list(services.values())[0]
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

    def search_summary(self):
        facets = self._cw.form
        summary = []
        facets_to_display = self.facets_to_display
        fulltext_summary = []
        inventory = facets.pop("inventory", None)
        service_labels = {}
        _ = self._cw._
        skip_in_summary = self.skip_in_summary
        if facets.get("advanced"):
            skip_in_summary += ("es_date_max", "es_date_min")
        for key, value in facets.items():
            summary_value = {}
            if key == "es_publisher" and value:
                service_labels = self.get_selected_services_names
                if inventory:
                    if service_labels:
                        inventory = list(service_labels.values())[0]
                    else:
                        inventory = ""
                    continue
            if key in skip_in_summary:
                continue
            if key.startswith("es_"):
                # get the facet label requires to remove the "es_" substring
                facetlabel = [x[1] for x in facets_to_display if x[0] == key[3:]]
                if key == "es_date_min" and value:
                    summary_value["name"] = self._cw._("date-min-label")
                elif key == "es_date_max" and value:
                    summary_value["name"] = self._cw._("date-max-label")
                elif len(facetlabel) > 0:
                    summary_value["name"] = facetlabel[0]
                else:
                    continue
                if not isinstance(value, (list, tuple)):
                    value = [value]
                data = []
                value = [str(val).strip() for val in value if val]
                for val in value:
                    url_params = {key: list(set(value).difference([val]))}
                    reset_url = rebuild_url(self._cw, replace_keys=True, **url_params)
                    if key == "es_publisher":
                        if val.isnumeric():
                            val = service_labels.get(int(val), val)
                    elif key == "es_digitized":
                        val = _("yes") if (val == "True" or val is True) else _("no")
                    data.append([val, reset_url])
                summary_value["value"] = data
            elif key == "fulltext_facet":
                value = value.strip()
                if value:
                    reset_url = rebuild_url(self._cw, **{key: None})
                    fulltext_summary.append((value, reset_url))

            if summary_value and key != "es_escategory":
                summary.append(summary_value)
        if fulltext_summary:
            summary.insert(0, {"name": _("Contains"), "value": fulltext_summary})
        context = {}
        query = self._cw.form.get("q", self._cw.form.get("search", "")).strip()
        if query:
            context["query"] = query
        section = self._cw.form.get("ancestors")
        if section:
            try:
                section = self._cw.find("Section", eid=self._cw.form["ancestors"]).one()
                context["section"] = section.cw_adapt_to("ITemplatable").entity_param().title
            except NoResultError:
                pass
        if inventory:
            context["inventory"] = inventory
        return {"context": context, "summary": summary}

    def reset_all_facets_link(self):
        """Creates a URL which resets the values from the facets to display

        The value of the initial query (parameter q) is kept
        as well as values which come from other SearchView
        """
        url_params = {}
        facets = self.facets_to_display
        for facet in facets:
            url_params["es_{}".format(facet[0])] = None
        url_params["fulltext_facet"] = None
        url_params["es_date_min"] = None
        url_params["es_date_max"] = None
        return rebuild_url(self._cw, **url_params)

    def sort_options(self, response):
        """
        Returns links with the sort_options and their label
        """
        _ = self._cw._
        url_params = {}
        url_params["page"] = None  # reset page number on new sort
        sort_options = {
            "pertinence": _("Pertinence"),
            "sortdate": _("Date ascending"),
            "-sortdate": _("Date descending"),
            "publisher": _("Publisher"),
        }
        cw_etypes_facet = [x[0] for x in getattr(response.facets, "cw_etype", ())]
        selected_cw_etype = self._cw.form.get("es_cw_etype", None)

        etypes_with_publisher = ["Publication", "FAComponent", "Virtual_exhibit", "FindingAid"]

        current_sort_option = self._cw.form.get("sort", "pertinence")

        # Remove publisher sort option when the cw_etype facet does not contain
        # a etypes_with_publisher or when a cw_etype is selected and is not
        # one of etypes_with_publisher
        if (not any(etype in cw_etypes_facet for etype in etypes_with_publisher)) or (
            selected_cw_etype
            and not any(etype in selected_cw_etype for etype in etypes_with_publisher)
        ):
            sort_options.pop("publisher", None)

        # fallback to pertinence option if the requested option doesn't exist
        if current_sort_option not in sort_options:
            current_sort_option = "pertinence"

        links = []
        for value, label in sort_options.items():
            if value != "pertinence":
                url_params["sort"] = value
            else:
                url_params["sort"] = None
            links.append(
                {
                    "label": label,
                    "url": rebuild_url(self._cw, replace_keys=True, **url_params),
                }
            )
        return {"current_label": sort_options[current_sort_option], "options_links": links}

    def add_css(self):
        self._cw.add_css("css/font-awesome.css")
        self._cw.add_css("introjs/introjs.min.css")
        self._cw.add_css("introjs/pnia.introjs.css")

    def add_js(self):
        self._cw.add_js("introjs/intro.min.js")
        self._cw.add_js("cubes.pnia_search.js")
        self._cw.add_js("bundle-pnia-faq.js")
        self._cw.add_js("bundle-intro-tour.js")

    def call(self, context=None, **kwargs):
        self.add_js()
        self.add_css()
        results = self.build_template_data(context=context)
        self.write_template(results)

    def build_template_data(self, context=None):
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
            response = FakeResponse()
            query_string = self._cw.form.get("q", self._cw.form.get("search", ""))

        # handle fuzzy options
        fuzzy_options = self.compute_fuzzy_search_options(response, query_string)
        # augmented search (SubjectAuhtorities only)
        augmented_search_options = self.compute_augmented_search_options(response, query_string)
        # handle fulltext
        fulltext_params = self._cw.form.copy()
        fulltext_value = fulltext_params.pop("fulltext_facet", "")
        fulltext_params.pop("page", None)
        for key, value in fulltext_params.items():
            if not isinstance(value, (tuple, list)):
                fulltext_params[key] = [value]

        date_params = self._cw.form.copy()
        facet_date_unfolded = any((p in date_params for p in ("es_date_min", "es_date_max")))
        es_date_min = date_params.pop("es_date_min", "")
        es_date_max = date_params.pop("es_date_max", "")
        date_params.pop("page", None)
        for key, value in date_params.items():
            if not isinstance(value, (tuple, list)):
                date_params[key] = [value]

        first_previous_pages, next_last_pages = self.pagination(response.hits.total.value)
        return dict(
            req=self._cw,
            _=self._cw._,
            response=response,
            results_title=self.format_results_title(response),
            query_string=query_string,
            display_facets=True,
            display_fulltext_facet=True,
            fulltext_form_action=self._cw.build_url(self._cw.relative_path(includeparams=False)),
            fulltext_params=fulltext_params,
            fulltext_value=fulltext_value,
            facets=self.build_facets(response, context),
            search_title=self._cw._(self.no_term_msg),
            search_results=self.build_results(response),
            first_previous_pages=first_previous_pages,
            next_last_pages=next_last_pages,
            restrict_to_single_etype=self._cw.form.get("restrict_to_single_etype", False),
            search_summary=self.search_summary(),
            reset_all_facets_link=self.reset_all_facets_link(),
            header=self.get_header_attrs(),
            items_per_page_links=self.items_per_page_links(),
            sort_options=self.sort_options(response),
            display_sort_options=self.display_sort_options,
            page_number_params=self.page_number_params(),
            page_number_form_action=self._cw.build_url(self._cw.relative_path(includeparams=False)),
            current_page=self.get_current_page,
            number_of_pages=self.number_of_pages(response.hits.total.value),
            display_date_facet=True,
            es_date_min=es_date_min,
            es_date_max=es_date_max,
            date_params=date_params,
            facet_date_unfolded=facet_date_unfolded,
            fuzzy_extra_link=fuzzy_options.get("extra_link"),
            augmented_extra_link=augmented_search_options.get("extra_link"),
            site_tour_url=self.get_site_tour_url(),
            rdf_formats=self.get_rdf_formats(),
            advanced_search=fulltext_params.get("advanced", False),
        )

    def write_template(self, data):
        self.w(self.template.render(data))

    def get_site_tour_url(self):
        if self.site_tour_url:
            return self._cw.build_url(self.site_tour_url)

    def get_header_attrs(self):
        return None

    def get_rdf_formats(self):
        return None

    def rset_from_response(self, response):
        """transform an ES response into a CubicWeb rset

        This consists in iterating on current panigated response and
        inspect the ``cw_etype`` and ``eid`` document fields.

        NOTE: some etypes used for the ES indexation are not part of the
        actual CubicWeb schema and therefore require to be mapped on a
        valid entity type (e.g. ExternRef's reftypes)

        others, e.g Card are not indexed with their own etypes
        """

        def get_etype_from_result(result):
            cw_etype = getattr(result, "cw_etype", "FindingAid")
            if cw_etype == "Article":
                cw_etype = getattr(result, "estype", cw_etype)
            return cw_etype

        req = self._cw
        descr, rows = [], []
        for idx, result in enumerate(response):
            # safety belt, in v0.6.0, PDF are indexed without a cw_etype field
            cw_etype = get_etype_from_result(result)
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
        if not rset and descr == "Article":
            rset = ResultSet(rows, "Any X", description="Card")
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

    def compute_augmented_search_options(self, response, query_string):
        """augmented_search is active only in SubjectAuhtorities"""
        return {}

    def compute_fuzzy_search_options(self, response, query_string):
        search_is_fuzzy = "fuzzy" in self._cw.form
        extra_link = {}
        search_contains_operators = is_simple_query_string(query_string)
        if search_is_fuzzy and query_string:
            url_params = self._cw.form.copy()
            del url_params["fuzzy"]

            if "page" in self._cw.form:
                del url_params["page"]
            pretext = self._cw._("Fuzzy search is activated.")
            if self._cw.lang == "fr":
                pretext = reveal_glossary(self._cw, pretext)
            extra_link = {
                "href": self._cw.build_url(**url_params),
                "title": self._cw._("regular search"),
                "pretext": pretext,
            }

        if response.hits.total.value == 0 and not search_is_fuzzy and not search_contains_operators:
            url_params = self._cw.form.copy()
            url_params["fuzzy"] = True
            if "indexentry" in self._cw.form:
                del url_params["indexentry"]

            if "page" in self._cw.form:
                del url_params["page"]

            text = self._cw._("with fuzzy search option.")
            if self._cw.lang == "fr":
                text = reveal_glossary(self._cw, text)
            extra_link = {
                "href": self._cw.build_url(**url_params),
                "title": self._cw._("fuzzy search activation"),
                "pretext": self._cw._("For more results,"),
                "text": self._cw._("restart the query"),
                "posttext": text,
            }

        # if more than 200 results and search is not already exact and not in a fuzzy search
        if (
            response.hits.total.value >= 200
            and " " in query_string.strip()
            and not search_contains_operators
            and not search_is_fuzzy
        ):
            url_params = self._cw.form.copy()
            exact_expression = f'"{query_string}"'
            url_params["q"] = exact_expression
            if "page" in self._cw.form:
                del url_params["page"]
            extra_link = {
                "href": self._cw.build_url(**url_params),
                "title": self._cw._("Exact search"),
                "pretext": self._cw._("For more specific results,"),
                "text": self._cw._("try the exact expression search {}").format(
                    xml_escape(exact_expression)
                ),
            }
        return {"extra_link": extra_link, "search_is_fuzzy": search_is_fuzzy}

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
            if etype and not isinstance(etype, list):
                search_class = FACETED_SEARCHES.get(etype.lower(), PniaCWFacetedSearch)
            else:
                search_class = PniaCWFacetedSearch
        elif facet_selections.get("escategory"):
            categories = facet_selections.get("escategory")
            # if category corresponds to a single etype and if this etype
            # has a specific facet definition, use it
            if not isinstance(categories, list):
                categories = [categories]
            for category in categories:
                # FIXME To be changed to suit the new facet interface with no vertical facets
                if category in DOC_CATEGORY_ETYPES and len(DOC_CATEGORY_ETYPES[category]) == 1:
                    etype = DOC_CATEGORY_ETYPES[category][0]
                    search_class = FACETED_SEARCHES.get(etype.lower(), PniaCWFacetedSearch)
                else:
                    search_class = PniaCWFacetedSearch
        else:
            search_class = PniaCWFacetedSearch
        if "indexentry" in self._cw.form:
            rset = self._cw.execute(
                "Any L, E WHERE X eid %(e)s, X label L, X is ET, ET name E",
                {"e": self._cw.form["indexentry"]},
            )
            if rset:
                query_string, cw_etype = rset[0]
                search_class = FACETED_SEARCHES.get(cw_etype.lower())
            else:
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
        kwargs["es_date_max"] = self._cw.form.get("es_date_max")
        kwargs["es_date_min"] = self._cw.form.get("es_date_min")
        kwargs["es_escategory"] = self._cw.form.get("es_escategory")
        kwargs["cw_etype"] = facet_selections.get("cw_etype")
        kwargs["sort"] = self._cw.form.get("sort", ())
        kwargs["fulltext_facet"] = self._cw.form.get("fulltext_facet")
        kwargs["es_date_max"] = self._cw.form.get("es_date_max")
        kwargs["es_date_min"] = self._cw.form.get("es_date_min")
        kwargs["searches"] = self._cw.form.get("searches")
        kwargs["searches_op"] = self._cw.form.get("searches_op")
        kwargs["searches_t"] = self._cw.form.get("searches_t")
        kwargs["services"] = self._cw.form.get("services")
        kwargs["services_op"] = self._cw.form.get("services_op")
        kwargs["producers"] = self._cw.form.get("producers")
        kwargs["producers_op"] = self._cw.form.get("producers_op")
        kwargs["producers_t"] = self._cw.form.get("producers_t")
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
            facet_html = facet_render(req, facet, facetid, facetlabel, context, response)
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
            ("digitized", _("digitized_facet")),
            ("cw_etype", _("document_type_facet")),
            ("publisher", _("publishers_facet")),
            ("status", _("status_facet")),
            ("year", _("time_period_facet")),
            ("originators", _("originators_facet")),
            ("level", _("service_level_facet")),
        )


class PniaElasticSearchWithContextView(PniaElasticSearchView):
    __abstract__ = True
    site_tour_url = None

    def display_contextual_info(self):
        w, _ = self.w, self._cw._
        with T.div(w, id="section-article-header"):
            w(T.h2(_("contexte de la recherche")))
            for info in self.get_infos():
                with T.div(w, Class="documents-fonds"):
                    w(info)

    def call(self, **kwargs):
        self.display_contextual_info()
        super(PniaElasticSearchWithContextView, self).call(**kwargs)


circular_facet_active = match_form_params(es_cw_etype="Circular")

service_facet_active = match_form_params(es_cw_etype="Service")


class SearchCmsChildrenView(PniaElasticSearchView):
    __select__ = (
        PniaElasticSearchView.__select__
        & match_form_params("ancestors")
        & ~circular_facet_active
        & ~service_facet_active
    )
    display_sort_options = False
    display_results_info = False
    title_count_templates = (
        _("No documents in this section"),
        _("1 document in this section"),
        _("{count} documents in this section"),
    )

    def get_themes_for_section(self, section, url_params=None):
        req = self._cw
        themes_rset = req.execute(
            """Any A, L, DH, DN, O ORDERBY O, L LIMIT 9 WHERE
            X eid %(e)s,
            X section_themes OA, OA order O,
            OA subject_entity A, A label L,
            A subject_image I, I image_file F,
            F data_hash DH, F data_name DN
            """,
            {"e": section.eid},
        )
        if not themes_rset:
            return []
        entities = []
        for auth_eid, label, dh, dn, order in themes_rset:
            image_src = req.build_url(f"file/{dh}/{dn}")
            url = f"subject/{auth_eid}"
            if url_params:
                url = rebuild_url(req, url=url, replace_keys=True, **url_params)
            entities.append(
                {
                    "url": req.build_url(url),
                    "label": label,
                    "image_src": image_src,
                    "order": order,
                }
            )
        return entities

    def call(self, context=None, **kwargs):
        self.add_js()
        self.add_css()
        results = self.build_template_data(context=context)
        entity = self._cw.find("Section", eid=self._cw.form["ancestors"]).one()
        if entity.display_mode == "mode_themes":
            # compute themes from results and add ancestors and cw_etype params
            # in subject url (cf. #74094377)
            url_params = {"ancestors": self._cw.form["ancestors"]}
            response = results["response"]
            etype = self._cw.form.get("restrict_to_single_etype", None)
            if etype is None:
                etypes = getattr(response.facets, "cw_etype", ())
                if len(etypes) == 1:
                    etype = etypes[0][0]
            if etype:
                url_params["cw_etype"] = etype
            themes = self.get_themes_for_section(entity, url_params=url_params)
            if themes:
                self.w(entity.view("section-themes", themes=themes))
        self.write_template(results)

    def customize_search(self, query_string, facet_selections, start=10, stop=None, **kwargs):
        req = self._cw
        # a req.form.pop("ancestors") was previously used
        query_string = req.form["ancestors"]
        etype = facet_selections.get("cw_etype", "section")
        if not isinstance(etype, list):
            search_class = FACETED_SEARCHES.get(etype.lower(), PniaCWFacetedSearch)
        else:
            search_class = PniaCWFacetedSearch
        default_index_name = "{}_all".format(self._cw.vreg.config.get("index-name"))
        for facet_searched in list(facet_selections.keys()):
            if facet_searched not in list(search_class.facets.keys()):
                del facet_selections[facet_searched]
        kwargs["ancestors-query"] = True
        kwargs["fulltext_facet"] = req.form.get("fulltext_facet")
        kwargs["es_date_min"] = req.form.get("es_date_min")
        kwargs["es_date_max"] = req.form.get("es_date_max")
        return search_class(
            query_string,
            facet_selections,
            doc_types=["_doc"],
            index=default_index_name,
            form=self._cw.form,
            **kwargs
        )[start:stop]


class PniaElasticSearchNewsContent(PniaElasticSearchView):
    __select__ = PniaElasticSearchView.__select__ & match_form_params(es_cw_etype="NewsContent")
    display_sort_options = False


class PniaElasticSearchService(PniaElasticSearchView):
    __select__ = PniaElasticSearchView.__select__ & service_facet_active
    site_tour_url = None

    @property
    def facets_to_display(self):
        _ = self._cw._
        return (
            ("cw_etype", _("document_type_facet")),
            ("level", _("service_level_facet")),
        )

    def get_header_attrs(self):
        return {"title": self._cw._("Service_plural")}


class PniaElasticSearchCirculaires(PniaElasticSearchView):
    __select__ = PniaElasticSearchView.__select__ & circular_facet_active
    title_count_templates = (_("No result"), _("1 circulaire"), _("{count} circulaires"))
    template = get_template("searchlist-circular.jinja2")
    site_tour_url = None
    display_sort_options = False

    @property
    def facets_to_display(self):
        _ = self._cw._
        return (
            ("cw_etype", _("document_type_facet")),
            ("status", _("status")),
            ("business_field", _("business_field_facet")),
            ("siaf_daf_signing_year", _("siaf_daf_signing_year")),
            ("archival_field", _("archival_field_facet")),
            ("historical_context", _("historical_context_facet")),
            ("action", _("action_facet")),
        )

    def get_header_attrs(self):
        return {"title": self._cw._("Circulars")}


class PniaConceptPrimaryView(PniaElasticSearchCirculaires):
    __regid__ = "primary"
    __select__ = PrimaryView.__select__ & is_instance("Concept")
    title_count_templates = (_("No result"), _("1 concept"), _("{count} concepts"))

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
        kwargs["es_date_max"] = self._cw.form.get("es_date_max")
        kwargs["es_date_min"] = self._cw.form.get("es_date_min")
        req.form["restrict_to_single_etype"] = True
        title = entity.dc_title()
        for facet_searched in list(facet_selections.keys()):
            if facet_searched not in list(search_class.facets.keys()):
                del facet_selections[facet_searched]
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
            "<a href={}>{}</a>".format(
                xml_escape(entity.absolute_url()), xml_escape(entity.dc_title())
            )
        )


class InventoryMixin:
    @property
    def facets_to_display(self):
        """
        Method to list facets to display (can be customized)
        Display PniaElasticSearchView but "publisher" facet
        """
        for facet in super().facets_to_display:
            if facet[0] != self.service_facet_name:
                yield facet

    @cachedproperty
    def service_name(self):
        service = self.get_selected_services_names.values()
        if service:
            return list(service)[0]


class InventoryPrimaryView(InventoryMixin, PniaElasticSearchView):
    __select__ = PniaElasticSearchView.__select__ & match_form_params(inventory=True)
    skip_in_summary = ("es_publisher",)

    def get_header_attrs(self):
        if self.service_name:
            return {
                "title": "{}{}{}".format(
                    self.service_name, self._cw._(":"), self._cw._("see all referenced archives")
                )
            }


class PniaElasticSearchAuthorityRecordt(PniaElasticSearchView):
    __select__ = PniaElasticSearchView.__select__ & match_form_params(es_cw_etype="AuthorityRecord")
    site_tour_url = None

    def get_header_attrs(self):
        return {"title": self._cw._("AuthorityRecords")}


def registration_callback(vreg):
    components = (
        (PniaElasticSearchView, ElasticSearchView),
        (PniaConceptPrimaryView, ConceptPrimaryView),
    )
    vreg.register_all(list(globals().values()), __name__, [new for (new, old) in components])
    for new, old in components:
        vreg.register_and_replace(new, old)
