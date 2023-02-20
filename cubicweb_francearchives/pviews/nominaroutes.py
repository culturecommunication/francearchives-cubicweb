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


import logging

from pyramid.view import view_config
from pyramid.response import Response
from pyramid.httpexceptions import HTTPNotFound

from cubicweb_francearchives.entities.cms import Service


LOG = logging.getLogger(__name__)


@view_config(route_name="nominarecords", request_method=("GET", "HEAD"))
def nominarecords_view(request):
    cwreq = request.cw_request
    viewsreg = cwreq.vreg["views"]
    view = viewsreg.select("nominarecords", cwreq, rset=None)
    return Response(viewsreg.main_template(cwreq, "main-template", rset=None, view=view))


@view_config(route_name="service-nominarecords", request_method=("GET", "HEAD"))
def service_documents_view(request):
    cwreq = request.cw_request
    service = Service.from_code(cwreq, request.matchdict["service"])
    if service is None:
        raise HTTPNotFound()
    cwreq.form.setdefault("es_service", service.eid)
    cwreq.form.setdefault("inventory", True)
    viewsreg = cwreq.vreg["views"]
    view = viewsreg.select("nominarecords", cwreq, rset=None)
    return Response(viewsreg.main_template(cwreq, "main-template", rset=None, view=view))


@view_config(route_name="agent-nominarecords", request_method=("GET", "HEAD"))
def agent_nominarecords(request):
    cwreq = request.cw_request
    rset = cwreq.find("AgentAuthority", eid=request.matchdict["eid"])
    if not rset:
        raise HTTPNotFound()
    viewsreg = cwreq.vreg["views"]
    view = viewsreg.select("agents-nomina", cwreq, rset=rset)
    return Response(viewsreg.main_template(cwreq, "main-template", rset=rset, view=view))


def includeme(config):
    config.add_route("nominarecords", "/basedenoms")
    config.add_route("service-nominarecords", "/basedenoms/{service}")
    config.add_route("agent-nominarecords", "agent/{eid}/nomina")
    config.scan(__name__)
