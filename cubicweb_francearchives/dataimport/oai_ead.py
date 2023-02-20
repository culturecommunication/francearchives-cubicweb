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
    oai_utils,
    usha1,
    OAIPMH_EAD_PATH,
    InvalidFindingAid,
)

from cubicweb_francearchives.dataimport.ead import Reader
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


class OAIEADImporter(object):
    """OAI EAD schema importer.

    :ivar dict config: server-side configuration
    :ivar Reader reader: EAD schema reader
    :ivar Connection cnx: connection
    :ivar es: Elasticsearch connection
    """

    def __init__(self, store, config, service_infos, log):
        """Initialize OAI DC schema reader.

        :param RQLObject store: store
        :param dict config: server-side configuration
        :param dict service_infos: service information
        :param Logger log: logger
        """
        self.log = log
        self.config = config
        self.reader = Reader(self.config, store)
        self.cnx = self.reader.store._cnx
        indexer = self.cnx.vreg["es"].select("indexer", self.cnx)
        self.es = indexer.get_connection()
        self.complete_list_size = None
        self.downloaded = 0
        cwconfig = self.cnx.vreg.config
        self.service_infos = service_infos
        self.oaipmh_writer = OAIEADWriter(
            cwconfig["ead-services-dir"],
            self.service_infos,
            subdirectories=OAIPMH_EAD_PATH.split("/"),
        )

    def download_records(self, records):
        """Harvest data and check them containing the needed information

        :param function records: read-in records (generator)
        """
        service_code = self.service_infos["code"]
        for record in records:
            if record is None:
                # PniaOAIItemIterator raised an error before creating a record
                continue
            self.downloaded += 1
            try:
                cursor = int(record.cursor) + 1
            except Exception:
                cursor = self.downloaded
            if self.complete_list_size is None:
                try:
                    self.complete_list_size = int(record.complete_list_size)
                    self.log.info(
                        "Repository contains %s documents (completeListSize).",
                        self.complete_list_size,
                    )
                except TypeError:
                    pass
            urlinfo = "<div>{url}<div><div>(record {cur} out of {lsz}).</div>".format(
                url=record.harvested_url, cur=cursor, lsz=self.complete_list_size or "?"
            )
            if record.error:
                if not hasattr(record, "metadata"):
                    self.log.warning("%s Skip the record: no metadata found", urlinfo)
                else:
                    self.log.warning("%s Skip the record: %r", urlinfo, record.error)
                continue
            if record.deleted:
                self.log.warning(
                    "%s The record with identifier: %r is to be deleted",
                    urlinfo,
                    record.header.identifier,
                )
                self.oaipmh_writer.add_record(record)
                continue
            if record.ead is None:
                self.log.warning("%s Skip the record: no metadata found", urlinfo)
                continue
            identifier = record.header.identifier
            if identifier is None:
                msg = "%s Skip the record: no identifier found"
                self.log.warning(msg, urlinfo)
                continue
            eadid = record.eadid
            if not eadid:
                msg = "%s Skip the record: no EADID value found for record %r"
                self.log.warning(msg, urlinfo, identifier)
                continue
            if not eadid.startswith(service_code):
                msg = (
                    '%s EADID value "%r" found for record %r is not valid: '
                    "value does not start with service code. Import it anyway."
                )
                self.log.warning(msg, urlinfo, eadid, identifier)
            if record.ead.find("archdesc") is None:
                msg = "%s Skip the record: no archdesc value found for record %r (eadid %r)"
                self.log.error(msg, urlinfo, identifier, eadid)
                continue
            if record.ead.find("archdesc/did") is None:
                msg = "%s Skip the record: no archdesc.did value found for record %r (eadid %r)"
                self.log.error(msg, urlinfo, identifier, eadid)
                continue
            self.log.info("%s Oai identifier: %s, eadid: %s", urlinfo, identifier, eadid)
            self.oaipmh_writer.add_record(record)

    def harvest_records(self, headers=None, **params):
        """Import records.

        :param dict headers: headers for harvest
        :param dict params: harvest parameters
        """
        oai_ead_mapping = {
            "ListRecords": OAIEADRecord,
            "GetRecord": OAIEADRecord,
        }
        client = oai_utils.PniaSickle(
            self.service_infos["oai_url"],
            iterator=oai_utils.PniaOAIItemIterator,
            class_mapping=oai_ead_mapping,
            headers=headers,
            retry_status_codes=(500, 502, 503),
        )
        client.logger = self.log
        records = client.ListRecords(**params)
        # harvest records
        try:
            self.download_records(records)
        except oai_utils.OAIXMLError as error:
            self.log.error(error)
        except Exception:
            formatted_exc = traceback.format_exc()
            self.log.error("Could not import record %s. Harvesting aborted.", formatted_exc)
        if self.complete_list_size is None:
            self.log.warning(
                """Processed %s records.
                No information about records list size (completeListSize) could be found.""",
                self.downloaded,
            )
        else:
            if self.downloaded < self.complete_list_size:
                self.log.error(
                    "only {} out of {} records have been processed.".format(
                        self.downloaded, self.complete_list_size
                    )
                )
            else:
                self.log.info("downloaded all {} record(s)".format(self.complete_list_size))

    def import_records(self):
        """import records in the database"""
        if not self.oaipmh_writer.oai_records:
            self.log.info("No records found")
            return
        self.reader.update_authorities_cache(self.service_infos.get("eid"))
        store = self.reader.store
        es_docs = self._import_records(store)
        if not self.reader.config["esonly"]:
            store.finish()
        return es_docs

    def _import_records(self, store):
        """Import records in the database

        :param RQLObjectStore store: store
        :param OAIEADWriter oaipmh_writer: write harvester content in fs files
        :param OAIEadReader reader: OAI DC schema reader
        :param dict service_infos: service information

        :returns: list of EsDocuments
        """
        filepaths = []
        es_docs = []
        for i, record in enumerate(self.oaipmh_writer.oai_records):
            identifier = record.header.identifier
            oai_id = oai_utils.compute_oai_id(self.service_infos["oai_url"], identifier)
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
                        self.reader.store._cnx,
                        filepath,
                        interactive=False,
                        esonly=self.reader.config["esonly"],
                    )
                    self.log.info(
                        "deleted record %r: remove the corresponding FindingAid %s",
                        identifier,
                        filepath,
                    )
                continue
            eadid = record.eadid
            self.log.info("importing %r, eadid %r", identifier, eadid)
            file_usha1 = usha1(self.oaipmh_writer.get_file_path(eadid))
            # stable_id are computed from file_path, not from eadid
            if file_usha1 in filepaths:
                msg = (
                    "record %r, eadid %r ignored: "
                    "a record with the same eadid "
                    "has already been imported"
                )
                self.log.error(msg, identifier, eadid)
                continue
            filepaths.append(file_usha1)
            file_contents = self.oaipmh_writer.get_file_contents(record.ead)
            file_path = self.oaipmh_writer.dump(eadid, file_contents)
            fa_support = self.reader.create_file(file_path)
            if fa_support is None:
                # the file exists and will not be reimported
                continue
            try:
                esdoc = self.reader.import_ead_xmltree(
                    record.ead, self.service_infos, fa_support, oai_id=oai_id
                )
            except InvalidFindingAid as exception:
                self.log.exception(
                    "failed to import %r (eadid %r) %r", identifier, eadid, exception
                )
                continue
            except Exception:
                self.log.exception("failed to import %r (eadid %r)", identifier, eadid)
                import traceback

                traceback.print_exc()
                continue
            es_docs.extend(esdoc)
            if not self.reader.config["esonly"]:
                store.flush()
        return es_docs


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
