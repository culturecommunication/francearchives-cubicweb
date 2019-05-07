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
call: python index-in-es-by-service.py <publisher_name> <instance> --es-index=<index>

ex: python index-in-es-by-service.py "AD du Cher" instance --es-index=index

"""
from __future__ import print_function
import argparse

from elasticsearch.helpers import parallel_bulk

from cubicweb_francearchives import admincnx


CHUNKSIZE = 100000


def get_indexable_fa(cnx, etype, publisher, chunksize=100000):
    rqlpart = 'X publisher %(p)s, ' if etype == 'FindingAid' else \
        'X finding_aid FA, FA publisher %(p)s, '
    lasteid = 0
    rql = (
        'Any X, E, D, U, S ORDERBY X LIMIT {} WHERE '
        'X is {}, E is EsDocument, E entity X, E doc D, '
        'X cwuri U, X stable_id S, '
        '{} '
        'X eid > %(l)s'
    ).format(chunksize, etype, rqlpart)
    while True:
        print('will execute', rql, {'l': lasteid, 'p': publisher})
        rset = cnx.execute(rql, {'l': lasteid, 'p': publisher})
        print('\tget', len(rset), 'rows')
        if not rset:
            break
        for e in rset.entities():
            yield e
        cnx.drop_entity_cache()
        lasteid = rset[-1][0]


def bulk_actions(cnx, publisher, index_name, dry_run=True):
    for etype in ('FindingAid', 'FAComponent'):
        gen = get_indexable_fa(cnx, etype, publisher, CHUNKSIZE)
        for idx, entity in enumerate(gen, 1):
            try:
                serializer = entity.cw_adapt_to('IFullTextIndexSerializable')
                json = serializer.serialize(complete=False)
            except Exception:
                cnx.error('[{}] Failed to serialize entity {} ({})'.format(
                    index_name, entity.eid, etype))
                continue
            if not dry_run and json:
                # Entities with
                # fulltext_containers relations return their container
                # IFullTextIndex serializer , therefor the "id" and
                # "doc_type" in kwargs bellow must be container data.
                data = {'_op_type': 'index',
                        '_index': index_name or cnx.vreg.config['index-name'],
                        '_type': '_doc',
                        '_id': serializer.es_id,
                        '_source': json
                        }
                yield data


def parse_cmdline():
    parser = argparse.ArgumentParser()
    parser.add_argument('publisher',
                        help='the publisher label (e.g. "AD du Cantal")')
    parser.add_argument('appid',
                        help='appid of cubicweb instance')
    parser.add_argument('--es-index',
                        help='The ES index (default is one specified in all-in-one.conf)')
    parser.add_argument('--dry-run',
                        action='store_true',
                        help='do not send request to elasticsearch')
    return parser.parse_args()


def main():
    args = parse_cmdline()
    with admincnx(args.appid) as cnx:
        indexer = cnx.vreg['es'].select('indexer', cnx)
        es = indexer.get_connection()
        for _ in parallel_bulk(
                es, bulk_actions(
                    cnx,
                    args.publisher,
                    index_name=args.es_index,
                    dry_run=args.dry_run
                ),
                raise_on_error=False,
                raise_on_exception=False):
            pass


if __name__ == '__main__':
    main()
