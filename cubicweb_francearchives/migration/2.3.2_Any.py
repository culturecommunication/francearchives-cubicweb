# flake8: noqa
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

from elasticsearch_dsl.connections import connections
from cubicweb_elasticsearch.es import get_connection
from cubicweb_francearchives.dataimport import es_bulk_index

import logging
LOGGER = logging.getLogger()


UNINDEX_CARDS = []

rql("SET X do_index False WHERE X is Card, X wikiid 'alert%%'")
rql("SET X do_index False WHERE X is Card, X wikiid ILIKE 'tableau-circulaires-%%'")

UNINDEX_CARDS.extend([r[0] for r in
                      rql("Any X WHERE X is Card, X wikiid ILIKE 'tableau-circulaires-%%'")])
UNINDEX_CARDS.extend([r[0] for r in
                      rql("Any X WHERE X is Card, X wikiid ILIKE 'alert%%'")])
UNINDEX_CARDS.extend([r[0] for r in
                      rql("Any X WHERE X is Card, X wikiid ILIKE 'newsletter%%'")])



for lang in ('es', 'de', 'en'):
    UNINDEX_CARDS.extend(
        [r[0] for r in
         rql("""Any X WHERE X wikiid ILIKE "%%-{}", X content NULL""".format(lang))])
    rql("""DELETE Card X WHERE X wikiid ILIKE "%-{}",
            X content NULL""".format(lang))

commit()

CMS_ES_PARAMS =  {
    "elasticsearch-locations": cnx.vreg.config["elasticsearch-locations"],
    "index-name": cnx.vreg.config["published-index-name"] + "_all",
}


es = get_connection(CMS_ES_PARAMS)
index_name = CMS_ES_PARAMS['index-name']
published_index_name = cnx.vreg.config["index-name"] + "_all",
for eid in UNINDEX_CARDS:
    for index in (index_name, published_index_name):
        print("deleting on {}/{}".format(eid, index_name))
        try:
            es.delete(index_name, doc_type="_doc", id=eid)
        except Exception as ex:
            print(ex)


# drop deprecated columns from 'published' schema
cnx.system_sql(
    """ALTER TABLE published.cw_findingaid DROP COLUMN cw_genreform, DROP COLUMN cw_function,
    DROP COLUMN cw_occupation""",
    rollback_on_failure=False,
)
# update missing/outdated cw_website_url values
cnx.system_sql(
    """UPDATE published.cw_findingaid SET cw_website_url=public.cw_findingaid.cw_website_url
    FROM public.cw_findingaid WHERE
    public.cw_findingaid.cw_stable_id=published.cw_findingaid.cw_stable_id
    AND public.cw_findingaid.cw_website_url IS DISTINCT FROM
    published.cw_findingaid.cw_website_url""", rollback_on_failure=False
)
