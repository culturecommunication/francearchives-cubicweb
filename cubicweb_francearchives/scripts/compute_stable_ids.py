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
"""
Recompute FindingAid and FAComponent stable ids by services only
for OIA harvested services

ElasticSearch reindexing is needed after the script is done

1/ delete FAComponent and FindinAid entries for services, f.e :

  curl -H content-type:application/json -XPOST
  'host/index/_doc/_delete_by_query?pretty' -d
  '{"query": {"bool": {"must": [{"term": {"publisher": "AD du Cher"}},
  {"term": {"cw_etype": "FindingAid"}}]}}}'


  curl -H content-type:application/json -XPOST
  'host/index/_doc/_delete_by_query?pretty' -d
  '{"query": {"bool": {"must": [{"term": {"publisher": "AD du Cher"}},
  {"term": {"cw_etype": "FAComponent"}}]}}}

 2/ run scripts/index-in-es-by-service.py to reindex services
    python index-in-es-by-service.py "AD du Cher" instance --es-index=index

"""

from itertools import chain
from cubicweb_francearchives.dataimport import usha1
from cubicweb_francearchives.dataimport.ead import component_stable_id


def build_parents(code):
    parents = {}
    comps = {}
    for f_eid, component_order, f_parent in rql(  # noqa
        "Any F, C, P WHERE F finding_aid X, "
        "X service S, F component_order C, "
        "F parent_component P?, S code %(c)s",
        {"c": code},
    ):
        if f_parent:
            parents[f_eid] = f_parent
        comps[f_eid] = component_order
    return parents, comps


def fa_component_stable_id(fa, fi_stable_id, parents, comps):
    def iterparents_bis(fa_eid, strict=True):
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

    comp_path = [co for co in iterparents_bis(fa.eid, strict=False)]
    comp_path.reverse()
    return component_stable_id(fi_stable_id, comp_path)


def main(serivces):
    sql = cnx.system_sql  # noqa
    for code in services:
        print("service %s" % code)
        parents, comps = build_parents(code)
        fis = rql(  # noqa
            "Any X, SI, E WHERE X is FindingAid, "
            "X eadid E, X stable_id SI, "
            "X service S, S code %(c)s",
            {"c": code},
        )
        print("found %s FindingAid" % len(fis))
        for fi in fis.entities():
            fi_attrs = {}
            fi_stable_id_old = fi.stable_id
            fi_stable_id_new = usha1(fi.eadid)
            if fi_stable_id_new != fi_stable_id_old:
                fi_attrs = {"s": fi_stable_id_new, "e": fi.eid}
                sql(
                    """UPDATE cw_esdocument set cw_doc = jsonb_set(cw_doc::jsonb, '{{stable_id}}', '"{}"') where cw_entity = %(e)s""".format(  # noqa
                        fi_attrs["s"]
                    ),
                    fi_attrs,
                )
                sql(
                    """UPDATE cw_esdocument set cw_doc = jsonb_set(cw_doc::jsonb, '{{fa_stable_id}}', '"{}"') where cw_entity = %(e)s""".format(  # noqa
                        fi_attrs["s"]
                    ),
                    fi_attrs,
                )
            fas = rql(  # noqa
                "Any F, SI WHERE F finding_aid X, " "F stable_id SI, " "X eid %(e)s",
                {"e": fi.eid},
            )
            print("found %s FAComponents" % len(fas))
            for fa in fas.entities():
                if fa.stable_id != fa_component_stable_id(fa, fi_stable_id_old, parents, comps):
                    # do not continue if we dont have the same old stable_id
                    print("FaComponent stable_id computing failed for %s" % fa.absolute_url())
                    continue
                # compte the new stable_id
                fa_stable_id_new = fa_component_stable_id(fa, fi_stable_id_new, parents, comps)
                if fa_stable_id_new != fa.stable_id:
                    attrs = {"s": fa_stable_id_new, "e": fa.eid, "fi_st": fi_stable_id_new}
                    sql(
                        "UPDATE cw_facomponent SET cw_stable_id = %(s)s WHERE cw_eid = %(e)s", attrs
                    )
                    sql(
                        """UPDATE cw_esdocument set cw_doc = jsonb_set(cw_doc::jsonb, '{{stable_id}}', '"{}"') where cw_entity = %(e)s""".format(  # noqa
                            attrs["s"]
                        ),
                        attrs,
                    )
                    sql(
                        """UPDATE cw_esdocument set cw_doc = jsonb_set(cw_doc::jsonb, '{{fa_stable_id}}', '"{}"') where cw_entity = %(e)s""".format(  # noqa
                            attrs["fi_st"]
                        ),
                        attrs,
                    )
            # update FindingAid stable id. This will trigger the update on published
            if fi_attrs:
                sql("UPDATE cw_findingaid SET cw_stable_id = %(s)s WHERE cw_eid = %(e)s", fi_attrs)

    cnx.commit()  # noqa


if __name__ == "__main__":
    import sys

    services = sys.argv[4]
    services = services.split(",")
    main(services)
