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
from __future__ import print_function

import logging
from itertools import count
from collections import defaultdict

from isodate import datetime_isoformat

from lxml import etree
from lxml.builder import E, ElementMaker

from oaipmh.metadata import MetadataRegistry, oai_dc_reader
from oaipmh.client import Client

from cubicweb.utils import json_dumps

from cubes.oaipmh import utcnow

from cubicweb_francearchives.dataimport import (usha1, clean_values,
                                                get_year, get_date,
                                                strip_html,
                                                facomponent_stable_id,
                                                )
from cubicweb_francearchives.dataimport import (es_bulk_index,
                                                oai_utils, OAIPMH_DC_PATH)

from cubicweb_francearchives.dataimport.dc import CSVReader

from cubicweb_francearchives.dataimport.ead import readerconfig
from cubicweb_francearchives.dataimport.sqlutil import delete_from_filename


class OAIDCWriter(oai_utils.OAIPMHWriter):
    """OAI-PMH writer (Dublin Core).

    :cvar str OAI_VERB: verb of the OAI-PMH request
    :ivar list oai_records: list of records
    """
    OAI_VERB = "ListRecords"

    def __init__(self, ead_services_dir, service_infos):
        """Initialize OAI-PMH writer (Dublin Core).

        :param str ead_services_dir: location of backup files
        :param dict service_infos: service information
        """
        super(OAIDCWriter, self).__init__(ead_services_dir, service_infos)
        self.oai_records = defaultdict(list, {})

    def add_record(self, header, metadata):
        """Add record to list of records.

        :param _Element header: header
        :param _Element metadata: metadata
        """
        eadid = header.setSpec()[0]
        self.oai_records[eadid].append((header, metadata))

    def to_xml(self, eadid):
        """Convert records to XML file format compliant tree.

        :param str eadid: EAD ID

        :returns: element factory
        :rtype: ElementMaker
        """
        date = E.responseDate(datetime_isoformat(utcnow()))
        nsmap = {None: 'http://www.openarchives.org/OAI/2.0/',
                 'xsi': 'http://www.w3.org/2001/XMLSchema-instance'}
        maker = ElementMaker(nsmap=nsmap)
        attributes = {
            '{%s}schemaLocation' % nsmap['xsi']: ' '.join([
                'http://www.openarchives.org/OAI/2.0/',
                'http://www.openarchives.org/OAI/2.0/OAI-PMH.xsd'
            ])
        }
        oai_records = [
            E.record(header.element(), metadata.element())
            for header, metadata in self.oai_records[eadid]
        ]
        body_elements = [E(self.OAI_VERB, *oai_records)]
        return maker(u'OAI-PMH', date, *body_elements, **attributes)

    def get_file_contents(self, eadid):
        """Get file contents.

        :param str eadid: EAD ID
        """
        file_contents = etree.tostring(
            self.to_xml(eadid),
            encoding="utf-8", xml_declaration=True
        )
        return file_contents


def build_header(header, namespaces):
    setsepec = header.setSpec()
    eadid = setsepec[0] if setsepec else None
    evaluator = etree.XPathEvaluator(header.element(),
                                     namespaces=namespaces).evaluate
    setName = evaluator('string(oai:setName/text())')
    return {
        'identifier': header.identifier(),
        'eadid': eadid,
        'name': setName or eadid
    }


def build_metadata(metadata):
    metadata = metadata._map.copy()
    start = stop = None
    date = metadata.pop('date')
    if date:
        date = date[0]
        if '-' in date:
            try:
                start, stop = [d.strip() for d in date.split('-')]
            except ValueError:
                pass
        else:
            try:
                start = date.strip()
                stop = None
            except ValueError:
                pass
    metadata['date1'] = get_year(start)
    metadata['date2'] = get_year(stop)
    return metadata


EXTIDS = {'ConceptScheme': u'siaf',
          'IndexRole': u'virtual-exhibit'}


class OAIDCImporter(object):
    """OAI DC schema importer.

    :ivar dict config: server-side configuration
    :ivar OAIDCReader reader: OAI DC schema reader
    :ivar Connection cnx: connection
    :ivar es: Elasticsearch connection
    """

    def __init__(self, store, log=None):
        """Initialize OAI DC schema reader.

        :param RQLObject store: store
        :param Logger log: logger
        """
        cwconfig = store._cnx.vreg.config
        if log is None:
            log = logging.getLogger('rq.task')
        self.log = log
        self.config = readerconfig(cwconfig, cwconfig.appid,
                                   log=self.log, esonly=False,
                                   nodrop=True, reimport=True)
        self.reader = OAIDCReader(
            self.config, store
        )
        self.cnx = self.reader.store._cnx
        indexer = self.cnx.vreg['es'].select('indexer', self.cnx)
        self.es = indexer.get_connection()

    def import_records(self, metadataPrefix, base_url,
                       service_infos, force_http_get, **params):
        """Import records.

        :param str metadataPrefix: metadata format of the record
        :param str base_url: base URL
        :param dict service_infos: service information
        :param bool force_http_get: toggle sending HTTP GET request on/off
        """
        registry = MetadataRegistry()
        registry.registerReader('oai_dc', oai_dc_reader)
        client = Client(base_url, registry, force_http_get=force_http_get)
        records = client.listRecords(metadataPrefix=metadataPrefix, **params)
        store = self.reader.store
        es_docs = []
        try:
            es_docs = self.process_records(store, client, records, service_infos)
        except Exception as exception:
            self.log.error("could not import records %s", exception)
        if not self.reader.config['esonly']:
            store.finish()
            store.commit()
        if es_docs:
            es_bulk_index(self.es, es_docs)

    def process_records(self, store, client, records, service_infos):
        oaipmh_writer = OAIDCWriter(
            store._cnx.vreg.config["ead-services-dir"], service_infos
        )
        directory = oaipmh_writer.makedir(subdirectories=OAIPMH_DC_PATH.split('/'))
        es_docs = []
        for header, metadata, about in records:
            identifier = header.identifier()
            if not header.setSpec():
                warning = 'ignoring identifier %r because unspecified setSpec'
                self.log.warning(warning, identifier)
                continue
            if not metadata.getField('title'):
                warning = 'ignoring identifier %r because unspecified dc_title'
                self.log.warning(warning, identifier)
                continue
            self.log.info("process  %r", identifier)
            oaipmh_writer.add_record(header, metadata)
        # write oai_dc_file
        for eadid in oaipmh_writer.oai_records.keys():
            file_path = oaipmh_writer.get_file_path(directory, eadid)
            file_contents = oaipmh_writer.get_file_contents(eadid)
            oaipmh_writer.dump(file_path, file_contents)
            # insert record into database
            for header, metadata in oaipmh_writer.oai_records[eadid]:
                try:
                    es_docs.extend(
                        self.reader.import_record(
                            build_header(header, client.getNamespaces()),
                            build_metadata(metadata),
                            service_infos
                        )
                    )
                except Exception as exception:
                    # try to find and eadid where we can to send a sensible log msg
                    self.log.warning(
                        'ignoring IR with eadid %r : %r', eadid, exception
                    )
                    continue
        if not self.reader.config['esonly']:
            store.flush()
        return es_docs


class OAIDCReader(CSVReader):
    """OAI DC schema reader.

    :ivar function next_id: returns consecutive IDs
    """

    def __init__(self, config, store):
        super(CSVReader, self).__init__(config, store)
        self.next_id = lambda c=count(1): next(c)
        self._created_fa = {}

    def richstring_html(self, data, attr):
        if data:
            if not isinstance(data, (list, tuple)):
                data = [data]
            return self.richstring_template.format(
                data=u' '.join(data), attr=attr)
        return None

    def import_record(self, header, metadata, service_infos):
        """Generate extentities read from `record` etree"""
        stable_id = usha1(header['eadid'])
        header['stable_id'] = stable_id
        fa_es_doc = self._created_fa.get(stable_id)
        es_docs = []
        if fa_es_doc is None:
            if stable_id in self.known_fa_ids and self.config.get('reimport'):
                delete_from_filename(
                    self.store._cnx, stable_id, interactive=False,
                    esonly=self.config['esonly'], is_filename=False)
            fa_es_doc = self.import_findingaid(header, metadata, service_infos)
            self._created_fa[stable_id] = fa_es_doc
            es_docs.append(fa_es_doc)
        es_doc = self.import_facomponent(
            metadata, fa_es_doc['_source'], header['identifier'])
        if es_doc:
            es_docs.append(es_doc)
        return es_docs

    def import_findingaid(self, header, metadata, service_infos):
        name = header['name']
        did_attrs = {
            'unittitle': name,
        }
        did_data = self.create_entity('Did', clean_values(did_attrs))
        fa_header_data = self.create_entity('FAHeader', {'titleproper': name})
        publisher = service_infos.get('name')
        if not publisher:
            publisher = u'; '.join(metadata['publisher']) or u'XXX'
        ead_services_dir = self.store._cnx.vreg.config["ead-services-dir"]
        oaipmh_writer = OAIDCWriter(ead_services_dir, service_infos)
        # directory exists, will not be overwritten
        directory = oaipmh_writer.makedir(subdirectories=["oaipmh", "dc"])
        file_path = oaipmh_writer.get_file_path(
            directory, header["eadid"]
        )
        findingaid_support = self.create_file(file_path)
        # convert str to File
        fa_attrs = {
            'name': name,
            'eadid': header['eadid'],
            'did': did_data['eid'],
            'publisher': publisher,
            'service': service_infos.get('eid'),
            'stable_id': header['stable_id'],
            'fa_header': fa_header_data['eid'],
            'findingaid_support': findingaid_support['eid']
        }
        fa_data = self.create_entity('FindingAid', clean_values(fa_attrs))
        fa_es_attrs = {
            'name': fa_data['name'],
            'fa_stable_id': fa_data['stable_id'],
            'scopecontent': strip_html(fa_attrs.get('scopecontent'))}
        es_doc = self.build_complete_es_doc(
            u'FindingAid', fa_data, did_data, index_entries={}, **fa_es_attrs)
        self.create_entity('EsDocument', {'doc': json_dumps(es_doc['_source']),
                                          'entity': fa_data['eid']})
        return es_doc

    def digitized_version(self, metadata):
        dao = []
        for url in metadata['identifier']:
            dao.append({'url': url})
        for illustration_url in metadata['relation']:
            dao.append({'illustration_url': illustration_url})
        return dao

    def import_facomponent(self, metadata, findingaid_data, identifier):
        fa_stable_id = findingaid_data['stable_id']
        unittitle = u' ; '.join(metadata['title'])
        # this is not a real stable_id. Add the composant order
        # it is not certain than the <header><idenfier> is unique
        fac_stable_id = facomponent_stable_id(
            u'{}{}'.format(identifier, self.next_id()),
            fa_stable_id)
        did_attrs = {
            'unitid': u' ; '.join(metadata['source']),
            'unittitle': unittitle,
            'unitdate': get_date(metadata['date1'], metadata['date2']),
            'startyear': get_year(metadata['date1']),
            'stopyear': get_year(metadata['date2']),
            'physdesc': self.richstring_html(
                u' ; '.join(metadata['format']), 'physdesc'),
            'physdesc_format': u'text/html',
            'origination': u' ; '.join(metadata['creator']),
        }
        languages = u' ; '.join(metadata['language'])
        if len(languages) < 4:
            did_attrs['lang_code'] = languages
        else:
            did_attrs['lang_description'] = self.richstring_html(
                languages, 'language')
            did_attrs['lang_description_format'] = u'text/html'
        did_data = self.create_entity('Did', clean_values(did_attrs))
        comp_attrs = {
            'finding_aid': findingaid_data['eid'],
            'stable_id': fac_stable_id,
            'did': did_data['eid'],
            'scopecontent': self.richstring_html(
                u' ; '.join(metadata['description']), 'scopecontent'),
            'scopecontent_format': u'text/html',
            'userestrict': self.richstring_html(metadata['rights'],
                                                'userestrict'),
            'userestrict_format': u'text/html',
        }
        comp_data = self.create_entity('FAComponent', clean_values(comp_attrs))
        # add daos
        comp_eid = comp_data['eid']
        daodefs = self.digitized_version(metadata)
        for daodef in daodefs:
            digit_ver_attrs = self.create_entity('DigitizedVersion',
                                                 clean_values(daodef))
            self.add_rel(comp_eid, 'digitized_versions',
                         digit_ver_attrs['eid'])
        indexes = self.index_entries({
            'index_personne': metadata['contributor'],
            'index_lieu': metadata['coverage'],
            'index_matiere': metadata['subject'],
        }, comp_eid, findingaid_data)
        es_doc = self.build_complete_es_doc(
            u'FAComponent', comp_data, did_data,
            name=findingaid_data['name'],
            fa_stable_id=fa_stable_id,
            publisher=findingaid_data['publisher'],
            index_entries=indexes,
            digitized=bool(daodef))
        self.create_entity('EsDocument', {'doc': json_dumps(es_doc),
                                          'entity': comp_eid})
        return es_doc
