# -*- coding: utf-8 -*-
#
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2022
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

"""small es utility functions"""
import logging

from cubicweb_francearchives.dataimport import es_bulk_index

from cubicweb_elasticsearch.es import get_connection


def get_es_connection(cnx, index_name, log):
    es = get_connection(
        {
            "elasticsearch-locations": cnx.vreg.config["elasticsearch-locations"],
            "index-name": index_name,
            "elasticsearch-verify-certs": cnx.vreg.config["elasticsearch-verify-certs"],
            "elasticsearch-ssl-show-warn": cnx.vreg.config["elasticsearch-ssl-show-warn"],
        }
    )
    if es:
        return es
    if log:
        log.error("-> no es connection.abort")
    else:
        print("-> no es connection.abort")


def delete_autority_from_es(cnx, eids, log=None):
    """Delete authorities from all es indexes"""

    def docs_to_delete(es, eids, index_name):
        if log:
            log.info("es [%s]: deleting %s", index_name, eids)
        else:
            print(f"es [{index_name}]: deleting {eids}")
        for eid in eids:
            yield {
                "_op_type": "delete",
                "_index": index_name,
                "_type": "_doc",
                "_id": eid,
            }

    config = cnx.vreg.config
    indexes = [f"{config['index-name']}_suggest"]
    if config.get("published-index-name"):  # only in cms
        indexes.append(f"{config['published-index-name']}_suggest")
    if config["enable-kibana-indexes"]:
        indexes.append(config["kibana-authorities-index-name"])
    for index_name in indexes:
        es = get_es_connection(cnx, index_name, log)
        if not es:
            return
        es_docs = docs_to_delete(es, eids, index_name)
        es_bulk_index(es, es_docs, raise_on_error=False)


def update_index_mapping(cnx, index_name, mapping, log=None):
    if not log:
        log = logging.getLogger("update_index_mapping")
    es = get_es_connection(cnx, index_name, log)
    es.indices.put_mapping(index=index_name, body=mapping, doc_type="_doc", include_type_name=True)
