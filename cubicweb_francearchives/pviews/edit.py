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
"""edition-related views"""

import base64
import logging
import re
from datetime import datetime, date

from pyramid.response import Response
from pyramid.httpexceptions import HTTPConflict, HTTPBadRequest
from pyramid.view import view_config

from cubicweb import Binary


LOG = logging.getLogger(__name__)
DATE_RE = re.compile(r"(\d+)[-/](\d+)[-/](\d+)")


def get_by_uuid(cnx, etype, **kwargs):
    rset = cnx.find(etype, **kwargs)
    if len(rset) != 1:
        raise HTTPBadRequest("no entity for etype %r and params %r" % (etype, kwargs))
    return rset.one()


def parse_date(value):
    m = DATE_RE.search(value)
    if m is None:
        raise ValueError("date data %s does not match regexp %s" % (value, DATE_RE.pattern))
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def load_json_value(value, ttype):
    if ttype == "Bytes":
        return Binary(base64.b64decode(value))
    elif ttype in ("TZDatetime", "Datetime"):
        date, time = value.split(" ", 1)
        time = datetime.strptime(time, "%H:%M:%S")
        date = parse_date(date)
        return datetime(date.year, date.month, date.day, time.hour, time.minute, time.second)
    elif ttype == "Date":
        return parse_date(value)
    elif ttype in ("Time", "TZTime"):
        return datetime.strptime(value, "%H:%M:%S").time()
    else:
        return value


def split_subobjects(schema, etype, posted):
    eschema = schema.eschema(etype)
    entity_data = {}
    relations_data = {}
    for rschema in eschema.ordered_relations():
        relname = rschema.type
        if relname in posted:
            data = posted[relname]
            if rschema.final:
                ttype = rschema.targets(eschema.type)[0].type
                entity_data[relname] = load_json_value(data, ttype)
            else:
                relations_data[relname] = data
    return entity_data, relations_data


def naive_dt(dt):
    return dt.replace(microsecond=0, tzinfo=None)


def _get_modifications(previous_state, new_state):
    """compare two entity states and return modifications

    Parameters:
    -----------

    previous_state : dictionary of attributes, as generated by ISync
    new_state      : dictionary of attributes, as generated by ISync

    """
    modifications = {}
    for attrname, attrvalue in list(new_state.items()):
        curvalue = previous_state.get(attrname)
        if hasattr(curvalue, "tzinfo"):
            curvalue = naive_dt(curvalue)
        # Binary objects implement __eq__ but not __ne__
        if not (curvalue == attrvalue):
            modifications[attrname] = attrvalue
    return modifications


def get_uuid_attr(vreg, etype):
    if vreg.schema.eschema(etype).has_relation("uuid", "subject"):
        return "uuid"
    eclass = vreg["etypes"].etype_class(etype)
    uuid_attr = getattr(eclass, "uuid_attr", None)
    if uuid_attr is None:
        vreg.warning("%s class does not have uuid_attr skipping edition", etype)
        return
    return uuid_attr


def edit_object(cnx, etype, posted, previous_state=None, _done=None):
    if _done is None:
        _done = {}
    schema = cnx.vreg.schema
    eschema = schema.eschema(etype)
    entity_data, relation_data = split_subobjects(schema, etype, posted)
    uuid_attr = get_uuid_attr(cnx.vreg, etype)
    uuid = entity_data[uuid_attr]
    if uuid in _done:
        return _done[uuid], False  # safety belt, we should not have cycles
    # 1/ update entity attributes
    rset = cnx.find(etype, **{uuid_attr: uuid})
    if rset:
        entity = rset.one()
        previous_state = previous_state or entity.cw_adapt_to("ISync").build_put_body()
        modifications = _get_modifications(previous_state, entity_data)
        if modifications:
            entity.cw_set(**modifications)
        created = False
    else:
        entity = cnx.create_entity(etype, **entity_data)
        previous_state = {}
        created = True
    _done[uuid] = entity
    # 2/ update relations and recurse on related entities
    for rtype in relation_data:
        ttypes = (t.type for t in eschema.rdef(rtype).rtype.targets())
        for ttype in ttypes:
            target_uuid_attr = get_uuid_attr(cnx.vreg, ttype)
            rdef = eschema.rdef(rtype, targettype=ttype, takefirst=True)
            existing_uuids = set()
            previous_target_states = {}
            for rdata in previous_state.get(rtype, ()):
                existing_uuids.add(rdata[target_uuid_attr])
                previous_target_states[rdata[target_uuid_attr]] = rdata
            posted_uuids = {}
            targets = []
            targets_data = (t for t in relation_data[rtype] if t["cw_etype"] == ttype)
            for target_data in targets_data:
                target_uuid = target_data[target_uuid_attr]
                # recurse: create / edit related entity
                target, target_created = edit_object(
                    cnx, ttype, target_data, previous_target_states.get(target_uuid, {}), _done
                )
                posted_uuids[target_uuid] = target
            for target_uuid in set(posted_uuids) - existing_uuids:
                targets.append(posted_uuids[target_uuid])
            entity.cw_set(**{rtype: targets})
            for target_uuid in existing_uuids - set(posted_uuids):
                if rdef.composite:
                    cnx.find(ttype, **{target_uuid_attr: target_uuid}).one().cw_delete()
                else:
                    rql = (
                        "DELETE X {rtype} Y WHERE X is {etype}, "
                        "X {uuid_attr} %(x)s, Y is {ttype}, "
                        "Y {target_uuid_attr} %(y)s".format(
                            rtype=rtype,
                            etype=etype,
                            uuid_attr=uuid_attr,
                            ttype=ttype,
                            target_uuid_attr=target_uuid_attr,
                        )
                    )
                    cnx.execute(rql, {"x": uuid, "y": target_uuid})
    return entity, created


@view_config(route_name="update-cmsobject", request_method=("PUT",))
def put_cmsobject(request):
    cnx = request.cw_cnx
    posted = request.json
    if posted.get("uuid") and posted["uuid"] != request.matchdict["uuid"]:
        raise HTTPConflict("ko")
    etype = request.matchdict["etype"]
    uuid_attr = get_uuid_attr(cnx.vreg, etype)
    uuid_value = request.matchdict["uuid"]
    LOG.debug("will update %s, %s: %s (%s)", etype, uuid_attr, uuid_value, list(posted.keys()))
    posted[uuid_attr] = uuid_value
    section_uuid = posted.pop("parent-section", None)
    with cnx.security_enabled(write=False):
        entity, created = edit_object(cnx, etype, posted)
        if created and section_uuid:
            section = cnx.find("Section", uuid=section_uuid).one()
            section.cw_set(children=entity)
        cnx.commit()
    return Response("ok", status_code=201 if created else 200)


@view_config(route_name="update-cmsobject", request_method=("DELETE",))
def delete_cmsobject(request):
    cnx = request.cw_cnx
    etype = request.matchdict["etype"]
    uuid_value = request.matchdict["uuid"]
    uuid_attr = get_uuid_attr(cnx.vreg, etype)
    LOG.debug("will delete %s, %s: %s", etype, uuid_attr, uuid_value)
    entity = get_by_uuid(cnx, etype, **{uuid_attr: uuid_value})
    with cnx.security_enabled(write=False):
        entity.cw_delete()
        cnx.commit()
    return Response("ok")


@view_config(route_name="update-move", request_method=("POST",))
def move_object(request):
    cnx = request.cw_cnx
    entity = get_by_uuid(cnx, request.matchdict["etype"], uuid=request.matchdict["uuid"])
    try:
        newsection = get_by_uuid(cnx, "Section", uuid=request.json["to-section"])
    except KeyError as err:
        raise HTTPBadRequest("property %s is missing in request body" % err.args[0])
    if entity.reverse_children and entity.reverse_children[0].eid == newsection.eid:
        # entity is already in this section
        return Response("ok")  # NOTE: return 304 NotModified ?
    with cnx.security_enabled(write=False):
        newsection.cw_set(children=entity)
        cnx.commit()
    return Response("ok")


@view_config(route_name="nls-csvexport", renderer="csv")
def news_letter_csv_export(request):
    # override attributes of response
    cnx = request.cw_cnx
    data = cnx.execute(
        "Any E,D WHERE X is NewsLetterSubscriber, " "X email E, X creation_date D"
    ).rows
    filename = "newsletter.csv"
    request.response.content_disposition = "attachment;filename=" + filename
    return {"rows": data}


def includeme(config):
    config.add_route("update-cmsobject", "/_update/{etype}/{uuid}")
    config.add_route("update-move", "/_update/move/{etype}/{uuid}")
    config.add_route("nls-csvexport", "/nlsexport")
    config.scan(__name__)
