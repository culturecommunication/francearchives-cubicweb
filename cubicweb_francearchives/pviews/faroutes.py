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
from __future__ import print_function, absolute_import

from functools import partial
import logging

from pyramid.view import view_config
from pyramid.response import Response
from pyramid.httpexceptions import HTTPNotFound, HTTPFound

from rql import TypeResolverException


from cubicweb import crypto, NoResultError

from cubicweb_francearchives.xy import (conjunctive_graph,
                                        add_statements_to_graph,
                                        namespaces)
from cubicweb_francearchives.utils import find_card
from cubicweb_francearchives.entities.cms import Service

from .cwroutes import startup_view_factory
from .csvutils import alignment_csv, indices_csv


LOG = logging.getLogger(__name__)


def rqlrequest_factory(request, rql, vid=None):
    cwreq = request.cw_request
    try:
        rset = cwreq.execute(rql, request.matchdict)
    except TypeResolverException:
        LOG.exception('seems there is no result for this rql')
        raise HTTPNotFound()
    if vid is None:
        if len(rset) == 1:
            vid = 'primary'
        elif rset:
            vid = 'list'
        else:
            vid = 'noresult'
    if not rset and vid != 'noresult':
        # unexpected empty rset raise 404
        raise HTTPNotFound()
    return {
        'vid': vid,
        'rset': rset,
    }


def rqlbased_view(request):
    cwreq = request.cw_request
    viewsreg = cwreq.vreg['views']
    ctx = request.context
    view = viewsreg.select(ctx['vid'], cwreq, rset=ctx['rset'])
    return Response(viewsreg.main_template(
        cwreq, 'main-template', rset=ctx['rset'], view=view))


def dpt_map_view(cwreq, dpt=None):
    if dpt:
        rset = cwreq.execute('Any X,XN,XC ORDERBY X '
                             'WHERE X is Service, X level "level-D", '
                             'X dpt_code %(dpt)s, X name XN, X dpt_code XC, '
                             'NOT X annex_of Y',
                             {'dpt': dpt.upper()})
        if rset:
            if len(rset) != 1:
                LOG.warning('Got %s service(s) instead of 1 for dpt %s '
                            'and level "level-D"', len(rset), dpt.upper())
                # the dpt-service-map view assumes there's either 0 or 1 result.
                # if there's more than one, pick arbitrarily the first one created
                # in order to display a service and make everything editable.
                # It's just a safety belt, a hook should forbid this specific case
                rset = rset.limit(1)
        else:
            rset = None
    else:
        rset = None
    viewsreg = cwreq.vreg['views']
    view = viewsreg.select('dpt-service-map', cwreq, rset=rset)
    return Response(
        viewsreg.main_template(cwreq, 'main-template', rset=rset, view=view)
    )


def all_services(req):
    rset = req.execute('Any S,SN,SN2,SSN,SPN,SF,SE,SA,SZ,SC,SCC,SU,SOP,SCODE,'
                       'SWU,SL,SI,SIF,SIFH,SIFN,PARENT,SDC,SML '
                       'ORDERBY SL,SN,PARENT '
                       'WHERE S is Service, S name SN, S name2 SN2, S short_name SSN, '
                       'S mailing_address SML, S dpt_code SDC, '
                       'S phone_number SPN, S fax SF, S email SE, S address SA, '
                       'S zip_code SZ, S city SC, S contact_name SCC, '
                       'S service_image SI?, SI image_file SIF?, '
                       'SIF data_sha1hex SIFH, SIF data_name SIFN, '
                       'S uuid SU, S opening_period SOP, S code SCODE, '
                       'S website_url SWU, S level SL, S annex_of PARENT?')
    return rset


@view_config(route_name='annuaire-vcard',
             request_method=('GET', 'HEAD'))
def annuaire_vcard_view(request):
    cwreq = request.cw_request
    vcards = []
    for service in all_services(cwreq).entities():
        card = service.cw_adapt_to('vcard').vcard()
        vcards.append(card.serialize().decode('utf-8'))
    return Response(u'\n\n'.join(vcards),
                    content_type='text/vcard')


@view_config(route_name='annuaire-csv',
             request_method=('GET', 'HEAD'),
             renderer='csv')
def annuaire_csv_view(request):
    cwreq = request.cw_request
    rows = []
    for service in all_services(cwreq).entities():
        icsv = service.cw_adapt_to('csv-props')
        rows.append(icsv.csv_row())
    headers = icsv.headers  # pick headers from any adapaters
    return {'rows': rows, 'headers': headers}


@view_config(route_name='annuaire-dpt',
             request_method=('GET', 'HEAD'))
def annuaire_dpt_view(request):
    cwreq = request.cw_request
    return dpt_map_view(cwreq, cwreq.form.get('dpt'))


@view_config(route_name='annuaire-explicit-dpt',
             request_method=('GET', 'HEAD'))
def annuaire_explicitdpt_view(request):
    return dpt_map_view(request.cw_request, request.matchdict['dpt'])


@view_config(route_name='alignment',
             request_method=('GET', 'HEAD'),
             renderer='csv')
def alignment_csv_view(request):
    return alignment_csv(request.cw_request)


@view_config(route_name='indices-csv',
             request_method=('GET', 'HEAD'),
             renderer='csv')
def indices_csv_view(request):
    auth_type = request.matchdict['type']
    return indices_csv(request.cw_request, auth_type)


def card_view(request):
    cwreq = request.cw_request
    card = find_card(cwreq, request.matchdict['wiki'])
    if card is None:
        raise HTTPNotFound()
    rset = card.as_rset()
    viewsreg = cwreq.vreg['views']
    view = viewsreg.select('primary', cwreq, rset=rset)
    return Response(
        viewsreg.main_template(
            cwreq, 'main-template', rset=rset, view=view))


@view_config(route_name='all-documents',
             request_method=('GET', 'HEAD'))
def all_documents_view(request):
    cwreq = request.cw_request
    cwreq.form.setdefault('vid', 'esearch')
    cwreq.form.setdefault('es_escategory', 'archives')
    viewsreg = cwreq.vreg['views']
    view = viewsreg.select('esearch', cwreq, rset=None)
    return Response(
        viewsreg.main_template(cwreq, 'main-template', rset=None, view=view)
    )


@view_config(route_name='virtualexhibits',
             request_method=('GET', 'HEAD'))
def virtualexhibitsview(request):
    cwreq = request.cw_request
    cwreq.form.setdefault('vid', 'esearch')
    cwreq.form.setdefault('es_cw_etype', 'Virtual_exhibit')
    viewsreg = cwreq.vreg['views']
    view = viewsreg.select('esearch', cwreq, rset=None)
    return Response(
        viewsreg.main_template(cwreq, 'main-template', rset=None, view=view)
    )


@view_config(route_name='service-documents',
             request_method=('GET', 'HEAD'))
def service_documents_view(request):
    cwreq = request.cw_request
    service = Service.from_code(cwreq, request.matchdict['service'])
    if service is None:
        raise HTTPNotFound()
    cwreq.form.setdefault('vid', 'esearch')
    cwreq.form.setdefault('es_escategory', 'archives')
    cwreq.form.setdefault('es_publisher', service.publisher())
    viewsreg = cwreq.vreg['views']
    view = viewsreg.select('esearch', cwreq, rset=None)
    return Response(
        viewsreg.main_template(cwreq, 'main-template', rset=None, view=view)
    )


@view_config(route_name='findingaid-rdf',
             request_method=('GET', 'HEAD'))
def findingaid_rdf_view(request):
    cwreq = request.cw_request
    etype = cwreq.vreg.case_insensitive_etypes[request.matchdict['etype']]
    entity = cwreq.find(etype, stable_id=request.matchdict['stable_id']).one()
    # XXX HTTPNotFound() on error
    rdf_adapter = entity.cw_adapt_to('rdf.edm')
    graph = conjunctive_graph()
    add_statements_to_graph(graph, rdf_adapter)
    format = request.matchdict['format'].split('.', 1)[1]
    if format == 'n3':
        content_type = 'text/rdf+n3'
    elif format == 'ttl':
        content_type = 'application/x-turtle'
    elif format == 'nt':
        content_type = 'text/plain'
    else:  # fallback to xml
        content_type = 'application/rdf+xml'
        format = 'pretty-xml'
    return Response(
        graph.serialize(format=format, context=namespaces),
        content_type=content_type
    )


@view_config(route_name='findingaid-csv',
             renderer='csv',
             request_method=('GET', 'HEAD'))
def findingaid_csv_view(request):
    cwreq = request.cw_request
    etype = cwreq.vreg.case_insensitive_etypes[request.matchdict['etype']]
    entity = cwreq.find(etype, stable_id=request.matchdict['stable_id']).one()
    adapter = entity.cw_adapt_to('entity.main_props')
    data = adapter.properties(export=True, vid='text', text_format='text/plain')
    filename = '%s.csv' % entity.rest_path()
    request.response.content_disposition = 'attachment;filename=' + filename
    return {'headers': [d[0] for d in data],
            'rows': [[d[1] for d in data]]}


@view_config(route_name='circulars-csv',
             request_method=('GET', 'HEAD'),
             renderer='csv')
def circulars_csv_view(request):
    cwreq = request.cw_request
    rset = cwreq.execute(
        'Any JV ORDERBY SDSD, SD '
        'WHERE S is Circular, S json_values JV, '
        'S siaf_daf_signing_date SDSD, S signing_date SD')
    rows = []
    for json_values in rset:
        rows.append([v or '' for l, v in json_values[0]])
    headers = [cwreq._(e[0]) for e in json_values[0]]
    return {'rows': rows, 'headers': headers}


REWRITE_RULES = [
    (
        'commemocoll-index',
        r'/commemo/recueil-{year:\d+}/index',
        {
            'vid': 'commemo-alpha-index',
            'rql': 'Any X WHERE X is CommemoCollection, X year %(year)s',
        },
    ), (
        'commemocoll-timeline-json',
        r'/commemo/recueil-{year:\d+}/timeline.json',
        {
            'vid': 'pnia.vtimeline.json',
            'rql': 'Any X WHERE X is CommemoCollection, X year %(year)s',
        },
    ), (
        'commemocoll-timeline',
        r'/commemo/recueil-{year:\d+}/timeline',
        {
            'vid': 'pnia.vtimeline',
            'rql': 'Any X WHERE X is CommemoCollection, X year %(year)s',
        },
    ), (
        'commemocoll',
        r'/commemo/recueil-{year:\d+}/',
        {
            'vid': 'primary',
            'rql': 'Any X WHERE X is CommemoCollection, X year %(year)s',
        },
    ), (
        'commemoitem',
        r'/commemo/recueil-{year:\d+}/{commemo:\d+}',
        {
            'vid': 'primary',
            'rql': 'Any X WHERE X commemoration_year %(year)s, X eid %(commemo)s',
        },
    ), (
        'annuaire',
        r'/annuaire/{eid:\d+}',
        {
            'vid': 'primary',
            'rql': 'Any X WHERE X is Service, X eid %(eid)s',
        },
    ),
    (
        'topsection',
        r'/{section:(decouvrir|comprendre|gerer)}',
        {
            'vid': 'primary',
            'rql': ('Any S WHERE S is Section, NOT EXISTS(X children S), '
                    'S name %(section)s'),
        },
    ),
]


def form_controller(request, regid):
    cwreq = request.cw_request
    form = cwreq.vreg['forms'].select(regid, cwreq)
    kwargs = form.publish_form()
    viewsreg = cwreq.vreg['views']
    cwreq.form['_ctrl'] = kwargs
    view = cwreq.vreg['views'].select(regid, cwreq)
    return Response(viewsreg.main_template(
        cwreq, 'main-template', rset=None, view=view))


@view_config(route_name='contact',
             request_method='POST')
def contact_controller(request):
    return form_controller(request, 'contact')


@view_config(route_name='lettre-info',
             request_method='POST')
def newsletter_controller(request):
    return form_controller(request, 'newsletter')


@view_config(route_name='nlconfirm',
             request_method=('GET', 'HEAD'))
def newsletter_confirm_controller(request):
    cwreq = request.cw_request
    view = cwreq.vreg['views'].select('nlconfirm', cwreq)
    viewsreg = cwreq.vreg['views']
    if 'key' not in cwreq.form:
        return Response(viewsreg.main_template(
            cwreq, 'main-template', rset=None, view=view))
    try:
        email = crypto.decrypt(cwreq.form['key'],
                               cwreq.vreg.config['newsletter-cypher-seed'])
    except Exception:
        msg = cwreq._(u'Invalid subscription data. Please try subscription again.')
        # '_d' arg stand for 'dispaly subscription form'
        cwreq.form['_ctrl'] = {'msg': msg, '_d': 1}
        return Response(viewsreg.main_template(
            cwreq, 'main-template', rset=None, view=view))
    with cwreq.cnx.repo.internal_cnx() as cnx:
        existing = cnx.find('NewsLetterSubscriber', email=email)
        if not existing:
            try:
                cnx.create_entity('NewsLetterSubscriber', email=email)
                cnx.commit()
                msg = cwreq._(u"Your email has been successfully added.")
                cwreq.form['_ctrl'] = {'msg': msg}
            except Exception:
                msg = cwreq._(u'Your subscription has failed. Please try subscription again.')
                cwreq.form['_ctrl'] = {'msg': msg, '_d': 1}
        else:
            msg = cwreq._(u'Your are already subscribed to the newsletter.')
            cwreq.form['_ctrl'] = {'msg': msg}
    return Response(viewsreg.main_template(
        cwreq, 'main-template', rset=None, view=view))


@view_config(route_name='absolute-url',
             request_method=('GET', 'HEAD'))
def uuid2absolute_url(request):
    req = request.cw_request
    rset = req.execute('Any X WHERE X is {}, X uuid %(uuid)s'.format(request.matchdict['etype']),
                       request.matchdict)
    return HTTPFound(location=rset.one().absolute_url())


@view_config(route_name='fa-map',
             request_method=('GET', 'HEAD'))
def famap_view(request):
    cwreq = request.cw_request
    cwreq.form.setdefault('vid', 'fa-map')
    viewsreg = cwreq.vreg['views']
    view = viewsreg.select('fa-map', cwreq, rset=None)
    return Response(
        viewsreg.main_template(cwreq, 'main-template', rset=None, view=view)
    )


@view_config(route_name='fa-map-json',
             renderer='json',
             http_cache=600,
             request_method=('GET', 'HEAD'))
def famap_data(request):
    cwreq = request.cw_request
    rset = cwreq.execute('Any P, PL, PLAT, PLNG, COUNT(F) GROUPBY P, PL, PLAT, PLNG '
                         'WHERE I authority P, I index F, '
                         'P is LocationAuthority, P latitude PLAT, P longitude PLNG, '
                         'P label PL, NOT P latitude NULL')
    return [
        {'eid': eid, 'label': label,
         'lat': lat, 'lng': lng,
         'dashLabel': '--' in label,
         'count': count, 'url': cwreq.build_url('location/{}'.format(eid))}
        for eid, label, lat, lng, count in rset
    ]


@view_config(context=NoResultError)
def rql_error_view(request):
    return HTTPNotFound()


def includeme(config):
    config.add_route('absolute-url', r'/uuid/{etype:\w+}/{uuid:\w+}')
    config.add_route('annuaire-vcard', '/annuaire.vcf')
    config.add_route('annuaire-csv', '/annuaire.csv')
    config.add_route('annuaire-dpt', '/annuaire/departements')
    config.add_route('annuaire-explicit-dpt', r'/annuaire/departements/{dpt:\d+[AB]}')
    config.add_route('indices-csv', '/indices-{type}.csv')
    for route, path, context in REWRITE_RULES:
        config.add_route(route, path,
                         factory=partial(rqlrequest_factory, **context))
        config.add_view(rqlbased_view, route_name=route,
                        request_method=('GET', 'HEAD'))
    config.add_route('entrypoint-card',
                     '/{wiki:(faq|cgu|open_data|about|emplois|privacy_policy|legal_notices|accessibility)}')  # noqa
    config.add_view(card_view, route_name='entrypoint-card',
                    request_method=('GET', 'HEAD'))
    for path, vid in (('sitemap', 'sitemap'),
                      ('search', 'esearch'),
                      ('recherche', 'esearch'),
                      ('contact', 'contact'),
                      ('lettre-info', 'newsletter')
                      ):
        config.add_route(path, '/' + path)
        # NOTE: lambda req, vid=vid: cw_startup_view(vid, req) doesn't work
        #       because pyramid seems to introspect the view object and behaves
        #       differently according to the number of parameters (e.g. 2 here)
        config.add_view(startup_view_factory(vid),
                        route_name=path,
                        request_method=('GET', 'HEAD'))
    config.add_route('all-documents', '/inventaires/')
    config.add_route('nlconfirm', '/nlconfirm')
    config.add_route('service-documents', '/inventaires/{service}')
    config.add_route('findingaid-rdf',
                     r'/{etype:(findingaid|facomponent)}/{stable_id}/{format:rdf\.(xml|n3|nt|ttl)}')
    config.add_route('findingaid-csv',
                     r'/{etype:(findingaid|facomponent)}/{stable_id}.csv')
    config.add_route('alignment', '/alignment.csv')
    config.add_route('fa-map', '/carte-inventaires')
    config.add_route('fa-map-json', '/fa-map.json')
    config.add_route('virtualexhibits', '/expositions')
    config.add_route('circulars-csv', '/circulaires.csv')
    config.add_notfound_view(startup_view_factory('404', status_code=404),
                             append_slash=True)
    config.scan(__name__)
