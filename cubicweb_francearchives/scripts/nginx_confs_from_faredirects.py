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

"""Create FindingAid and FAComponent nginx redirections from data stored in
fa_redirects sql table

"""

from collections import defaultdict

from itertools import chain
from cubicweb_francearchives.dataimport.ead import component_stable_id


def build_parents(facomp_rset):
    """
    :returns: dict parents: facomponent parent, dict comps: facomponent order
    """
    parents = {}
    comps = {}
    for facomponent_eid, component_order, f_parent, _ in facomp_rset:
        if f_parent:
            parents[facomponent_eid] = f_parent
        comps[facomponent_eid] = component_order
    return parents, comps


def fa_component_stable_id(fa, fi_stable_id, parents, comps):
    def iterparents(fa_eid, strict=True):
        """Return an iterator on the parents of the entity."""

        def _uptoroot(fa_eid):
            curr = fa_eid
            while True:
                curr = parents.get(curr)
                if curr is None:
                    break
                yield comps[curr]

        if not strict:
            return chain([comps[fa_eid]], _uptoroot(fa_eid))
        return _uptoroot(fa_eid)

    comp_path = [co for co in iterparents(fa.eid, strict=False)]
    comp_path.reverse()
    return component_stable_id(fi_stable_id, comp_path)


def write_nginx_confs(cnx):
    fi_count = 0
    records = []
    processed_services = set()
    res = cnx.system_sql(
        """
        SELECT from_stable_id, to_stable_id from fa_redirects ORDER BY from_stable_id;
    """
    ).fetchall()
    if not res:
        print("No data found in fa_redirects table")
        return
    for fi_old_stable_id, fi_new_stable_id in res:
        fi = cnx.find("FindingAid", stable_id=fi_new_stable_id)
        if not fi:
            print("Missing IR with the new_stable_id {}".format(fi_new_stable_id))
            continue
        fi = fi.one()
        facomp_rset = cnx.execute(
            """
            Any F, C, P, FSI WHERE F finding_aid X,
            X stable_id %(s)s, F component_order C,
            F stable_id FSI, F parent_component P?
        """,
            {"s": fi_new_stable_id},
        )
        parents, comps = build_parents(facomp_rset)
        if fi_new_stable_id != fi_old_stable_id:
            records.append(
                {
                    "from_stable_id": fi_old_stable_id,
                    "to_stable_id": fi_new_stable_id,
                    "code": fi.service[0].code,
                    "etype": fi.cw_etype.lower(),
                }
            )
            fi_count += 1
        else:
            print(
                "FindingAid {}: new stable_id and old stable_id are identical".format(
                    fi_new_stable_id
                )
            )
        for fa in facomp_rset.entities():
            if fa.component_order is None:
                continue
            fa_old_stable_id = fa_component_stable_id(fa, fi_old_stable_id, parents, comps)
            fa_new_stable_id = fa.stable_id
            if fa_new_stable_id != fa_old_stable_id:
                records.append(
                    {
                        "from_stable_id": fa_old_stable_id,
                        "to_stable_id": fa_new_stable_id,
                        "code": fi.service[0].code,
                        "etype": fa.cw_etype.lower(),
                    }
                )
            else:
                print(
                    "FAComponent {}: new stable_id and old stable_id are identical".format(
                        fa_new_stable_id
                    )
                )

    print("\n Processed {} FindingAid".format(fi_count))
    print("\n Processed data for {} services".format(", ".join(list(processed_services))))
    print("\n Find {} redirections".format(len(records)))
    write_nginx_files(cnx, records)


def write_nginx_files(cnx, records):
    """
    Write ngix config files for redirection.

    Exemple of lines:
        ~francearchives.fr/findingaid/a3a85ba9c9c9b9ebf1935895af0ad959f615c178$ https://francearchives.fr/findingaid/0d07672aa789ecb127a2c580c80213a803609689;  # noqa
    """
    base_url = cnx.vreg.config.get("consultation-base-url")
    services = defaultdict(list)
    for r in records:
        f = "~francearchives.fr/{}/{}/?$".format(r["etype"], r["from_stable_id"])
        to = "{}/{}/{};".format(base_url, r["etype"], r["to_stable_id"])
        services[r["code"]].append(("{} {}".format(f, to)))
    nginx_dir = cnx.vreg.config.get("nginx-configs")
    for service, values in list(services.items()):
        with open("{}/redirect-old-stable_id_map_{}.conf".format(nginx_dir, service), "w") as outf:
            outf.write("\n".join(values))


if __name__ == "__main__":
    write_nginx_confs(cnx)  # noqa
