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

from collections import defaultdict

from isodate import datetime_isoformat

from lxml import etree
from lxml.builder import E, ElementMaker

from sickle.models import Record
from sickle.utils import get_namespace

from cubicweb.utils import json_dumps

from cubicweb_oaipmh import utcnow

from cubicweb_francearchives.dataimport import (
    usha1,
    clean_values,
    get_year,
    get_date,
    strip_html,
    component_stable_id_for_dc,
)
from cubicweb_francearchives.dataimport import (
    oai_utils,
    OAIPMH_DC_PATH,
)

from cubicweb_francearchives.dataimport.dc import CSVReader

from cubicweb_francearchives.dataimport.ead import readerconfig, service_infos_for_es_doc
from cubicweb_francearchives.storage import S3BfssStorageMixIn
from cubicweb_francearchives.dataimport.sqlutil import delete_from_filename


class OAIDCWriter(oai_utils.OAIPMHWriter):
    """OAI-PMH writer (Dublin Core).

    :cvar str OAI_VERB: verb of the OAI-PMH request
    :ivar list oai_records: list of records
    """

    OAI_VERB = "ListRecords"

    def __init__(self, ead_services_dir, service_infos, subdirectories=[]):
        """Initialize OAI-PMH writer (Dublin Core).

        :param str ead_services_dir: location of backup files
        :param dict service_infos: service information
        :param list subdirectories: list of subdirectories
        """
        super(OAIDCWriter, self).__init__(
            ead_services_dir, service_infos, subdirectories=subdirectories
        )
        self.oai_records = defaultdict(list, {})

    def add_record(self, record):
        """Add record to list of records.

        :param _Element record: record
        """
        # check on the eadid is done before this method is called
        eadid = record.header.setSpecs[0]
        self.oai_records[eadid].append(record)

    def to_xml(self, eadid):
        """Convert records to XML file format compliant tree.

        :param str eadid: EAD ID

        :returns: element factory
        :rtype: ElementMaker
        """
        date = E.responseDate(datetime_isoformat(utcnow()))
        nsmap = {
            None: "http://www.openarchives.org/OAI/2.0/",
            "xsi": "http://www.w3.org/2001/XMLSchema-instance",
        }
        maker = ElementMaker(nsmap=nsmap)
        attributes = {
            "{%s}schemaLocation"
            % nsmap["xsi"]: " ".join(
                [
                    "http://www.openarchives.org/OAI/2.0/",
                    "http://www.openarchives.org/OAI/2.0/OAI-PMH.xsd",
                ]
            )
        }
        oai_records = [record.xml for record in self.oai_records[eadid]]
        body_elements = [E(self.OAI_VERB, *oai_records)]
        return maker("OAI-PMH", date, *body_elements, **attributes)

    def get_file_contents(self, eadid):
        """Get file contents.

        :param str eadid: EAD ID
        """
        file_contents = etree.tostring(self.to_xml(eadid), encoding="utf-8", xml_declaration=True)
        return file_contents


def build_header(header):
    # check on the eadid is done before this method is called
    setNames = [setName.text for setName in header.xml.findall(header._oai_namespace + "setName")]
    eadid = header.setSpecs[0]
    return {
        "identifier": header.identifier,
        "eadid": eadid,
        "name": setNames[0] if setNames else eadid,
    }


def build_metadata(data):
    keys = [
        "title",
        "creator",
        "subject",
        "description",
        "publisher",
        "contributor",
        "type",
        "format",
        "identifier",
        "source",
        "language",
        "relation",
        "coverage",
        "rights",
    ]
    metadata = dict.fromkeys(keys, [])
    metadata.update(data)
    start = stop = None
    if "date" in metadata:
        date = metadata.pop("date")[0]
        if "-" in date:
            try:
                start, stop = [d.strip() for d in date.split("-")]
            except ValueError:
                pass
        else:
            try:
                start = date.strip()
                stop = None
            except ValueError:
                pass
    metadata["date1"] = get_year(start)
    metadata["date2"] = get_year(stop)
    return metadata


EXTIDS = {"ConceptScheme": "siaf", "IndexRole": "virtual-exhibit"}


class OAIDCRecord(Record):
    def __init__(self, record_element, strip_ns=True):
        self.error = None
        try:
            super(OAIDCRecord, self).__init__(record_element, strip_ns=strip_ns)
        except Exception as e:
            self.error = e
            return
        self.harvested_url = ""


class OAIDCImporter:
    """OAI DC schema importer.

    :ivar dict config: server-side configuration
    :ivar OAIDCReader reader: OAI DC schema reader
    :ivar Connection cnx: connection
    :ivar es: Elasticsearch connection
    """

    def __init__(self, store, config, service_infos, log=None):
        """Initialize OAI DC schema reader.

        :param RQLObject store: store
        :param dict config: server-side configuration
        :param dict service_infos: service information
        :param Logger log: logger
        """
        cwconfig = store._cnx.vreg.config
        if log is None:
            log = logging.getLogger("rq.task")
        self.log = log
        self.storage = S3BfssStorageMixIn()
        if config is None:
            config = readerconfig(
                cwconfig,
                cwconfig.appid,
                log=self.log,
                esonly=False,
                nodrop=True,
                reimport=True,
                force_delete=True,
            )
        self.config = config
        self.reader = OAIDCReader(self.config, store)
        self.cnx = self.reader.store._cnx
        self.complete_list_size = None
        self.downloaded = 0
        indexer = self.cnx.vreg["es"].select("indexer", self.cnx)
        self.es = indexer.get_connection()
        self.service_infos = service_infos
        self.oaipmh_writer = OAIDCWriter(
            store._cnx.vreg.config["ead-services-dir"],
            self.service_infos,
            subdirectories=OAIPMH_DC_PATH.split("/"),
        )

    def download_records(self, records):
        """Harvest data and check they contain the needed information
        :param function records: read-in records (generator)
        """
        service_code = self.service_infos["code"]
        for record in records:
            if record is None:
                # PniaOAIItemIterator raised an error before creating a record
                continue
            self.downloaded += 1
            identifier = record.header.identifier
            # eadid is caclulated from header.setSpec()
            eadid = record.header.setSpecs
            try:
                cursor = int(record.cursor) + 1
            except Exception:
                cursor = self.downloaded
            if self.complete_list_size is None:
                try:
                    self.complete_list_size = int(record.complete_list_size)
                except TypeError:
                    pass
            urlinfo = "<div>{url}<div><div>(record {cur} out of {lsz}).</div>".format(
                url=record.harvested_url, cur=cursor, lsz=self.complete_list_size or "?"
            )
            if record.deleted:
                self.log.info(
                    "%s The record with identifier is to be deleted: %r", urlinfo, identifier
                )
                self.oaipmh_writer.add_record(record)
                continue
            if eadid:
                eadid = eadid[0].strip()
            if not eadid:
                warning = (
                    "%s Ignoring identifier %r because unspecified setSpec "
                    "which is used as eadid value"
                )
                self.log.warning(warning, urlinfo, identifier)
                continue
            if not record.metadata.get("title"):
                warning = (
                    "%s Ignoring identifier %r because unspecified dc_title "
                    "which is used as unittitle"
                )
                self.log.warning(warning, urlinfo, identifier)
                continue
            if not eadid.startswith(service_code):
                msg = (
                    '%s EADID value "%r" found for record %r is not valid:'
                    "value does not starts with service_code. Import it anyway."
                )
                self.log.warning(msg, urlinfo, eadid, identifier)
            self.log.info("%s Oai identifier: %s, eadid: %s", urlinfo, identifier, eadid)
            self.oaipmh_writer.add_record(record)

    def download_from_file(self, filepath):
        data = self.storage.storage_get_oaifile_content(filepath)
        try:
            tree = etree.parse(data)
        except Exception:
            self.log.exception('Could not process file "%r"', filepath)
            return
        if hasattr(tree, "getroot"):
            root = tree.getroot()
        else:
            root = tree
        records = root.findall("{ns}ListRecords/{ns}record".format(ns=get_namespace(root)))
        for record_element in records:
            self.oaipmh_writer.add_record(OAIDCRecord(record_element))

    def harvest_records(self, from_file=False, headers=None, **params):
        """Import records.

        :param bool from_file: data origin (True for file, False for harvesting)
        :param dict headers: headers for harvest
        :param dict params: harvest parameters
        """
        print("download_records", self.service_infos, from_file, headers, params)
        base_url = self.service_infos["oai_url"]
        if not from_file:
            oai_mapping = {
                "ListRecords": OAIDCRecord,
                "GetRecord": OAIDCRecord,
            }
            client = oai_utils.PniaSickle(
                base_url,
                iterator=oai_utils.PniaOAIItemIterator,
                class_mapping=oai_mapping,
                headers=headers,
                retry_status_codes=(500, 502, 503),
            )
            client.logger = self.log
            records = client.ListRecords(**params)
            try:
                self.download_records(records)
            except oai_utils.OAIXMLError as error:
                self.log.error(error)
            except Exception as exception:
                self.log.error(("Could not import records: %s. Harvesting aborted.", exception))
                if not self.oaipmh_writer.oai_records:
                    return
        else:
            self.download_from_file(base_url)
        if self.complete_list_size is None:
            self.log.warning(
                """Downloaded %s records.
                No information about records list size (completeListSize) could be found""",
                self.downloaded,
            )
        else:
            if self.downloaded < self.complete_list_size:
                self.log.error(
                    "only {} out of {} records have been downloaded".format(
                        self.downloaded, self.complete_list_size
                    )
                )
            else:
                self.log.info("downloaded all {} record(s)".format(self.complete_list_size))
        if from_file and self.oaipmh_writer.oai_records:
            self.import_records(from_file=from_file)

    def import_records(self, from_file=False):
        """import records in the database"""
        if not self.oaipmh_writer.oai_records:
            self.log.info("No records found")
            return

        self.reader.update_authorities_cache(self.service_infos.get("eid"))
        es_docs = self._import_records(from_file=from_file)
        if from_file:
            # in this case only return es_docs as
            # flush/commit and es_bulk_index are done in
            # the calling `importer._findingaid_importer` function
            return es_docs
        store = self.reader.store
        if not self.reader.config["esonly"]:
            store.finish()
            store.commit()
        return es_docs

    def _import_records(self, from_file=False):
        """Import records in the database
        :param OAIDCWriter oaipmh_writer: write harvester content in fs files
        :param dict service_infos: service information
        """
        es_docs = []
        for eadid in list(self.oaipmh_writer.oai_records.keys()):
            file_contents = self.oaipmh_writer.get_file_contents(eadid)
            if not from_file:
                # not not rewrite the file from which data are beeing imported
                self.oaipmh_writer.dump(eadid, file_contents)
            for record in self.oaipmh_writer.oai_records[eadid]:
                self.log.info("importing %r, eadid %r", record.header.identifier, eadid)
                header = build_header(record.header)
                metadata = build_metadata(record.metadata)
                if record.deleted:
                    self.reader.delete_findingaid(header, self.service_infos)
                try:
                    esdoc = self.reader.import_record(
                        header, metadata, self.oaipmh_writer, self.service_infos
                    )
                except Exception:
                    import traceback

                    traceback.print_exc()
                    print("failed to import", repr(eadid))
                    self.log.exception("failed to import %r", eadid)
                    continue
                es_docs.extend(esdoc)
        if not from_file or not self.reader.config["esonly"]:
            self.reader.store.flush()
        return es_docs


class OAIDCReader(CSVReader):
    """OAI DC schema reader."""

    def __init__(self, config, store):
        super(CSVReader, self).__init__(config, store)
        self._created_fa = {}

    def richstring_html(self, data, attr):
        if data:
            if not isinstance(data, (list, tuple)):
                data = [data]
            return self.richstring_template.format(data=" ".join(data), attr=attr)
        return None

    def import_record(self, header, metadata, oaipmh_writer, service_infos):
        """Generate extentities read from `record` etree"""
        eadid = header["eadid"]
        filepath = oaipmh_writer.get_file_path(eadid)
        creation_date = self.creation_date_from_filepath(filepath)
        fa_key = usha1(eadid)
        fa_es_doc = self._created_fa.get(fa_key)
        es_docs = []
        if fa_es_doc is None:
            # directory exists, will not be overwritten
            findingaid_support = self.create_file(filepath)
            self.delete_from_filename(filepath)
            ir_name, stable_id = self.process_existing_findingaids(eadid, findingaid_support)
            header.update({"stable_id": stable_id, "irname": ir_name})
            metadata["creation_date"] = creation_date
            fa_es_doc = self.import_findingaid(header, metadata, service_infos, findingaid_support)
            self._created_fa[fa_key] = fa_es_doc
            es_docs.append(fa_es_doc)
        fa_data = fa_es_doc["_source"].copy()
        fa_data.update({"service": service_infos.get("eid"), "creation_date": creation_date})
        es_doc = self.import_facomponent(metadata, fa_data, header["identifier"], service_infos)
        if es_doc:
            es_docs.append(es_doc)
        return es_docs

    def delete_findingaid(self, header, service_infos):
        # delete the. FindingAid if exists
        identifier = header["identifier"]
        res = self.store._cnx.execute(
            """
        Any FSPATH(D) WHERE X is FindingAid,
        X oai_id %(oai_id)s,
        X findingaid_support FS, FS data D
        """,
            {"oai_id": oai_utils.compute_oai_id(service_infos["oai_url"], identifier)},
        )
        if res:
            filepath = res[0][0].getvalue()
            delete_from_filename(
                self.store._cnx, filepath, interactive=False, esonly=self.config["esonly"]
            )
            self.log.info(
                "deleted record %r: remove the corresponding FindingAid %s", identifier, filepath
            )

    def import_findingaid(self, header, metadata, service_infos, findingaid_support):
        name = header["name"] or "Sans titre"
        did_attrs = {
            "unittitle": name,
        }
        did_data = self.create_entity("Did", clean_values(did_attrs))
        fa_header_data = self.create_entity("FAHeader", {"titleproper": name})
        publisher = service_infos.get("name")
        if not publisher:
            publisher = "; ".join(metadata["publisher"]) or "XXX"
        fa_attrs = {
            "name": header["irname"],
            "eadid": header["eadid"],
            "did": did_data["eid"],
            "publisher": publisher,
            "service": service_infos.get("eid"),
            "stable_id": header["stable_id"],
            "fa_header": fa_header_data["eid"],
            "findingaid_support": findingaid_support["eid"],
            "oai_id": oai_utils.compute_oai_id(service_infos["oai_url"], header["identifier"]),
        }
        fa_attrs["creation_date"] = metadata["creation_date"]
        fa_data = self.create_entity("FindingAid", clean_values(fa_attrs))
        fa_es_attrs = {
            "name": fa_data["name"],
            "fa_stable_id": fa_data["stable_id"],
            "scopecontent": strip_html(fa_attrs.get("scopecontent")),
            **service_infos_for_es_doc(self.store._cnx, service_infos),
        }
        es_doc = self.build_complete_es_doc(
            "FindingAid", fa_data, did_data, index_entries={}, **fa_es_attrs
        )
        self.create_entity(
            "EsDocument", {"doc": json_dumps(es_doc["_source"]), "entity": fa_data["eid"]}
        )
        return es_doc

    def digitized_version(self, metadata):
        dao = []
        for url in metadata["identifier"]:
            dao.append({"url": url})
        for illustration_url in metadata["relation"]:
            dao.append({"illustration_url": illustration_url})
        return dao

    def import_facomponent(self, metadata, findingaid_data, identifier, service_infos):
        fa_stable_id = findingaid_data["stable_id"]
        unittitle = " ; ".join(metadata["title"])
        # Use <header><identifier> to compute the stable_id
        # cf https://extranet.logilab.fr/ticket/64684874
        fac_stable_id = component_stable_id_for_dc(identifier, fa_stable_id)
        did_attrs = {
            "unitid": " ; ".join(metadata["source"]),
            "unittitle": unittitle,
            "unitdate": get_date(metadata["date1"], metadata["date2"]),
            "startyear": get_year(metadata["date1"]),
            "stopyear": get_year(metadata["date2"]),
            "physdesc": self.richstring_html(" ; ".join(metadata["format"]), "physdesc"),
            "physdesc_format": "text/html",
            "origination": " ; ".join(metadata["creator"]),
        }
        languages = " ; ".join(metadata["language"])
        if len(languages) < 4:
            did_attrs["lang_code"] = languages
        else:
            did_attrs["lang_description"] = self.richstring_html(languages, "language")
            did_attrs["lang_description_format"] = "text/html"
        did_data = self.create_entity("Did", clean_values(did_attrs))
        comp_attrs = {
            "finding_aid": findingaid_data["eid"],
            "stable_id": fac_stable_id,
            "did": did_data["eid"],
            "scopecontent": self.richstring_html(
                " ; ".join(metadata["description"]), "scopecontent"
            ),
            "scopecontent_format": "text/html",
            "userestrict": self.richstring_html(metadata["rights"], "userestrict"),
            "userestrict_format": "text/html",
        }
        comp_attrs["creation_date"] = findingaid_data.get("creation_date")
        comp_data = self.create_entity("FAComponent", clean_values(comp_attrs))
        # add daos
        comp_eid = comp_data["eid"]
        daodefs = self.digitized_version(metadata)
        for daodef in daodefs:
            digit_ver_attrs = self.create_entity("DigitizedVersion", clean_values(daodef))
            self.add_rel(comp_eid, "digitized_versions", digit_ver_attrs["eid"])
        else:
            digit_ver_attrs = {}
        indexes = self.index_entries(
            {
                "index_personne": metadata["contributor"],
                "index_lieu": metadata["coverage"],
                "index_matiere": metadata["subject"],
            },
            comp_eid,
            findingaid_data,
        )
        es_doc = self.build_complete_es_doc(
            "FAComponent",
            comp_data,
            did_data,
            name=findingaid_data["name"],
            fa_stable_id=fa_stable_id,
            publisher=findingaid_data["publisher"],
            index_entries=indexes,
            digitized=bool(daodefs),
            **service_infos_for_es_doc(self.store._cnx, service_infos),
        )
        self.create_entity("EsDocument", {"doc": json_dumps(es_doc["_source"]), "entity": comp_eid})
        return es_doc


def import_oai_dc_filepath(store, filepath, service_infos, config=None):
    base_url = "file://{}".format(filepath)
    service_infos["oai_url"] = base_url
    importer = OAIDCImporter(store, config, service_infos)
    return importer.harvest_records(from_file=True)
