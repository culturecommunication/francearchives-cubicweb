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

import json

from elasticsearch_dsl import TermsFacet, HistogramFacet, Q, query as dsl_query

from logilab.common.textutils import unormalize

from cubicweb import _, UnknownEid

from cubicweb_elasticsearch.views import CWFacetedSearch

from cubicweb_francearchives.entities.nomina import nomina_translate_codetype
from cubicweb_francearchives.views import rebuild_url, format_number, get_template

# FIXME - this might end up being configurable by facet
FACET_SIZE = 15
MISSING_INT = -100000
ALL_VALUES_SIZE = 300


class MissingNAMixIn(object):
    def add_filter(self, filter_values):
        if "N/R" in filter_values:
            return Q("bool", **{"must_not": Q("exists", field=self._params["field"])})
        return super(MissingNAMixIn, self).add_filter(filter_values)


class MissingNATermsFacet(MissingNAMixIn, TermsFacet):
    pass


class MissingNAHistogramFacet(MissingNAMixIn, HistogramFacet):
    def get_values(self, data, filter_values):
        out = []
        for bucket in data:
            key = self.get_value(bucket)
            if key == MISSING_INT:
                key = _("N/R")
            try:
                key = int(key)
            except Exception:
                pass
            out.append((key, bucket["doc_count"], self.is_filtered(key, filter_values)))
        return out


# TODO provide generic mechanism for missing query
class PublisherTermsFacet(TermsFacet):
    except_AN_key = "Tout sauf les Archives Nationales"

    def add_filter(self, filter_values):
        """Create a terms filter instead of bool containing term filters."""
        if self.except_AN_key in filter_values:
            return Q("bool", **{"must_not": Q("terms", publisher=["Archives Nationales"])})
        if "N/R" in filter_values:
            return Q("bool", **{"must_not": Q("exists", field="publisher")})
        if filter_values:
            return Q("terms", **{self._params["field"]: filter_values})

    def get_values(self, data, filter_values):
        except_AN_count = 0
        out = []
        for bucket in data:
            key = self.get_value(bucket)
            # TODO on es_response there is a global count, substract Archives Nationales to it
            if key != "Archives Nationales":
                except_AN_count += bucket["doc_count"]
            out.append((key, bucket["doc_count"], self.is_filtered(key, filter_values)))
        if not except_AN_count or len(data) <= 2:
            return out
        all_except = [
            (
                self.except_AN_key,
                except_AN_count,
                self.is_filtered(self.except_AN_key, filter_values),
            )
        ]
        return all_except + out


class ServiceTermsFacet(MissingNAMixIn, TermsFacet):
    def get_values(self, data, filter_values):
        """publisher value is a keyword in ES, but an integer in Posgres (service eid)"""
        out = []
        for bucket in data:
            key = self.get_value(bucket)
            try:
                key = int(key)
            except Exception:
                continue
            out.append((key, bucket["doc_count"], self.is_filtered(key, filter_values)))
        return out


class PniaCWFacetedSearch(CWFacetedSearch):
    fields = [
        "did.unitid^6",
        "title*^3",
        "did.unittitle^3",
        "content*",
        "scopecontent",
        "text",
        "name",
        "attachment",
        "index_entries.label",
        "alltext*",
    ]
    facets = {
        "cw_etype": TermsFacet(field="cw_etype", size=FACET_SIZE),
        # custom
        "publisher": ServiceTermsFacet(field="service.eid", size=ALL_VALUES_SIZE),
        "digitized": TermsFacet(field="digitized"),
        "originators": TermsFacet(field="originators", size=FACET_SIZE),
    }

    def add_to_query(self, bool_query, search, query):
        if bool_query is None:
            return search
        if query:
            search.query.filter.append(bool_query)
        else:
            if search.query:
                search.query.filter.append(bool_query)
            else:
                search.query = bool_query
        return search

    def only_or_query(self, searches, get_term_query, types):
        term_queries = []
        for index, value in enumerate(searches):
            if value == "":
                continue
            term_query = get_term_query(value, index, types)
            term_queries.append(term_query)
        return Q("bool", should=term_queries, minimum_should_match=1)

    def only_and_query(self, searches, get_term_query, types):
        term_queries = []
        for index, value in enumerate(searches):
            if value == "":
                continue
            term_query = get_term_query(value, index, types)
            term_queries.append(term_query)
        return Q("bool", must=term_queries)

    def add_advanced_query(self, parameter_name, search, query, get_term_query):
        search_value = self.extra_kwargs.get(parameter_name)
        if search_value is None:
            return search
        searches = json.loads(search_value)
        search_op = json.loads(self.extra_kwargs.get(f"{parameter_name}_op"))
        search_t = json.loads(self.extra_kwargs.get(f"{parameter_name}_t"))

        if ("ET" not in search_op) and ("SAUF" not in search_op):
            return self.add_to_query(
                self.only_or_query(searches, get_term_query, search_t), search, query
            )
        if ("OU" not in search_op) and ("SAUF" not in search_op):
            return self.add_to_query(
                self.only_and_query(searches, get_term_query, search_t), search, query
            )

        bool_query = None
        for index, value in enumerate(searches):
            if value == "":
                continue
            term_query = get_term_query(value, index, search_t)
            if index == 0:
                bool_query = term_query
                continue
            if len(search_op) >= index:
                operator = search_op[index - 1]
                if operator == "SAUF":
                    bool_query = Q("bool", must=bool_query, must_not=term_query)
                elif operator == "OU":
                    bool_query = Q("bool", should=[bool_query, term_query], minimum_should_match=1)
                else:
                    bool_query = Q("bool", must=[bool_query, term_query])

        return self.add_to_query(bool_query, search, query)

    def test_or_authority_query(self, search, query):
        def get_term_query(value, index, types):
            if types[index] not in ["s", "l", "a"]:
                return Q(
                    "simple_query_string",
                    query=value,
                    default_operator="and",
                )
            else:
                return Q("term", **{"index_entries.authority": value})

        return self.add_advanced_query("searches", search, query, get_term_query)

    def producers_query(self, search, query):
        def get_term_query(value, index, types):
            if types[index] == "k":
                return Q("term", **{"originators": value})
            else:
                return Q(
                    "simple_query_string",
                    query=value,
                    default_operator="and",
                    fields=["originators.text"],
                )

        return self.add_advanced_query("producers", search, query, get_term_query)

    def service_query(self, search, query):
        services_value = self.extra_kwargs.get("services")
        if services_value is None:
            return search
        services = json.loads(services_value)
        services_op = json.loads(self.extra_kwargs.get("services_op"))

        services_query = []

        for service_eid in services:
            if not service_eid:
                continue
            term_query = Q("term", **{"service.eid": service_eid})
            services_query.append(term_query)

        if services_op == "SAUF":
            return self.add_to_query(Q("bool", must_not=services_query), search, query)
        return self.add_to_query(Q("bool", should=services_query), search, query)

    def query(self, search, query):
        if self.extra_kwargs.get("ancestors-query") and query:
            # we are in Section primary view
            search.query = dsl_query.Bool(must=Q("match", ancestors=query))
        else:
            search = super(PniaCWFacetedSearch, self).query(search, query)
        search = self.test_or_authority_query(search, query)
        search = self.producers_query(search, query)
        search = self.service_query(search, query)
        search = self.add_dates_range(search, query)
        search = self.fulltext_facet(search, query)
        search = self.add_escategory(search, query)

        return search

    def get_dates_ranges(self):
        dates_lte = self.extra_kwargs.get("es_date_max")
        dates_gte = self.extra_kwargs.get("es_date_min")
        date_range = {}
        if dates_lte:
            date_range["lte"] = dates_lte
        if dates_gte:
            date_range["gte"] = dates_gte
        return date_range

    def add_dates_range(self, search, query):
        date_range = self.get_dates_ranges()
        if not date_range:
            return search
        must_query = Q("exists", field="dates") & dsl_query.Range(**{"dates": date_range})
        if query:
            search.query.filter.append(must_query)
        else:
            if search.query:
                search.query.filter.append(must_query)
            else:
                search.query = dsl_query.Bool(must=must_query)
        return search

    def fulltext_facet(self, search, query):
        fulltext_query = self.extra_kwargs.get("fulltext_facet")
        if not fulltext_query:
            return search
        if query:
            search.query.filter.append(
                Q("simple_query_string", query=fulltext_query, default_operator="and")
            )

        else:
            must_query = Q("simple_query_string", query=fulltext_query, default_operator="and")
            if search.query:
                search.query.filter.append(must_query)
            else:
                search.query = dsl_query.Bool(must=must_query)
        return search

    def add_escategory(self, search, query):
        escategory = self.extra_kwargs.get("es_escategory", None)
        if not isinstance(escategory, str):
            return search
        must_query = dsl_query.Term(escategory=escategory)
        if query or search.query:
            search.query.filter.append(must_query)
        else:
            search.query = dsl_query.Bool(must=must_query)
        return search


class PniaFCFacetedSearch(PniaCWFacetedSearch):
    fields = [
        "did.unitid^6",
        "title*^3",
        "did.unittitle^3",
        "name^3",
        "content*^2",
        "content*",
        "index_entries.label",
        "alltext*",
    ]


class NoHighlightMixin(object):
    def highlight(self, search):
        """
        don't highlight when searching for FAComponent children
        https://github.com/elastic/elasticsearch/issues/14999
        """
        return search


class PniaFAFacetedSearch(PniaCWFacetedSearch):
    fields = [
        "did.unitid^6",
        "title^3",
        "did.unittitle^3",
        "name^3",
        "content^2",
        "acquisition_info",
        "scopecontent",
        "index_entries.label",
        "alltext*",
    ]


# TODO provide generic mechanism for missing query


class PniaCircularFacetedSearch(PniaCWFacetedSearch):
    facets = {
        "cw_etype": TermsFacet(field="cw_etype", size=FACET_SIZE),
        "status": TermsFacet(field="status"),
        "business_field": MissingNATermsFacet(
            field="business_field", missing=_("N/R"), size=ALL_VALUES_SIZE
        ),
        "historical_context": MissingNATermsFacet(
            field="historical_context", missing=_("N/R"), size=ALL_VALUES_SIZE
        ),
        "document_type": MissingNATermsFacet(
            field="document_type", missing=_("N/R"), size=ALL_VALUES_SIZE
        ),
        "action": MissingNATermsFacet(field="action", missing=_("N/R"), size=ALL_VALUES_SIZE),
        "siaf_daf_signing_year": MissingNAHistogramFacet(
            field="siaf_daf_signing_year", interval=10, missing=MISSING_INT, min_doc_count=1
        ),
        "archival_field": MissingNATermsFacet(
            field="archival_field", missing=_("N/R"), size=FACET_SIZE
        ),
    }

    def query(self, search, query):
        search = super(PniaCircularFacetedSearch, self).query(search, query)
        return search.sort("-sortdate")


class PniaNewsContentFacetedSearch(PniaCWFacetedSearch):
    facets = {
        "cw_etype": TermsFacet(field="cw_etype", size=FACET_SIZE),
    }

    def query(self, search, query):
        search = super(PniaNewsContentFacetedSearch, self).query(search, query)
        return search.sort("-sortdate")


class IndexFacetedSearchMixin(object):
    def query(self, search, query):
        queries = [Q("term", **{"index_entries.authority": self.form["indexentry"]})]
        ancestors = self.form.get("ancestors")
        if ancestors:
            queries.append(Q("match", ancestors=ancestors))
        search.query = dsl_query.Bool(must=queries)
        search = self.add_dates_range(search, query)
        search = self.fulltext_facet(search, query)
        search = self.add_escategory(search, query)
        return search


class PniaIndexEntryFacetedSearch(IndexFacetedSearchMixin, PniaCWFacetedSearch):
    pass


class PniaFCIndexEntryFacetedSearch(NoHighlightMixin, IndexFacetedSearchMixin, PniaFCFacetedSearch):
    pass


class PniaSubjectAuthorityFacetedSearch(IndexFacetedSearchMixin, PniaCWFacetedSearch):
    fields = [
        "title*",
        "did.unittitle",
        "name",
        "content*",
        "acquisition_info",
        "scopecontent",
        "index_entries.label^3",  # boost indexed documents
        "alltext*",
    ]

    def query(self, search, query):
        """
        for multiple fields text search use
          Q("multi_match", query=query, type="phrase", slop=0, fields=("title", "content"))
        """
        # We want "index_query" results to be displayed before "text_query" results
        # the max score for index_query is 1, so we boost it with an arbitrary value of 100
        # Note that if the autority label matches the label in index_entries.label
        # and alltext this score will increase
        if not self.form.get("aug"):
            # execute the basic IndexFacetedSearchMixin.query without augmented query
            # https://extranet.logilab.fr/ticket/74056123
            return super().query(search, query)
        # ancestors are not used with augmented query
        date_range = self.get_dates_ranges()
        index_query_must = [
            Q("term", index_entries__authority={"value": self.form["indexentry"], "boost": 100})
        ]
        # match_phrase query can not be called on multiple fields
        text_query_must = [Q("multi_match", query=query, type="phrase", slop=0, fields=self.fields)]
        if date_range:
            dates_query = Q("exists", field="dates") & dsl_query.Range(**{"dates": date_range})
            index_query_must.append(dates_query)
            text_query_must.append(dates_query)
        fulltext_query = self.extra_kwargs.get("fulltext_facet")
        if fulltext_query:
            fulltext_query = Q("simple_query_string", query=fulltext_query, default_operator="and")
            index_query_must.append(fulltext_query)
            text_query_must.append(fulltext_query)
        index_query = dsl_query.Bool(must=index_query_must)
        text_query = dsl_query.Bool(must=text_query_must)
        search.query = dsl_query.Bool(should=[index_query, text_query])
        return search


class PniaCmsSectionFacetedSearch(PniaCWFacetedSearch):
    def query(self, search, query):
        search = super(PniaCmsSectionFacetedSearch, self).query(search, query)
        return search.sort("order", "-sortdate")


class PniaServiceFacetedSearch(PniaCWFacetedSearch):
    facets = {
        "cw_etype": TermsFacet(field="cw_etype", size=FACET_SIZE),
        "level": MissingNATermsFacet(field="level", missing=_("N/R"), size=FACET_SIZE),
    }

    def query(self, search, query):
        # XXX using query because there is no sort in faceted_search
        # https://github.com/elastic/elasticsearch-dsl-py/issues/532
        search = super(PniaServiceFacetedSearch, self).query(search, query)
        return search.sort("sort_name")


class PniaAuthorityRecordFacetedSearch(PniaCWFacetedSearch):
    fields = [
        "title*^3",
        "name^3",
        "history",
        "functions",
        "occupations",
        "index_entries.label",
        "alltext*",
    ]


class NominaFacetedSearch(PniaCWFacetedSearch, NoHighlightMixin):
    fields = [
        "alltext",
    ]
    facets = {
        "service": ServiceTermsFacet(field="service", size=ALL_VALUES_SIZE),
        "acte_type": TermsFacet(field="acte_type", size=ALL_VALUES_SIZE),
    }

    def query(self, search, query):
        forenames = self.extra_kwargs.get("es_forenames")
        names = self.extra_kwargs.get("es_names")
        locations = self.extra_kwargs.get("es_locations")
        authority = self.extra_kwargs.get("authority")

        must = []
        if forenames:
            must.append(Q("match", forenames=forenames))
        if names:
            must.append(Q("match", names=names))
        if locations:
            must.append(Q("match", locations=locations))
        if authority:
            must.append(Q("match", authority=authority))

        search.query = dsl_query.Bool(must=must)
        search = self.add_dates_range(search, query)
        search = self.fulltext_facet(search, query)

        return search


FACETED_SEARCHES = {
    "default": PniaCWFacetedSearch,
    "newscontent": PniaNewsContentFacetedSearch,
    "circular": PniaCircularFacetedSearch,
    "section": PniaCmsSectionFacetedSearch,
    "service": PniaServiceFacetedSearch,
    "facomponent": PniaFCFacetedSearch,
    "findingaid": PniaFAFacetedSearch,
    "indexentry": PniaIndexEntryFacetedSearch,
    "agentauthority": PniaIndexEntryFacetedSearch,
    "locationauthority": PniaIndexEntryFacetedSearch,
    "subjectauthority": PniaSubjectAuthorityFacetedSearch,
    "facomponent_indexentry": PniaFCIndexEntryFacetedSearch,
    "authorityrecord": PniaAuthorityRecordFacetedSearch,
}


class PniaDefaultFacetRenderer(object):
    template = get_template("facet.jinja2")
    item = (
        '<li class="{css}" style="{style}">'
        '    <a href="{url}" title="{alt}" class="facet__focusable-item">'
        "      {content}"
        '      <span class="facet__item_count">{count}</span>'
        "    </a>"
        "</li>"
    )
    item_nolink = (
        '<li class="facet__value">'
        '  <div class="facet--nolink">'
        "   {content}"
        '   <span class="facet__item_count">{count}</span>'
        "  </div>"
        "</li>"
    )
    filter_tags = True
    unfolded = False

    @staticmethod
    def build_content(req, content):
        return req._(content)

    def __init__(self, sort="count", items_size=FACET_SIZE, nr_tag="N/R"):
        assert sort in ("count", "item")
        self.item_sort = sort
        self.items_size = items_size
        self.nr_tag = nr_tag

    def __call__(self, req, bucket, facetid, facetlabel, searchcontext, response):
        # keep only items leading to more than 1 result
        bucket = self.build_bucket(bucket)
        if len(bucket) == 0:
            return None
        self.req = req
        self.facetid = facetid
        self.searchcontext = searchcontext
        self.selected = False
        if "es_{}".format(self.facetid) in self.req.form:
            self.selected = True
        self.total_count = response.hits.total.value if response is not None else 0
        return self.render(bucket, facetlabel)

    def item_css(self, idx, selected):
        css = ["facet__value"]
        if idx >= self.items_size:
            css.append("more-option")
        if selected:
            css.append("facet__value--active")
        return css

    def item_style(self, idx):
        if idx >= self.items_size:
            return "display: none"
        return ""

    def build_bucket(self, bucket):
        # keep only items leading to more than 1 result
        bucket = [item for item in bucket if item[1] > 0]
        if self.item_sort == "item":
            bucket.sort(key=lambda x: unormalize(x[0].lower()))
        # sort facet values to put selected first
        bucket = sorted(bucket, key=lambda x: -x[2])
        return bucket

    def build_item_content(self, content, selected):
        content = self.build_content(self.req, content)
        if selected:
            return '<span class="facet--active">{}</span>'.format(content)
        return content

    def translate_label(self, tag):
        return tag

    def render_nolink_item(self, idx, tag, count, selected):
        tag = self.translate_label(tag)
        return self.item_nolink.format(
            content=self.build_item_content(tag, selected), count=format_number(count, self.req)
        )

    def render_item(self, idx, tag, count, selected):
        req = self.req
        _ = self.req._
        param_name = "es_{}".format(self.facetid)
        alt = _("select")
        url_params = {
            "vid": None,
            "page": None,
            param_name: str(tag),
        }
        if selected:
            alt = _("deselect")
        tag = self.translate_label(tag)
        return self.item.format(
            url=rebuild_url(req, **url_params),
            css=" ".join(self.item_css(idx, selected)),
            alt=alt,
            content=self.build_item_content(tag, selected),
            style=self.item_style(idx),
            count=format_number(count, req),
        )

    def render(self, bucket, facetlabel):
        items = []
        more_items = []
        last_item = None
        for idx, (tag, count, selected) in enumerate(bucket):
            if not tag and self.filter_tags:
                continue
            if len(bucket) == 1 and count == self.total_count:
                item = self.render_nolink_item(idx, tag, count, selected)
            else:
                item = self.render_item(idx, tag, count, selected)
            if item:
                # XXX do it in build_bucket ?
                if tag == self.nr_tag:
                    last_item = item
                elif idx <= self.items_size:
                    items.append(item)
                else:
                    more_items.append(item)
        if last_item:
            if idx <= self.items_size:
                items.append(last_item)
            else:
                more_items.append(last_item)
        if not items:
            return None
        return self.template.render(
            {
                "_": self.req._,
                "facetid": self.facetid,
                "facet_label": facetlabel,
                "facet_items": items,
                "facet_unfolded": self.unfolded or self.selected,
                "more_items_label": self.req._("More options (%(count)s)")
                % {"count": len(more_items)},
                "less_items_label": self.req._("Less options"),
                "more_facet_items": more_items,
            }
        )


def format_year_item(year, incr):
    year_value = int(year)
    return "{} - {}".format(year_value, year_value + incr)


class PniaYearFacetRenderer(PniaDefaultFacetRenderer):
    def render_item(self, idx, bucket_key, count, selected):
        if isinstance(bucket_key, float):
            bucket_key = int(bucket_key)
        return super(PniaYearFacetRenderer, self).render_item(idx, bucket_key, count, selected)

    @staticmethod
    def build_content(req, content):
        return format_year_item(content, 99)


class PniaEtypeFacetRenderer(PniaDefaultFacetRenderer):
    @staticmethod
    def build_content(req, content):
        if content == "Service":
            return req._("archive-services-label")
        return req.__("%s_plural" % content)


class PniaNominaDocumentTypeRenderer(PniaDefaultFacetRenderer):
    def translate_label(self, tag):
        return nomina_translate_codetype(self.req, tag)


class PniaServiceRenderer(PniaDefaultFacetRenderer):
    def render(self, bucket, facetlabel):
        self.services = {
            eid: name
            for eid, name in self.req.execute(
                """Any X, SN WHERE X is Service,
                   X short_name SN"""
            )
        }
        return super().render(bucket, facetlabel)

    def translate_label(self, tag):
        return self.services.get(tag, tag)


class PniaAncestorsFacetRenderer(PniaDefaultFacetRenderer):
    item = (
        '<li data-eid="{eid}" class="{css}" style="{style}">'
        '    <a href="{url}" title="{alt}" class="facet__focusable-item">'
        "        {content}"
        '        <span class="facet__item_count">{count}</span>'
        "   </a>"
        "</li>"
    )

    def render_nolink_item(self, idx, tag, count, selected):
        return self.render_item(idx, tag, count, selected)

    def render_item(self, idx, tag, count, selected):
        req = self.req
        try:
            section = req.entity_from_eid(tag)
        except UnknownEid:
            req.exception("failed to get entity with eid %s (ES out of sync?)", tag)
            return None
        if self.searchcontext:
            path = self.searchcontext.get("path", ())
            if tag in path:
                return None
        return self.item.format(
            url=section.absolute_url(),
            eid=tag,
            css=" ".join(self.item_css(idx, selected)),
            alt=req._("select"),
            content=section.dc_title(),
            style=self.item_style(idx),
            count=format_number(count, req),
        )


class PniaDigitizedFacetRenderer(PniaDefaultFacetRenderer):
    filter_tags = False
    unfolded = True

    def build_bucket(self, bucket):
        # convert int value to boolean: 0 -> False and 1 -> True
        bucket = super(PniaDigitizedFacetRenderer, self).build_bucket(bucket)
        return [(bool(item[0]),) + item[1:] for item in bucket]

    @staticmethod
    def build_content(req, content):
        _ = req._
        return _("yes") if content else _("no")


class PniaStatusFacetRenderer(PniaDefaultFacetRenderer):
    @staticmethod
    def build_content(req, content):
        _ = req._
        status_html = '<div class="circular-status circular-status-{}"></div> {}'
        return status_html.format(content, _(content))


def format_missing_year_item(req, year, incr):
    try:
        year_value = int(year)
        return "{} - {}".format(year_value, year_value + incr)
    except Exception:
        return req._(year)


class PniaSigningYearFacetRenderer(PniaDefaultFacetRenderer):
    @staticmethod
    def build_content(req, content):
        return format_missing_year_item(req, content, 9)


FACET_RENDERERS = {
    "default": PniaDefaultFacetRenderer(),
    "year": PniaYearFacetRenderer(),
    "cw_etype": PniaEtypeFacetRenderer(),
    "digitized": PniaDigitizedFacetRenderer(),
    "status": PniaStatusFacetRenderer(),
    "siaf_daf_signing_year": PniaSigningYearFacetRenderer(),
    "business_field": PniaDefaultFacetRenderer(sort="item"),
    "historical_context": PniaDefaultFacetRenderer(sort="item"),
    "document_type": PniaDefaultFacetRenderer(sort="item"),
    "action": PniaDefaultFacetRenderer(sort="item"),
    "service": PniaServiceRenderer(),
    "acte_type": PniaNominaDocumentTypeRenderer(),
    "publisher": PniaServiceRenderer(),
}
