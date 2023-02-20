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
from collections import defaultdict

from cubicweb import _


def alignment_csv(req):
    headers = (_("index_entry"), _("index_url"), _("aligned_url"))
    rows = []
    rset = req.execute(
        "Any X,XN,N,AN,A WHERE "
        "X is IN (AgentAuthority, LocationAuthority, SubjectAuthority), "
        "X label N, X is XE, XE name XN, "
        "X same_as A, A is AE, AE name AN, "
        "NOT A is IN (ExternalUri, NominaRecord)"
    )
    for index_eid, index_etype, index_preflabel, align_etype, align_eid in rset.rows:
        index_etype = index_etype[: -len("Authority")].lower()
        rest = align_etype.lower()
        props = {
            "index_entry": index_preflabel,
            "index_url": req.build_url("{}/{}".format(index_etype, index_eid)),
            "aligned_url": req.build_url("{}/{}".format(rest, align_eid)),
        }
        rows.append([(props[h] or "") for h in headers])

    # nominarecord
    rset = req.execute(
        "Any X,XN,N,AN,A,AI WHERE "
        "X is IN (AgentAuthority, LocationAuthority, SubjectAuthority), "
        "X label N, X is XE, XE name XN, "
        "X same_as A, A is AE, AE name AN, A stable_id AI, "
        "A is NominaRecord"
    )
    for (
        index_eid,
        index_etype,
        index_preflabel,
        align_etype,
        align_eid,
        align_stableid,
    ) in rset.rows:
        index_etype = index_etype[: -len("Authority")].lower()
        props = {
            "index_entry": index_preflabel,
            "index_url": req.build_url("{}/{}".format(index_etype, index_eid)),
            "aligned_url": req.build_url("basedenoms/{}".format(align_stableid)),
        }
        rows.append([(props[h] or "") for h in headers])

    # external url
    rset = req.execute(
        "Any X,XN,N,AU WHERE "
        "X is IN (AgentAuthority, LocationAuthority, SubjectAuthority), "
        "X label N, X is XE, XE name XN, "
        "X same_as A, A is ExternalUri, A uri AU"
    )
    for index_eid, index_etype, index_preflabel, align_url in rset.rows:
        index_etype = index_etype[: -len("Authority")].lower()
        props = {
            "index_entry": index_preflabel,
            "index_url": req.build_url("{}/{}".format(index_etype, index_eid)),
            "aligned_url": align_url,
        }
        rows.append([(props[h] or "") for h in headers])
    return {"rows": rows, "headers": headers}


def all_indices(req, auth_type, etype):
    if etype == "AgentAuthority":
        query = (
            "(Any A,AL,ANT,T WHERE A is AgentAuthority, A label AL, "
            " AN authority A, AN type ANT, AN index T)"
            " UNION "
            '(Any A,AL,"persname",T WHERE A is AgentAuthority, A label AL, '
            " T related_authority A)"
        )
    elif etype == "SubjectAuthority":
        query = (
            '(Any A,AL,"subject",T WHERE A is SubjectAuthority, A label AL, '
            " AN authority A, AN index T) "
            " UNION "
            '(Any A,AL,"subject",T WHERE A is SubjectAuthority, A label AL, '
            " T related_authority A)"
        )
    else:
        query = (
            '(Any A,AL,"geogname",T WHERE A is LocationAuthority, A label AL, '
            " AN authority A, AN index T) "
            " UNION "
            '(Any A,AL,"geogname",T WHERE A is LocationAuthority, A label AL, '
            " T related_authority A)"
        )
    return req.execute(query)


def indices_csv(req, auth_type):
    types = {
        "agent": "AgentAuthority",
        "subject": "SubjectAuthority",
        "location": "LocationAuthority",
    }
    data = defaultdict(dict)
    for eid, preflabel, index_type, target_eid in all_indices(
        req, auth_type, types[auth_type]
    ).rows:
        target = req.entity_from_eid(target_eid)
        docs = data[eid].get("docs", [])
        docs.append(target.absolute_url())
        data[eid].update({"preflabel": preflabel, "index_type": index_type, "docs": docs})
    headers = (_("index_entry"), _("index_type"), _("documents"))
    rows = []
    for eid, values in data.items():
        props = {
            "index_entry": values["preflabel"],
            "index_type": values["index_type"],
            "documents": "$$$".join(values["docs"]),
        }
        rows.append([(props[h] or "") for h in headers])
    return {"rows": rows, "headers": headers}
