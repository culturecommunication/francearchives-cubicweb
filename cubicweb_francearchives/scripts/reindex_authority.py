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
this script reindex authority's related FindingAid, FAComponent
"""
from cubicweb_francearchives.dataimport import es_bulk_index


def es_index(es, index_name, rset):
    docs = []
    for e in rset.entities():
        if e.cw_etype in ("FAComponent", "FindingAid"):
            print(" -> Indexing {} {} {}".format(e.cw_etype, e.eid, e.stable_id))
        else:
            print(" -> Indexing {} {}".format(e.cw_etype, e.eid))

        serializable = e.cw_adapt_to("IFullTextIndexSerializable")
        if not serializable:
            print(
                "\n -> Entity {} {} is not adaptable to IFullTextIndexSerializable".format(
                    e.cw_etype, e.eid
                )
            )
            continue
        json = serializable.serialize()
        if not json:
            continue
        docs.append(
            {
                "_op_type": "index",
                "_index": index_name,
                "_type": "_doc",
                "_id": serializable.es_id,
                "_source": json,
            }
        )
        if len(docs) > 30:
            es_bulk_index(es, docs)
            docs = []
    es_bulk_index(es, docs)


def get_related_docs(cnx, adapted, published=False):
    return cnx.execute(
        """Any F WITH F BEING ({queries})""".format(
            queries=" UNION ".join(adapted.related_docs_queries(published=published))
        ),
        {"eid": adapted.entity.eid},
    )


def reindex_authority(cnx, eid):
    """
    reindex related FindingAid, FAComponent, etc for both
    indexes
    """
    indexer = cnx.vreg["es"].select("indexer", cnx)
    unpublished_index_name = indexer.index_name
    es = indexer.get_connection()
    published_index_name = cnx.vreg["es"].select("indexer", cnx, published=True).index_name
    rset = cnx.execute("Any X WHERE X eid %(eid)s", {"eid": eid})
    if not rset:
        print("\n -> No Authority with eid {} found".format(eid))
        return
    authority = rset.one()
    adapted = authority.cw_adapt_to("ISuggestIndexSerializable")
    for index_name, is_published in (
        (unpublished_index_name, False),
        (published_index_name, True),
    ):
        related_rset = get_related_docs(cnx, adapted, published=is_published)
        print(
            " -> Found {} {} related entities for {} {}".format(
                related_rset.rowcount,
                "published" if is_published else "draft",
                authority.cw_etype,
                authority.eid,
            )
        )
        es_index(es, index_name, related_rset)
