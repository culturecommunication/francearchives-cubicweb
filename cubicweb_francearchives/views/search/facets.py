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

from elasticsearch_dsl import TermsFacet, DateHistogramFacet, HistogramFacet, Q, query as dsl_query

from logilab.common.textutils import unormalize
from logilab.mtconverter import xml_escape

from cubicweb import _, UnknownEid

from cubicweb_elasticsearch.views import CWFacetedSearch

from cubicweb_francearchives.utils import merge_dicts
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
        """ Create a terms filter instead of bool containing term filters.  """
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


class PniaCWFacetedSearch(CWFacetedSearch):
    fields = [
        "did.unitid^6",
        "title^3",
        "did.unittitle^3",
        "component_texts^2",
        "content",
        "name",
        "manif_prog",
        "attachment",
        "alltext",
    ]
    facets = {
        "cw_etype": TermsFacet(field="cw_etype", size=FACET_SIZE),
        "escategory": TermsFacet(field="escategory", size=FACET_SIZE),
        "creation_date": DateHistogramFacet(
            field="creation_date", interval="month", min_doc_count=1
        ),
        # custom
        "unitid": TermsFacet(field="unitid", size=FACET_SIZE),
        "commemoration_year": HistogramFacet(
            field="commemoration_year", interval="1", min_doc_count=1
        ),
        "year": HistogramFacet(field="year", interval=100, min_doc_count=1),
        "publisher": TermsFacet(field="publisher", size=ALL_VALUES_SIZE),
        "digitized": TermsFacet(field="digitized"),
        "reftype": TermsFacet(field="reftype", size=FACET_SIZE),
        "originators": TermsFacet(field="originators", size=FACET_SIZE),
    }

    def query(self, search, query):
        if self.extra_kwargs.get("ancestors-query") and query:
            # we are in Section primary view
            search.query = dsl_query.Bool(must=Q("match", ancestors=query))
        else:
            search = super(PniaCWFacetedSearch, self).query(search, query)
        return self.fulltext_facet(search, query)

    def fulltext_facet(self, search, query):
        fulltext_query = self.extra_kwargs.get("fulltext_facet")
        if not fulltext_query:
            return search
        phrase = False
        for char in ('"', "'", xml_escape('"'), xml_escape("'")):
            # TODO - implement phrase + term
            if len(fulltext_query.split(char)) == 3:
                # TODO add this to most important queries, instead of single query ?
                phrase = True
                fulltext_query = fulltext_query.split(char)[1]
        if query:
            if phrase:
                search.query.filter.append(Q("multi_match", type="phrase", query=fulltext_query))
            else:
                search.query.filter.append(Q("multi_match", operator="and", query=fulltext_query))
        else:
            if phrase:
                must_query = Q("multi_match", type="phrase", query=fulltext_query)
            else:
                must_query = Q("multi_match", operator="and", query=fulltext_query)
            if search.query:
                search.query.filter.append(must_query)
            else:
                search.query = dsl_query.Bool(must=must_query)
        return search


class PniaFCFacetedSearch(PniaCWFacetedSearch):
    fields = [
        "did.unitid^6",
        "title^3",
        "did.unittitle^3",
        "name^3",
        "content^2",
        "content",
        "alltext",
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
        "alltext",
    ]


# TODO provide generic mechanism for missing query


class PniaCircularFacetedSearch(PniaCWFacetedSearch):
    facets = {
        "cw_etype": TermsFacet(field="cw_etype", size=FACET_SIZE),
        "escategory": TermsFacet(field="escategory", size=FACET_SIZE),
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
        # XXX using query because there is no sort in faceted_search
        # https://github.com/elastic/elasticsearch-dsl-py/issues/532
        search = super(PniaCircularFacetedSearch, self).query(search, query)
        return search.sort("-sort_date")


class PniaNewsContentFacetedSearch(PniaCWFacetedSearch):
    facets = {
        "cw_etype": TermsFacet(field="cw_etype", size=FACET_SIZE),
        "escategory": TermsFacet(field="escategory", size=FACET_SIZE),
    }

    def query(self, search, query):
        search = super(PniaNewsContentFacetedSearch, self).query(search, query)
        return search.sort("-start_date", "-creation_date")


class PniaCommemoCollectionFacetedSearch(PniaCWFacetedSearch):
    facets = {
        "cw_etype": TermsFacet(field="cw_etype", size=FACET_SIZE),
        "escategory": TermsFacet(field="escategory", size=FACET_SIZE),
    }

    def query(self, search, query):
        search = super(PniaCommemoCollectionFacetedSearch, self).query(search, query)
        return search.sort("-year")


class IndexFacetedSearchMixin(object):
    def query(self, search, query):
        queries = [Q("term", **{"index_entries.authority": self.form["indexentry"]})]
        search.query = dsl_query.Bool(must=queries)
        return self.fulltext_facet(search, query)


class PniaIndexEntryFacetedSearch(IndexFacetedSearchMixin, PniaCWFacetedSearch):
    pass


class PniaFCIndexEntryFacetedSearch(NoHighlightMixin, IndexFacetedSearchMixin, PniaFCFacetedSearch):
    pass


class PniaCmsSectionFacetedSearch(PniaCWFacetedSearch):
    facets = merge_dicts(
        {},
        PniaCWFacetedSearch.facets,
        {"ancestors": TermsFacet(field="ancestors", size=ALL_VALUES_SIZE)},
    )

    def query(self, search, query):
        search = super(PniaCmsSectionFacetedSearch, self).query(search, query)
        return search.sort("order", "-creation_date")


class PniaServiceFacetedSearch(PniaCWFacetedSearch):
    facets = {
        "cw_etype": TermsFacet(field="cw_etype", size=FACET_SIZE),
        "level": MissingNATermsFacet(field="level", missing=_("N/R"), size=FACET_SIZE),
        "escategory": TermsFacet(field="escategory", size=FACET_SIZE),
    }

    def query(self, search, query):
        # XXX using query because there is no sort in faceted_search
        # https://github.com/elastic/elasticsearch-dsl-py/issues/532
        search = super(PniaServiceFacetedSearch, self).query(search, query)
        return search.sort("sort_name")


FACETED_SEARCHES = {
    "default": PniaCWFacetedSearch,
    "newscontent": PniaNewsContentFacetedSearch,
    "circular": PniaCircularFacetedSearch,
    "section": PniaCmsSectionFacetedSearch,
    "service": PniaServiceFacetedSearch,
    "facomponent": PniaFCFacetedSearch,
    "findingaid": PniaFAFacetedSearch,
    "indexentry": PniaIndexEntryFacetedSearch,
    "facomponent_indexentry": PniaFCIndexEntryFacetedSearch,
    "commemocollection": PniaCommemoCollectionFacetedSearch,
}


class PniaDefaultFacetRenderer(object):
    template = get_template("facet.jinja2")
    item = (
        '<li class="{css}" style="{style}">'
        '    <a href="{url}" title="{alt}" class="facet__focusable-item">'
        "        {content} [{count}]"
        "    </a>"
        "</li>"
    )
    item_nolink = (
        '<li class="facet__value">'
        '  <span class="facet--nolink">{content} [{count}]</span>'
        "</li>"
    )
    filter_tags = True

    @staticmethod
    def build_content(req, content):
        return req._(content)

    def __init__(self, sort="count", items_size=FACET_SIZE, nr_tag="N/R"):
        assert sort in ("count", "item")
        self.item_sort = sort
        self.items_size = items_size
        self.nr_tag = nr_tag

    def __call__(self, req, bucket, facetid, facetlabel, searchcontext):
        # keep only items leading to more than 1 result
        bucket = self.build_bucket(bucket)
        if len(bucket) == 0:
            return None
        self.req = req
        self.facetid = facetid
        self.searchcontext = searchcontext
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

    def render_nolink_item(self, idx, tag, count, selected):
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
            if param_name in url_params:
                url_params[param_name] = None
            alt = _("deselect")
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
            if len(bucket) == 1:
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
        if content == "BaseContent":
            return req._(content)
        if content == "Service":
            return req._("archive-services-label")
        return req.__("%s_plural" % content)


class PniaAncestorsFacetRenderer(PniaDefaultFacetRenderer):
    item = (
        '<li data-eid="{eid}" class="{css}" style="{style}">'
        '    <a href="{url}" title="{alt}" class="facet__focusable-item">'
        "        {content} [{count}]"
        "   </a>"
        "</li>"
    )

    def render_nolink_item(self, idx, tag, count, selected):
        return self.render_item(idx, tag, count, selected)

    def render_item(self, idx, tag, count, selected):
        req = self.req
        # NOTE: section can either be a ``Section`` or a ``CommemoCollection``
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
    "ancestors": PniaAncestorsFacetRenderer(),
    "digitized": PniaDigitizedFacetRenderer(),
    "status": PniaStatusFacetRenderer(),
    "siaf_daf_signing_year": PniaSigningYearFacetRenderer(),
    "business_field": PniaDefaultFacetRenderer(sort="item"),
    "historical_context": PniaDefaultFacetRenderer(sort="item"),
    "document_type": PniaDefaultFacetRenderer(sort="item"),
    "action": PniaDefaultFacetRenderer(sort="item"),
}
