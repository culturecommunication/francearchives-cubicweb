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
"""This script uses a service mapping definition to update
the 'publisher' field in both ElasticSearch and Postgresql accordingly.
"""
import logging

from elasticsearch.helpers import scan

from elasticsearch_dsl.connections import connections

from cubicweb_francearchives.dataimport import es_bulk_index
from cubicweb_francearchives.dataimport.ead import load_services_map


LOGGER = logging.getLogger()


PUBLISHER_MAPPINGS = {
    'FRAD005-1485 W.XML': 'FRAD005',
    'FRAD70': 'FRAD070',
    'FRA023': 'FRAD023',
    'FRAD0005': 'FRAD005',
    # 'FRAC006088': 'FRAC006088',
    'INVENTAIRE': 'FRSHD',
    'ETAT': 'FRSHD',
    'TEMP': 'FRAD078',
    'A011449479853LY6Z37': 'FRAD025',
    'A011449479854POTAPY': 'FRAD025',
    'A011449479854CJ3B3W': 'FRAD025',
    'A011449479856P01ZMJ': 'FRAD025',
    'A01144947985153MGCU': 'FRAD025',
    'A0114494798065WBUUB': 'FRAD025',
    'A011449479856L67FGR': 'FRAD025',
    'A011449479856PQFDIV': 'FRAD025',
    'A011449480146WZPPPW': 'FRAD025',
    'A011449479837ZELHO5': 'FRAD025',
    'A011449479855WEZDJB': 'FRAD025',
    'A0114494798443GFB0Y': 'FRAD025',
    'A011449479850DGO7XB': 'FRAD025',
    'A011449479851HRV9RU': 'FRAD025',
    'A011449479853GJSYHG': 'FRAD025',
    'A011449479856X94VJG': 'FRAD025',
    'A011449479854XNU4OO': 'FRAD025',
    'A011449479807QA4WJP': 'FRAD025',
    'A011449479809S7SUHD': 'FRAD025',
}


def get_connection(host):
    try:
        return connections.get_connection()
    except KeyError:
        es = connections.create_connection(hosts=host, timeout=20)
        return es


def update_publishers_in_database(cnx):
    """update publisher in the database

    return the old publisher / new publisher mapping
    """
    services = load_services_map(cnx)
    sqldata = []
    old_new_mapping = {}
    for old_pubname, service_code in PUBLISHER_MAPPINGS.items():
        service = services[service_code]
        new_pubname = service.publisher()
        sqldata.append({'service': service.eid,
                        'old_pubname': old_pubname,
                        'new_pubname': new_pubname})
        old_new_mapping[old_pubname] = new_pubname
    cu = cnx.cnxset.cu
    try:
        cu.executemany('UPDATE cw_findingaid '
                       'SET cw_publisher=%(new_pubname)s, cw_service=%(service)s '
                       'WHERE cw_publisher=%(old_pubname)s', sqldata)
    except Exception:
        cnx.exception('failed to update publishers')
        cnx.rollback()
        raise
    finally:
        cnx.commit()
    return old_new_mapping


def es_documents(es, index, doc_type, old_new_mapping):
    """generate bulk-update documents to update ES according to ``old_new_mapping``
    """
    for old_pubname, new_pubname in old_new_mapping.items():
        query = {"query": {"match": {"publisher": old_pubname}}}
        for doc in scan(es,
                        index=index,
                        doc_type=doc_type,
                        _source=('publisher',),
                        query=query):
            source = doc['_source']
            source['publisher'] = new_pubname
            yield {
                '_op_type': 'update',
                '_index': index,
                '_type': doc['_type'],
                '_id': doc['_id'],
                'doc': source,
            }


def main(cnx):
    old_new_mapping = update_publishers_in_database(cnx)
    es = get_connection(cnx.vreg.config['elasticsearch-locations'])
    es_docs = es_documents(
        es, index=cnx.vreg.config['index-name'] + '_all',
        doc_type='FAComponent,FindingAid',
        old_new_mapping=old_new_mapping)
    es_bulk_index(es, es_docs, raise_on_error=False)


if __name__ == '__main__':
    main(cnx)  # noqa
