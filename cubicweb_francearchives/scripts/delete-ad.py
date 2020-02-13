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
import time
import argparse

from elasticsearch.helpers import bulk, scan
from elasticsearch.exceptions import ConnectionTimeout, SerializationError

from elasticsearch_dsl.connections import connections


LOGGER = logging.getLogger()


def get_connection(host):
    try:
        return connections.get_connection()
    except KeyError:
        es = connections.create_connection(hosts=host, timeout=20)
        return es


# XXX blunt duplication of ``cubicweb_francearchives.dataimport.es_bulk_index``
#     Importing it would require ``cubes.elasticsearch`` to be found and thus
#     the CW's ``adjust_sys_path`` trickery and I want to be able to use
#     the delete-ad script in a plain python environment.
def es_bulk_index(es, es_docs, max_retry=3, **kwargs):
    if not es:
        return
    numtry = 0
    while numtry < max_retry:
        try:
            bulk(es, es_docs, stats_only=True, **kwargs)
        except (ConnectionTimeout, SerializationError):
            LOGGER.warning("failed to bulk index in ES, will retry in 0.5sec")
            numtry += 1
            time.sleep(0.5)
        else:
            break


def count(es, index, doc_type, query=None):
    results = es.search(index=index, doc_type=doc_type, fields=(), body=query)
    return results["hits"]["total"]


def es_documents(es, index, doc_type, query=None):
    for doc in scan(es, index=index, doc_type=doc_type, fields=(), query=query):
        yield {
            "_op_type": "delete",
            "_index": index,
            "_type": doc["_type"],
            "_id": doc["_id"],
        }


def parse_cmdline():
    parser = argparse.ArgumentParser()
    parser.add_argument("publisher", help='the publisher label (e.g. "AD du Cantal")')
    parser.add_argument(
        "--es-host", default="http://localhost:9200", help="The ES host (default is localhost:9200)"
    )
    parser.add_argument(
        "--es-index",
        default="francearchives_all",
        help="The ES index (default is francearchives_all)",
    )
    return parser.parse_args()


def run():
    args = parse_cmdline()
    es = get_connection(args.es_host)
    print("deleting on {}/{}".format(args.es_host, args.es_index))
    nb_docs = count(
        es,
        index=args.es_index,
        doc_type="FAComponent,FindingAid",
        query={"query": {"match": {"publisher": args.publisher}}},
    )
    print("fetched {} documents".format(nb_docs))
    if nb_docs:
        answer = input("proceed ? [yes / no] ").strip().lower()  # noqa
        if answer != "yes":
            print("ok, aborting")
            return
        else:
            print("proceeding")

    es_docs = es_documents(
        es,
        index=args.es_index,
        doc_type="FAComponent,FindingAid",
        query={"query": {"match": {"publisher": args.publisher}}},
    )

    es_bulk_index(es, es_docs, raise_on_error=False)


if __name__ == "__main__":
    run()
