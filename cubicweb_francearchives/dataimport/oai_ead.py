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


import lxml.etree
from sickle.models import Record

import traceback

from cubicweb_francearchives.dataimport import (
    es_bulk_index,
    oai_utils,
    usha1,
    OAIPMH_EAD_PATH,
    InvalidFindingAid,
    load_services_map,
)
from sickle import Sickle

from cubicweb_francearchives import get_user_agent
from cubicweb_francearchives.dataimport.ead import Reader, readerconfig
from cubicweb_francearchives.dataimport.eadreader import cleanup_ns
from cubicweb_francearchives.dataimport.sqlutil import delete_from_filename


class OAIEADWriter(oai_utils.OAIPMHWriter):
    """OAI-PMH writer (EAD)."""

    def __init__(self, ead_services_dir, service_infos, subdirectories=[]):
        """Initialize OAI-PMH writer (Dublin Core).

        :param str ead_services_dir: location of backup files
        :param dict service_infos: service information
        :param list subdirectories: list of subdirectories
        """
        super(OAIEADWriter, self).__init__(
            ead_services_dir, service_infos, subdirectories=subdirectories
        )
        self.oai_records = []

    def get_file_contents(self, metadata):
        """Get file contents.

        :param _Element metadata: contents of metadata tag
        """
        file_contents = lxml.etree.tostring(metadata, encoding="utf-8", xml_declaration=True)
        return file_contents

    def add_record(self, record):
        """Add record to list of records.
        :param _Element record: record
        """
        self.oai_records.append(record)


def import_oai_ead(store, base_url, service_infos, log, **params):
    """Import records based on OAI EAD standard.

    :param RQLObjectStore store: store
    :param str base_url: base URL
    :param dict service_infos: service information
    :param Logger log: logger
    :param dict params: harvest parameters
    """
    cnx = store._cnx
    cwconfig = cnx.vreg.config
    oaipmh_writer = OAIEADWriter(
        cwconfig["ead-services-dir"], service_infos, subdirectories=OAIPMH_EAD_PATH.split("/")
    )
    oai_ead_mapping = {
        "ListRecords": OAIEADRecord,
        "GetRecord": OAIEADRecord,
    }
    headers = {"User-Agent": get_user_agent()}
    client = Sickle(
        base_url,
        iterator=oai_utils.PniaOAIItemIterator,
        class_mapping=oai_ead_mapping,
        headers=headers,
    )
    client.logger = log
    records = client.ListRecords(**params)
    # harvest records
    try:
        download_records(records, oaipmh_writer, service_infos["code"], log)
    except Exception:
        formatted_exc = traceback.format_exc()
        log.error(
            ("Could not import record %s. Harvesting aborded."), formatted_exc,
        )
    log.info("downloaded %s record(s)", len(oaipmh_writer.oai_records))
    if not oaipmh_writer.oai_records:
        return
    reader = Reader(
        readerconfig(
            cwconfig,
            cwconfig.appid,
            log=log,
            esonly=False,
            nodrop=True,
            reimport=True,
            force_delete=True,
        ),
        store,
    )
    indexer = cnx.vreg["es"].select("indexer", cnx)
    es = indexer.get_connection()
    # import records in the database
    reader.update_authorities_cache(service_infos.get("eid"))
    es_docs = import_records(store, oaipmh_writer, reader, es, service_infos, log)
    if not reader.config["esonly"]:
        store.finish()
        store.commit()
    if es_docs:
        es_bulk_index(indexer.get_connection(), es_docs)


class OAIEADRecord(Record):
    def __init__(self, record_element, strip_ns=True):
        self.error = None
        try:
            super(OAIEADRecord, self).__init__(record_element, strip_ns=strip_ns)
        except Exception as e:
            self.error = e
            return
        self.ead = self.xml.find(".//" + self._oai_namespace + "metadata/")
        self.harvested_url = ""
        self.preprocess_ead()

    def preprocess_ead(self):
        """Preprocesses the EAD xml file to remove ns and internal content
           (adapted from dataimport.eadreader.preprocess_ead)

        :param XMLElement record: the lxml etree object (metadata)

        :returns the lxml etree object (ead), cleaned from internal content or
        None if the lxml etree is empty

        """
        if self.ead is not None:
            cleanup_ns(self.ead)
            for elt in self.ead.findall('.//*[@audience="internal"]'):
                elt.getparent().remove(elt)

    @property
    def eadid(self):
        eadid = self.metadata.get("eadid")
        if eadid and eadid[0]:
            return eadid[0].strip()


def download_records(records, oaipmh_writer, service_code, log):
    """Harvest data and check them containing the needed information

    :param function records: read-in records (generator)
    :param OAIEADWriter oaipmh_writer: write harvester content in fs files
    :param Logger log: logger
    """
    for record in records:
        if record is None:
            # PniaOAIItemIterator raised an error before creating a record
            continue
        url = record.harvested_url
        if record.error:
            log.warning("%s. Skip the record: %r", url, record.error)
            continue
        if record.deleted:
            log.info("%s. The record with identifier: %r is to be deleted",
                     url, record.header.identifier)
            oaipmh_writer.add_record(record)
            continue
        if record.ead is None:
            log.warning("%s. Skip the record: no metadata found", url)
            continue
        identifier = record.header.identifier
        if identifier is None:
            msg = "%s. Skip the record: no identifier found"
            log.warning(msg, url)
            continue
        eadid = record.eadid
        if not eadid:
            msg = "%s. Skip the record: no EADID value found for record %r"
            log.warning(msg, url, identifier)
            continue
        if not eadid.startswith(service_code):
            msg = (
                '%s. Skip the record: EADID value "%r" found for record %r is not valid: '
                "value does not start with service code"
            )
            log.warning(msg, url, eadid, identifier)
        if record.ead.find("archdesc") is None:
            msg = "%s. Skip the record: no archdesc value found for record %r (eadid %r)"
            log.error(msg, url, identifier, eadid)
            continue
        if record.ead.find("archdesc/did") is None:
            msg = "%s. no archdesc.did value found for record %r (eadid %r) - skip the record"
            log.error(msg, url, identifier, eadid)
            continue
        log.info("%s. Downloaded identifier: %s, eadid: %s", url, identifier, eadid)
        oaipmh_writer.add_record(record)


def import_records(store, oaipmh_writer, reader, es, service_infos, log):
    """ Import records in the database

    :param RQLObjectStore store: store
    :param OAIEADWriter oaipmh_writer: write harvester content in fs files
    :param OAIEadReader reader: OAI DC schema reader
    :param Elasticsearch es: elasticsearch connection
    :param dict service_infos: service information
    :param Logger log: logger

    :returns: list of EsDocuments
    """
    filepaths = []
    es_docs = []
    service = None
    if "code" in service_infos and "eid" not in service_infos:
        services_map = load_services_map(store._cnx)
        service = services_map.get(service_infos["code"])
        if service:
            service_infos.update({"name": service.publisher(), "eid": service.eid})
    for i, record in enumerate(oaipmh_writer.oai_records):
        identifier = record.header.identifier
        oai_id = oai_utils.compute_oai_id(service_infos["oai_url"], identifier)
        if record.deleted:
            # delete the FindingAid if exists
            res = store._cnx.execute(
                """
            Any FSPATH(D) WHERE X is FindingAid,
            X oai_id %(oai_id)s,
            X findingaid_support FS, FS data D
            """,
                {"oai_id": oai_id},
            )
            if res:
                filepath = res[0][0].getvalue()
                delete_from_filename(
                    reader.store._cnx, filepath, interactive=False, esonly=reader.config["esonly"]
                )
                log.info(
                    "deleted record %r: remove the corresponding FindingAid %s",
                    identifier,
                    filepath,
                )
            continue
        eadid = record.eadid
        log.info("importing %r, eadid %r", identifier, eadid)
        file_path = usha1(oaipmh_writer.get_file_path(eadid))
        # stable_id are computed from file_path, not from eadid
        if file_path in filepaths:
            msg = (
                "record %r, eadid %r ignored: "
                "a record with the same eadid "
                "has already been imported"
            )
            log.error(msg, identifier, eadid)
            continue
        filepaths.append(file_path)
        file_contents = oaipmh_writer.get_file_contents(record.ead)
        file_path = oaipmh_writer.dump(eadid, file_contents)
        findingaid_support = reader.create_file(file_path)
        if findingaid_support is None:
            # the file exists and will not be reimported
            continue
        try:
            esdoc = reader.import_ead_xmltree(
                record.ead, service_infos, fa_support=findingaid_support, oai_id=oai_id
            )
        except InvalidFindingAid as exception:
            log.exception("failed to import %r (eadid %r) %r", identifier, eadid, exception)
            continue
        except Exception:
            log.exception("failed to import %r (eadid %r)", identifier, eadid)
            import traceback

            traceback.print_exc()
            continue
        es_docs.extend(esdoc)
        if not reader.config["esonly"]:
            store.flush()
    return es_docs
