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
from pyramid.view import view_config


def initiate_tour_data(cnx):
    _ = cnx._
    return {
        "nextLabel": _("Next"),
        "prevLabel": _("Previous"),
        "doneLabel": _("Done"),
        "skipLabel": _("Close"),
        "hidePrev": True,
        "scrollTo": "tooltip",
        "autoPosition": False,
        "showBullets": False,
    }


@view_config(
    route_name="search-tour.json", renderer="json", http_cache=600, request_method=("GET", "HEAD")
)
def search_tour_data(request):
    cnx = request.cw_request
    intro_data = initiate_tour_data(cnx)
    _ = cnx._
    intro_data["steps"] = [
        {
            "intro": _("tour_search_intro"),
        },
        {
            "element": "#search-bar-form",
            "intro": _("tour_search_query"),
        },
        {
            "element": ".search-results__title",
            "intro": _("tour_search_results_number"),
            "position": "right",
        },
        {
            "element": ".search-results__sort-options",
            "intro": _("tour_search_results_sort_options"),
            "position": "right",
        },
        {
            "element": ".search-results__items-per-page",
            "intro": _("tour_search_number_items"),
            "position": "left",
        },
        {
            "element": "#search-results .document div",
            "intro": _("tour_search_result"),
        },
        {
            "element": ".search-summary",
            "intro": _("tour_search_summary"),
        },
        {
            "element": "#fulltext-facet",
            "intro": _("tour_search_facet_fulltext"),
        },
        {
            "element": ".facets",
            "intro": _("tour_search_facets"),
        },
        {
            "element": ".pagination",
            "intro": _("tour_search_results_pagination"),
        },
    ]
    return intro_data


@view_config(
    route_name="findingaid-tour.json",
    renderer="json",
    http_cache=600,
    request_method=("GET", "HEAD"),
)
def findingaid_tour_data(request):
    cnx = request.cw_request
    intro_data = initiate_tour_data(cnx)
    _ = cnx._
    intro_data["steps"] = [
        {
            "element": ".page-main-content h1",
            "intro": _("fi_tour_title"),
        },
        {
            "element": "#breadcrumbs",
            "intro": _("fi_tour_breadcrumbs"),
        },
        {
            "element": ".pdf-download-button",
            "intro": _("fi_tour_pdf"),
        },
        {
            "element": ".document-digit-versions",
            "intro": _("fi_tour_digit_versions"),
        },
        {
            "element": ".content-metadata-item .fi-context",
            "intro": _("fi_tour_context"),
        },
        {
            "element": ".detailed-path-list-item-active",
            "intro": _("fi_tour_fatree"),
        },
        {
            "element": ".main-properties.ir-indexes",
            "intro": _("fi_tour_indexes"),
        },
        {
            "element": ".service-site-button",
            "intro": _("fi_tour_goto_service"),
        },
        {
            "element": ".service-url-button",
            "intro": _("fi_tour_service_url"),
        },
        {
            "element": ".csv-download-button",
            "intro": _("fi_tour_download-cvs"),
        },
    ]
    return intro_data


@view_config(
    route_name="facomponent-tour.json",
    renderer="json",
    http_cache=600,
    request_method=("GET", "HEAD"),
)
def facomponent_tour_data(request):
    cnx = request.cw_request
    intro_data = initiate_tour_data(cnx)
    _ = cnx._
    intro_data["steps"] = [
        {
            "element": ".page-main-content h1",
            "intro": _("fa_tour_title"),
        },
        {
            "element": "#breadcrumbs",
            "intro": _("fi_tour_breadcrumbs"),
        },
        {
            "element": ".document-digit-versions",
            "intro": _("fi_tour_digit_versions"),
        },
        {
            "element": ".content-metadata-item .fi-context",
            "intro": _("fa_tour_context"),
        },
        {
            "element": ".detailed-path-list-item-active",
            "intro": _("fi_tour_fatree"),
        },
        {
            "element": ".main-properties.ir-indexes",
            "intro": _("fi_tour_indexes"),
        },
        {
            "element": ".service-site-button",
            "intro": _("fi_tour_goto_service"),
        },
        {
            "element": ".service-url-button",
            "intro": _("fi_tour_service_url"),
        },
        {
            "element": ".csv-download-button",
            "intro": _("fi_tour_download-cvs"),
        },
    ]
    return intro_data


def includeme(config):
    config.add_route("search-tour.json", "/search-tour.json")
    config.add_route("findingaid-tour.json", "/findingaid-tour.json")
    config.add_route("facomponent-tour.json", "/facomponent-tour.json")
    config.scan(__name__)
