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


def reindex_authority(cnx, eid):
    """
    reindex related FindingAid, FAComponent, etc for both
    indexes
    """
    indexer = cnx.vreg["es"].select("indexer", cnx)
    index_name = indexer.index_name
    es = indexer.get_connection()
    published_indexer = cnx.vreg["es"].select("indexer", cnx, published=True)
    docs = []
    published_docs = []
    for fa in cnx.execute(
        "DISTINCT Any FA WHERE X eid %(eid)s, I authority X, I index FA", {"eid": eid}
    ).entities():
        serializable = fa.cw_adapt_to("IFullTextIndexSerializable")
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
        if published_indexer:
            published = True
            if fa.cw_etype in ("FindingAid", "FAComponent"):
                if fa.cw_etype == "FindingAid":
                    wf = fa.cw_adapt_to("IWorkflowable")
                else:
                    wf = fa.finding_aid[0].cw_adapt_to("IWorkflowable")
                published = wf and wf.state == "wfs_cmsobject_published"
            if published:
                published_docs.append(
                    {
                        "_op_type": "index",
                        "_index": published_indexer.index_name,
                        "_type": "_doc",
                        "_id": serializable.es_id,
                        "_source": json,
                    }
                )
        print("docs", len(docs))
        print("published_docs", len(published_docs))
        if len(docs) > 30:
            es_bulk_index(es, docs)
            if len(published_docs):
                es_bulk_index(es, published_docs)
            docs = []
            published_docs = []
    es_bulk_index(es, docs)
    if published_docs:
        es_bulk_index(es, published_docs)
