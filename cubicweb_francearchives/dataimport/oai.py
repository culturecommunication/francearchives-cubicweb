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
from itertools import chain
import traceback
import logging

from six.moves.urllib import parse as urlparse

from oaipmh.metadata import MetadataRegistry
from oaipmh.client import Client
from oaipmh.datestamp import datestamp_to_datetime

from cubicweb_francearchives.dataimport import (log_in_db,
                                                ExtentityWithIndexImporter)
from cubicweb_francearchives.dataimport.ead import ead_foreign_key_tables
from cubicweb_francearchives.dataimport.sqlutil import no_trigger
from cubicweb_francearchives.dataimport.stores import create_massive_store

from cubicweb_francearchives.dataimport import oai_ead, oai_nomina, oai_dc
from cubicweb_francearchives.dataimport.scripts.generate_ape_ead import (
    generate_ape_ead_from_other_sources,)


class PniaBatchMetadataRegistry(MetadataRegistry):

    def __init__(self, cnx, service_infos=None):
        super(PniaBatchMetadataRegistry, self).__init__()
        # maybe used for custom reader selection / dedicated appobjects ?
        self.cnx = cnx
        if service_infos is None:
            service_infos = {}
        self.service_infos = service_infos

    def readMetadata(self, metadata_prefix, element):
        reader = self._readers[metadata_prefix]
        return reader(element, self.cnx, self.service_infos)


@log_in_db
def import_oai(cnx, url, service_infos,
               store=None, log=None, index_policy=None):
    """Import data based on OAI-PMH.

    :param Connection cnx: database connection
    :param str url: repository URL
    :param dict service_infos: service information
    :param RQLObjectStore store: store
    :param Logger log: logger
    :param dict index_policy: indexing policy
    """
    if log is None:
        log = logging.getLogger('rq.task')
    if not service_infos['code']:
        log.exception('harvesting aborded: no service code found')
        return
    if index_policy is None:
        index_policy = {'autodedupe_authorities': 'service/strict'}
    base_url, params = parse_oai_url(url.strip())
    assert params.pop('verb') == 'ListRecords', \
        "import_oai only handles `ListRecords` verb"
    prefix = params.pop('metadataPrefix')
    if store is None:
        store = create_massive_store(cnx, nodrop=True)
        notrigger_tables = ead_foreign_key_tables(cnx.vreg.schema)
    else:
        notrigger_tables = ()
    with no_trigger(cnx, notrigger_tables, interactive=False):
        if base_url.startswith('file:///'):
            force_http_get = False
        else:
            force_http_get = True
        if prefix == 'oai_dc':
            importer = oai_dc.OAIDCImporter(store, log)
            importer.import_records(
                prefix, base_url, service_infos, force_http_get, **params)
        else:
            registry = PniaBatchMetadataRegistry(cnx, service_infos)
            # XXX use appobjects for registration and custom selection ?
            #     This could be useful for oai_dc where we might have
            #     a bunch of different metadata profiles
            registry.registerReader('nomina', oai_nomina.OAINominaReader())
            registry.registerReader('ead', oai_ead.OAIEadReader())
            registry.registerReader('oai_ead', oai_ead.OAIEadReader())
            # decide if we should make a POST or a GET
            # it seems oai server prefer GET request so make it the default
            # but urllib2 is not able to find file if parameters are in url
            # so put them in body (which is default behavior for POST request)
            client = Client(base_url, registry, force_http_get=force_http_get)
            records = client.listRecords(metadataPrefix=prefix, **params)
            if prefix == "nomina":
                extentities = (
                    record_entities for _, record_entities, _ in records
                    if record_entities is not None
                )
                import_record_entities(
                    cnx, chain(*extentities), store, service_infos,
                    index_policy, log
                )
            else:
                try:
                    oai_ead.import_oai_ead(store, records, service_infos, log)
                except Exception as exception:
                    log.error("could not import records %s", exception)
                store.finish()
                store.commit()
        generate_ape_ead_from_other_sources(cnx)


def import_record_entities(
        cnx, extentities, store, service_infos=None, index_policy=None, log=None
):
    extid2eid = {}
    if service_infos is not None and service_infos.get('eid'):
        service_eid = service_infos['eid']
        extid2eid['service-{}'.format(service_eid)] = service_eid
    importer = ExtentityWithIndexImporter(
        cnx.vreg.schema, store, extid2eid, index_policy=index_policy, log=log
    )
    importer.import_entities(extentities)
    store.flush()
    store.finish()
    store.commit()


def parse_oai_url(url):
    url = urlparse.urlparse(url)
    qs = urlparse.parse_qs(url.query)
    allowed = {'from', 'until', 'set', 'metadataPrefix', 'verb'}
    if set(qs) - allowed:
        raise ValueError('Got invalid query parameter(s): %s',
                         set(qs) - allowed)
    base_url = url.scheme + '://' + url.netloc + url.path
    params = {k: v[0] for k, v in qs.items() if len(v) == 1}
    if 'until' in params:
        params['until'] = datestamp_to_datetime(params['until'])
    if 'from' in params:
        params['from_'] = datestamp_to_datetime(params.pop('from'))
    return base_url, params


def import_delta(cnx, repo_eid, ignore_last_import=False, log=None, reraise=False):
    """Import data based on OAI-PMH.

    :param Connection cnx: database connection
    :param int repo_eid: ID of an OAIRepository entity of interest
    :param bool ignore_last_import: toggle continuing from last successful
    import on/off
    :param Logger log: logger
    :param bool reraise: toggle exception re-raising on/off

    :raises Exception: if import_oai raises Exception and reraise=True
    """
    repo = cnx.entity_from_eid(repo_eid)
    service = repo.service[0]
    url = repo.url
    if not ignore_last_import:
        _from = repo.last_successful_import
        if _from is not None:
            url += '&from={}'.format(_from.strftime('%Y-%m-%d'))
    oaitask = cnx.create_entity('OAIImportTask', oai_repository=repo_eid)
    wf = oaitask.cw_adapt_to('IWorkflowable')
    cnx.commit()
    try:
        import_oai(cnx, url, service_infos={'code': service.code,
                                            'name': service.publisher(),
                                            'eid': service.eid},
                   log=log)
    except Exception:
        formatted_exc = traceback.format_exc().decode('utf-8', 'replace')
        wf.fire_transition('wft_faimport_fail', formatted_exc)
        if log:
            log.exception('exception when importing oaid "%s"', url)
        if reraise:
            raise
    else:
        wf.fire_transition('wft_faimport_complete')
    cnx.commit()
