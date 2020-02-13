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
from pyramid.view import view_config
from pyramid.httpexceptions import HTTPNotFound, HTTPFound
from pyramid.response import Response

from cubicweb.pyramid.resources import ETypeResource, EntityResource

from cubicweb_francearchives.pviews.helpers import update_headers
from cubicweb_francearchives.pviews.predicates import (
    MultiAcceptPredicate,
    SegmentIsEnlargedETypePredicate,
)
from cubicweb_francearchives.xy import conjunctive_graph, add_statements_to_graph, namespaces


class ApplicationSchema(object):
    """The root schema resource, describing the application schema."""

    translations = {
        "article": "BaseContent",
        "articles": "BaseContent",
        "actualite": "NewsContent",
        "actualites": "NewsContent",
        "circulaire": "Circular",
        "circulaires": "Circular",
        "services": "Service",
        "annuaire": "Service",
        "agent": "AgentAuthority",
        "location": "LocationAuthority",
        "subject": "SubjectAuthority",
        "subjectname": "Subject",
    }

    def __init__(self, request):
        self.request = request

    def __getitem__(self, value):
        vreg = self.request.registry["cubicweb.registry"]
        try:
            etype = self.translations[value]
        except KeyError:
            try:
                etype = vreg.case_insensitive_etypes[value.lower()]
            except KeyError:
                raise KeyError(value)
        return ETypeResource(self.request, etype)


RDF_MAPPING = {
    "application/ld+json": "json-ld",
    "text/rdf+n3": "n3",
    "text/plain": "nt",
    "application/n-triples": "nt",
    "application/x-turtle": "turtle",
    "application/rdf+xml": "pretty-xml",
}


@view_config(
    route_name="restpath",
    request_method=("GET", "HEAD"),
    multi_accept=list(RDF_MAPPING.keys()),
    context=EntityResource,
)
def rdf_view(context, request):
    content_type = request.accept.best_match(list(RDF_MAPPING.keys()))
    fmt = RDF_MAPPING[content_type]
    entity = context.rset.one()
    rdf_adapter = entity.cw_adapt_to("rdf.edm")
    if rdf_adapter is None:
        raise HTTPNotFound()
    graph = conjunctive_graph()
    add_statements_to_graph(graph, rdf_adapter)
    return Response(graph.serialize(format=fmt, context=namespaces), content_type=content_type)


@view_config(route_name="restpath", request_method=("GET", "HEAD"), context=EntityResource)
def primary_view(context, request):
    cwreq = request.cw_request
    viewsreg = cwreq.vreg["views"]
    entity = context.rset.one()
    to_entity = getattr(entity, "grouped_with", None)
    if to_entity:
        raise HTTPFound(location=to_entity[0].absolute_url())
    view = viewsreg.select("primary", cwreq, rset=context.rset)
    return update_headers(
        cwreq,
        Response(viewsreg.main_template(cwreq, "main-template", rset=context.rset, view=view)),
    )


@view_config(route_name="restpath", request_method=("GET", "HEAD"), context=ETypeResource)
def list_view(context, request):
    cwreq = request.cw_request
    viewsreg = cwreq.vreg["views"]
    # XXX use self._cw.form for backward compat for now, we'll refactor
    #     search.py later.
    cwreq.form.update(
        {
            "vid": "esearch",
            "search": "",
            "es_cw_etype": context.etype,
            "restrict_to_single_etype": True,
        }
    )
    view = viewsreg.select("esearch", cwreq, rset=None)
    return update_headers(
        cwreq,
        Response(viewsreg.main_template(cwreq, "main-template", rset=context.rset, view=view)),
    )


@view_config(
    route_name="children-relation", renderer="json", http_cache=600, request_method=("GET", "HEAD")
)
def children_relation(request):
    cwreq = request.cw_request
    rset = cwreq.execute("Any X, JSON_AGG(Y) GROUPBY X WHERE X children Y", build_descr=False)
    return dict(rset.rows)


def includeme(config):
    config.add_view_predicate("multi_accept", MultiAcceptPredicate)
    config.add_route_predicate("segment_is_enlarged_etype", SegmentIsEnlargedETypePredicate)
    config.add_route("children-relation", "/_children")
    config.add_route(
        "restpath",
        "*traverse",
        factory=ApplicationSchema,
        segment_is_enlarged_etype=("traverse", 0, ApplicationSchema.translations),
    )
    config.scan(__name__)
