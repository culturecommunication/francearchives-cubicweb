# -*- coding: utf-8 -*-
#
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2021
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


from cubicweb.rset import ResultSet
from elasticsearch.exceptions import ConnectionError, RequestError

from logilab.common.decorators import cachedproperty

from cwtags import tag as T
from cubicweb import _
from cubicweb.predicates import match_form_params

from cubicweb_francearchives.views import rebuild_url

from cubicweb_francearchives.entities.nomina import nomina_translate_codetype
from cubicweb_francearchives.views.search import FakeResponse, PniaElasticSearchView, InventoryMixin
from cubicweb_francearchives.views.search.facets import NominaFacetedSearch


class PniaNominaElasticSearchView(PniaElasticSearchView):
    __regid__ = "nominarecords"
    items_per_page_options = [100, 200]
    default_items_per_page = 100
    text_facets = ["es_forenames", "es_names", "es_locations"]
    title = _("Search in the name base")
    service_facet_name = "service"

    def breadcrumbs(self):
        breadcrumbs = [(self._cw.build_url(""), self._cw._("Home"))]
        breadcrumbs.append((None, self._cw._(self.title)))
        return breadcrumbs

    def add_css(self):
        self._cw.add_css("css/font-awesome.css")

    def add_js(self):
        self._cw.add_js("cubes.pnia_search.js")

    @cachedproperty
    def get_selected_services_names(self):
        value = self._cw.form.get("es_service", None)
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

    def translate_acte_type(self, acte_type):
        return nomina_translate_codetype(self._cw, acte_type)

    @cachedproperty
    def xiti_chapters(self):
        return ["NominaRecords", self.__regid__]

    def template_context(self):
        ctx = super().template_context()
        ctx.update(
            {
                "nomina": True,
                "query_forenames": self._cw.form.get("es_forenames", ""),
                "query_names": self._cw.form.get("es_names", ""),
                "query_locations": self._cw.form.get("es_locations", ""),
                "query_fulltext": self._cw.form.get("fulltext_facet", ""),
                "display_nomina_search": False,
            }
        )
        return ctx

    def reset_all_facets_link(self):
        """Creates a URL which resets the values from the facets to display

        The value of the initial query (parameter q) is kept
        as well as values which come from other SearchView
        """
        url_params = {}
        facets = self.facets_to_display
        for facet in facets:
            url_params["es_{}".format(facet[0])] = None
        for key in self.text_facets:
            url_params[key] = None
        url_params["fulltext_facet"] = None
        url_params["es_date_min"] = None
        url_params["es_date_max"] = None
        return rebuild_url(self._cw, **url_params)

    def search_summary(self):
        facets = self._cw.form
        summary = []
        inventory = facets.pop("inventory", None)
        facets_to_display = self.facets_to_display
        service_labels = {}
        for key, value in facets.items():
            summary_value = {}
            if key in self.skip_in_summary:
                continue
            if key.startswith("es_"):
                # get the facet label requires to remove the "es_" substring
                facetlabel = [x[1] for x in facets_to_display if x[0] == key[3:]]
                if key == "es_service" and value:
                    service_labels = self.get_selected_services_names
                    if inventory:
                        if service_labels:
                            inventory = list(service_labels.values())[0]
                        else:
                            inventory = ""
                        continue
                    summary_value["name"] = value
                if key == "es_date_min" and value:
                    summary_value["name"] = self._cw._("date-min-label")
                elif key == "es_date_max" and value:
                    summary_value["name"] = self._cw._("date-max-label")
                elif len(facetlabel) > 0:
                    summary_value["name"] = facetlabel[0]
                elif key in self.text_facets:
                    summary_value["name"] = self._cw._(key.split("es_")[1].capitalize())
                else:
                    continue
                if not isinstance(value, (list, tuple)):
                    value = [value]
                value = [str(val).strip() for val in value if val]
                data = []
                for val in value:
                    if val:
                        url_params = {key: list(set(value).difference([val]))}
                        reset_url = rebuild_url(self._cw, replace_keys=True, **url_params)
                        if key == "es_service":
                            if val.isnumeric():
                                val = service_labels.get(int(val), val)
                        elif key == "es_acte_type":
                            val = self.translate_acte_type(val)
                        data.append([val, reset_url])
                if data:
                    summary_value["value"] = data
                    summary.append(summary_value)
            elif key == "fulltext_facet":
                value = value.strip()
                if value:
                    reset_url = rebuild_url(self._cw, **{key: None})
                    summary.insert(
                        0, {"name": self._cw._("Contains"), "value": ((value, reset_url),)}
                    )
        context = {}
        if inventory:
            context["inventory"] = inventory
        return {"context": context, "summary": summary}

    @cachedproperty
    def cached_search_response(self):
        query_string = self._cw.form.get("q")
        if hasattr(self, "_esresponse"):
            return self._esresponse, query_string
        try:
            self._esresponse = self.do_search(query_string)
        except Exception as err:
            self.exception(err)
            self._esresponse = FakeResponse()

        return self._esresponse, query_string

    def customize_search(self, query_string, facet_selections, start=0, stop=10, **kwargs):
        """
        This is where one can customize the search by modifying the
        query string and facet selection in an inherited class.

        """
        stop = stop if stop != 10 else self.default_items_per_page
        cwconfig = self._cw.vreg.config
        index_name = cwconfig["nomina-index-name"]
        for facet_searched in list(facet_selections.keys()):
            if facet_searched not in list(NominaFacetedSearch.facets.keys()):
                del facet_selections[facet_searched]
        kwargs["fulltext_facet"] = self._cw.form.get("fulltext_facet")
        kwargs["es_date_max"] = self._cw.form.get("es_date_max")
        kwargs["es_date_min"] = self._cw.form.get("es_date_min")
        for facet in self.text_facets:
            kwargs[facet] = self._cw.form.get(facet)
        kwargs["authority"] = self._cw.form.get("authority")
        return NominaFacetedSearch(
            query_string, facet_selections, doc_type="_doc", index=index_name, **kwargs
        )[start:stop]

    @property
    def facets_to_display(self):
        """
        Method to list facets to display (can be customized)
        """
        _ = self._cw._
        return (
            ("service", _("publishers_facet")),
            ("acte_type", _("acte_type_facet")),
        )

    def rset_from_response(self, response):
        """transform an ES response into a CubicWeb rset

        This consists in iterating on current panigated response and
        inspect the ``cw_etype`` and ``eid`` document fields.
        """
        req = self._cw
        descr, rows = [], []
        for idx, result in enumerate(response):
            if not result.eid:
                # must not happen
                continue
            else:
                eid = result.eid
            descr.append(("NominaRecord", "String"))
            rows.append([eid, "foo"])
        rset = ResultSet(rows, "Any X WHERE X is NominaRecord", description=descr)
        rset.req = req
        return rset

    def call(self, context=None, **kwargs):
        self.add_js()
        self.add_css()
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
            self.exception(f"Key error on {self.__class__} do_search")
            response = FakeResponse()

        date_params = self._cw.form.copy()
        facet_date_unfolded = any((p in date_params for p in ("es_date_min", "es_date_max")))
        es_date_min = date_params.pop("es_date_min", "")
        es_date_max = date_params.pop("es_date_max", "")
        date_params.pop("page", None)
        for key, value in date_params.items():
            if not isinstance(value, (tuple, list)):
                date_params[key] = [value]

        first_previous_pages, next_last_pages = self.pagination(response.hits.total.value)
        self.w(
            self.template.render(
                req=self._cw,
                _=self._cw._,
                response=response,
                display_facets=True,
                facets=self.build_facets(response, context),
                results_title=self.format_results_title(response),
                display_fulltext_facet=False,
                search_results=self.build_results(response),
                search_summary=self.search_summary(),
                reset_all_facets_link=self.reset_all_facets_link(),
                first_previous_pages=first_previous_pages,
                next_last_pages=next_last_pages,
                header=self.get_header_attrs(),
                items_per_page_links=self.items_per_page_links(),
                display_sort_options=False,
                display_date_facet=True,
                es_date_min=es_date_min,
                es_date_max=es_date_max,
                date_params=date_params,
                facet_date_unfolded=facet_date_unfolded,
                page_number_params=self.page_number_params(),
                page_number_form_action=self._cw.build_url(
                    self._cw.relative_path(includeparams=False)
                ),
                current_page=int(self._cw.form.get("page", 1)),
                number_of_pages=self.number_of_pages(response.hits.total.value),
            )
        )


class InventoryNominaPrimaryView(InventoryMixin, PniaNominaElasticSearchView):
    __select__ = PniaNominaElasticSearchView.__select__ & match_form_params(inventory=True)

    @cachedproperty
    def service_name(self):
        service = self.get_selected_services_names.values()
        if service:
            return list(service)[0]

    def breadcrumbs(self):
        breadcrumbs = [
            (self._cw.build_url(""), self._cw._("Home")),
            (self._cw.build_url("basedenoms"), self._cw._("Search in the name base")),
        ]
        if self.service_name:
            breadcrumbs.append((None, self.service_name))
        return breadcrumbs

    def get_header_attrs(self):
        _ = self._cw._
        if self.service_name:
            return {"title": "{}{}{}".format(self.service_name, _(":"), _("see all the names"))}
        return _("see all the names")
