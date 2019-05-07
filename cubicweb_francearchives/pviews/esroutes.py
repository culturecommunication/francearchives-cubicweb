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
"""elasticsearch-related views"""
from elasticsearch.exceptions import NotFoundError
from elasticsearch_dsl.search import Search
from elasticsearch_dsl import query as dsl_query

from pyramid.view import view_config

from cubicweb_elasticsearch.es import get_connection


@view_config(route_name='suggest',
             renderer='json',
             request_method=('GET', 'HEAD'))
def suggest_view(request):
    query_string = request.params.get('q', '').strip()
    if not query_string:
        return []
    cwconfig = request.registry['cubicweb.config']
    get_connection(cwconfig)
    search = Search(doc_type='_doc',
                    index='{}_suggest'.format(cwconfig['index-name'])).sort('-count')
    must = [{'match': {'text': {'query': query_string,
                                'operator': 'and'}}}]
    search.query = dsl_query.Bool(must=must)
    try:
        response = search.execute()
    except NotFoundError:
        return []
    build_url = request.cw_request.build_url
    results = []
    if response and response.hits.total:
        _ = request.cw_request._
        countlabel_templates = (_('No result'),
                                _('1 document'),
                                _('{count} documents'))
        for result in response:
            count = result.count if hasattr(result, 'count') else 0
            countlabel = countlabel_templates[min(count, 2)].format(
                count=count)
            indextype = result.type if 'type' in result else result.cw_etype
            results.append({
                'url': build_url(result.urlpath),
                'text': result.text,
                'countlabel': countlabel,
                'etype': _(indextype),
                'additional': result.additional})
    return results


def includeme(config):
    config.add_route('suggest', '/_suggest')
    config.scan(__name__)
