# -*- coding: utf-8 -*-
#
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2021
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

from collections import defaultdict, OrderedDict
from datetime import datetime
import csv
import json

import logging
import pytz

from cubicweb_francearchives.dataimport import (
    load_services_map,
    strip_nones,
    sqlutil,
)
from cubicweb_francearchives.dataimport.oai_nomina import str2bool, compute_nomina_stable_id
from cubicweb_francearchives.storage import S3BfssStorageMixIn
from cubicweb_francearchives.entities.nomina import (
    NominaIndexJsonDataSerializable,
    NominaActCodeTypes,
    NominaESActCodeTypes,
    normalized_doctype_code,
)

NOMINA_ACT_TYPES = list(NominaActCodeTypes.keys()) + list(NominaESActCodeTypes.keys())


def invalid_doc_type(doctype):
    if not doctype:
        return True
    if doctype != "OAI" and normalized_doctype_code(doctype) not in NOMINA_ACT_TYPES:
        return True
    return False


COMMON_FIELDS = OrderedDict(
    (
        ("Cote du registre", "C_c"),
        ("Classe", "D_RM_y"),  # Date in nomina
        ("Bureau de recrutement", "L_RM_p"),  # not in nomina
        ("Code département de recrutement", "L_RM_dc"),
        ("Département de recrutement", "L_RM_d"),
        ("Code pays ou territoire de recrutement", "L_RM_cc"),
        ("Pays ou territoire de recrutement", "L_RM_c"),
        ("Nom", "P_n"),
        ("Prénoms", "P_f"),
        ("Année de naissance", "D_N_y"),
        ("Date de naissance", "D_N_d"),
        ("Commune de naissance", "L_N_p"),
        ("Code département naissance", "L_N_dc"),
        ("Département de naissance", "L_N_d"),
        ("Code pays ou territoire de naissance", "L_N_cc"),
        ("Pays ou territoire de naissance", "L_N_c"),
        ("Profession", "C_o"),  # profession
        ("Instruction générale", "C_e"),  # niveau
        ("Commune de résidence", "L_R_p"),
        ("Code département de résidence", "L_R_dc"),
        ("Département de résidence", "L_R_d"),
        ("Code pays ou territoire de résidence", "L_R_cc"),
        ("Pays ou territoire de résidence", "L_R_c"),
        ("Année de décès", "D_D_y"),
        ("Date de décès", "D_D_d"),
        ("Commune de décès", "L_D_p"),  # not in nomina, precision
        ("code département de décès", "L_D_dc"),
        ("Département décès", "L_D_d"),
        ("Code pays ou territoire de décès", "L_D_cc"),
        ("Pays ou territoire de décès", "L_D_c"),
        ("URI", "U"),
        ("Matricule", "C_n"),  # nro
        ("Mention", "C_m"),  # mention
        ("identifiant", "notice_id"),  # notice_id
        ("numerise", "C_d"),
        ("delete", "delete"),  # optional
    )
)


class CSVNominaFieldnames:
    fieldnames = {
        "OAI": OrderedDict(
            (
                ("stable_id", "stable_id"),
                ("oai_id", "oai_id"),
                ("json_data", "json_data"),
                ("service", "service"),
                ("delete", "delete"),
                ("harvested_url", "harvested_url"),
            )
        ),
    }


def readerconfig(cwconfig, **kwargs):
    config = {
        "nomina-index-name": cwconfig["nomina-index-name"],
    }
    config.update(kwargs)
    return config


def check_document_fieldnames(cnx, doctype, fieldnames):
    """
    :param Connection cnx: CubicWeb database connection
    :param String doctype   : CSV file data type
    :param List fieldnames : CSV file  fieldnames
    """
    errors = []
    if invalid_doc_type(doctype):
        errors.append("Abort import for unknown document type %s", doctype)
        return errors
    expected_fieldnames = CSVNominaFieldnames.fieldnames.get(doctype, COMMON_FIELDS)
    errors = []
    invalid_fieldnames = set(fieldnames).difference(expected_fieldnames.keys())
    if invalid_fieldnames:
        errors.append(
            cnx._('The document contains invalid fieldnames: "%s".') % ", ".join(invalid_fieldnames)
        )
    if list(fieldnames) != list(expected_fieldnames.keys()):
        if doctype != "OAI" and fieldnames + ["delete"] == list(expected_fieldnames.keys()):
            return errors
        errors.append(
            cnx._(
                'The document fieldnames are different or are in different order from expected ones: "%s".'  # noqa
            )
            % ", ".join(fieldnames)
        )
    if errors:
        errors.append(cnx._('Expected fieldnames are "%s"') % ", ".join(expected_fieldnames))
        return errors
    return errors


class CSVNominaReader(object):
    def __init__(self, config, store, service_code, log=None):
        """Initialize CSVNominaReader.

        :param dict config : reader configuration
        :param RQLObject store: store
        :param String service: service code
        :param Logger log: logger
        """
        self.config = config
        if log is None:
            log = logging.getLogger("rq.task")
        self.log = log
        self.store = store
        self.service = load_services_map(self.store._cnx)[service_code]
        self.created_records = 0
        self.updated_records = 0
        self.nomina_records_to_delete = []
        # keep tack of same_as relaitons
        self.linked_authorities = defaultdict(list)
        self.init_authorities_for_service()

    def init_authorities_for_service(self):
        rset = self.store.rql(
            """Any XS, A, L WHERE X is NominaRecord, X stable_id XS,
               X same_as A, A is AgentAuthority, A label L,
               X service S, S code %(code)s""",
            {"code": self.service.code},
        )
        for nomina_stable_id, auth_eid, label in rset:
            self.linked_authorities[nomina_stable_id].append((auth_eid, label))

    def create_entity(self, etype, attrs):
        attrs = strip_nones(attrs)
        eid = self.store.prepare_insert_entity(etype, **attrs)
        attrs["eid"] = eid
        return attrs

    def required_columns(self, doctype):
        if doctype == "OAI":
            return ("oai_id",)
        return ("notice_id",)

    def update_nomina_record(self, notice_eid, attrs):
        attrs = strip_nones(attrs)
        cursor = self.store._cnx.cnxset.cu
        cursor.execute(
            """
            UPDATE cw_nominarecord
            SET cw_json_data=%(json_data)s, cw_modification_date=NOW()
            WHERE cw_stable_id=%(stable_id)s
            """,
            attrs,
        )
        attrs["eid"] = notice_eid
        return attrs

    def delete_nomina_records(self):
        if self.nomina_records_to_delete:
            self.log.info(
                "Start deleting %s deprecated nomina records.", len(self.nomina_records_to_delete)
            )
            sqlutil.delete_nomina_records(
                self.store._cnx,
                self.nomina_records_to_delete,
                interactive=False,
            )
            self.log.info("End deleting deprecated nomina records.")

    def get_stable_id_for_delete(self, values):
        # import csv
        if "notice_id" in values:
            return compute_nomina_stable_id(self.service.code, values["notice_id"])
        # import oai
        rset = self.store._cnx.execute(
            """Any S WHERE X is NominaRecord,
                     X stable_id S,
                     X service %(s)s, X oai_id %(o)s""",
            {"o": values["oai_id"], "s": self.service.eid},
        )
        if rset:
            return rset[0][0]

    def import_records(self, filepath, doctype, delimiter=";"):
        """create NominaRecords

        :param String filepath  : Filepath to proc.[]ess
        :param String doctype   : CSV file data type
        :param String delimiter : CSV delimiter
        """
        if invalid_doc_type(doctype):
            self.log.error("Abort import for unknown document type %s", doctype)
            return
        fieldnames = CSVNominaFieldnames.fieldnames.get(doctype, COMMON_FIELDS)
        if doctype == "OAI":
            func = self.extract_nomina_data
        else:
            func = self.build_nomina_data
        required_columns = self.required_columns(doctype)
        st = S3BfssStorageMixIn()
        es_docs = []
        with st.storage_read_file(filepath) as stream:
            # check headers
            file_fieldnames = csv.DictReader(stream, delimiter=delimiter).fieldnames
            stream.seek(0)
            errors = check_document_fieldnames(self.store._cnx, doctype, file_fieldnames)
            if errors:
                self.log.error("Abort import: %s", "\n".join(errors))
                return es_docs
            reader = csv.DictReader(
                stream,
                delimiter=delimiter,
                fieldnames=list(fieldnames.keys()),
            )
            next(reader, None)  # skip the headers
            idx = 1
            identifiers = defaultdict(list)
            while True:  # _csv.Error: line contains NULL byte
                try:
                    line = next(reader)
                except csv.Error as exception:
                    self.log.warning(f"line {idx}: skipped line ({exception})")
                    idx += 1
                    continue
                except StopIteration:
                    break
                if not any(line.values()):
                    continue
                idx += 1
                values = {fieldnames[key]: value for key, value in line.items() if key and value}
                missing_required = False
                for attr in required_columns:
                    if not values.get(attr):
                        missing_required = True
                        colname = [col for col, _attr in fieldnames.items() if _attr == attr][0]
                        self.log.warning('line %s: skip the record: no "%s" found', idx, colname)
                if missing_required:
                    continue
                if values.get("delete") in ("y", "yes"):
                    stable_id = self.get_stable_id_for_delete(values)
                    if not stable_id:
                        self.log.warning(
                            "line %s: could not find stable id for delete: %s", idx, values
                        )

                        continue
                    self.nomina_records_to_delete.append(stable_id)
                    continue
                data = func(values, doctype)
                if data:
                    data["creation_date"] = datetime.now(pytz.utc)  # XXX to be corrected
                    identifier, column = self.get_identifier(values)
                    if identifier is None:
                        self.log.error("line %s: no identifier found in %s. Skip data", idx, data)
                        continue
                    duplicated = identifiers.get(identifier)
                    if duplicated:
                        self.log.error(
                            "line %s: duplicated identifier '%s' (column '%s') "
                            "found in line(s): %s. Skip data.",
                            idx,
                            identifier,
                            column,
                            ", ".join(duplicated),
                        )
                        identifiers[identifier].append(str(idx))
                        continue
                    identifiers[identifier].append(str(idx))
                    notice_eid = self._get_eid_from_notice_stable_id(data["stable_id"])
                    if notice_eid is not None:
                        nomina_attrs = self.update_nomina_record(notice_eid, data)
                        self.updated_records += 1
                    else:
                        nomina_attrs = self.create_entity("NominaRecord", data)
                        self.created_records += 1
                    notice_eid = nomina_attrs["eid"]
                    es_doc = self.build_es_doc(nomina_attrs)
                    es_docs.append(es_doc)
        self.delete_nomina_records()
        return es_docs

    def _get_eid_from_notice_stable_id(self, stable_id):
        """
        Return the eid of the nomina record having the given stable_id.
        If the nomina record does not exist, return None.

        :param stable_id: the stable_id
        """
        cursor = self.store._cnx.cnxset.cu
        cursor.execute(
            "SELECT cw_eid FROM cw_nominarecord WHERE cw_stable_id = %s LIMIT 1", (stable_id,)
        )
        result = cursor.fetchone()
        if result:
            return result[0]
        else:
            return None

    def build_es_source(self, attrs):
        authorities, labels = [], []
        for eid, label in self.linked_authorities.get(attrs["stable_id"], []):
            authorities.append(eid)
            labels.append(label)
        es_doc = {
            "service": self.service.eid,
            "cw_etype": "NominaRecord",
            "eid": attrs["eid"],
            "stable_id": attrs["stable_id"],
            "creation_date": attrs["creation_date"],
            "modification_date": attrs["creation_date"],
            "cwuri": self.store._cnx.build_url(f"basedenoms/{attrs['stable_id']}"),
            "authority": authorities,
        }
        json_data = json.loads(attrs["json_data"])
        es_doc.update(
            NominaIndexJsonDataSerializable(self.store._cnx, json_data).process_json_data(
                alltext=" ".join(labels)
            )
        )
        return es_doc

    def build_es_doc(self, attrs):
        return {
            "_op_type": "index",
            "_index": self.config["nomina-index-name"],
            "_type": "_doc",
            "_id": attrs["stable_id"],
            "_source": self.build_es_source(attrs),
        }

    def extract_nomina_data(self, values, doctype):
        """
        process CSV resulting from OAI-PMH harvest

        :param dict values  : processed CSV row
        """
        # check doctype
        data = json.loads(values["json_data"])
        oai_id = values["oai_id"]
        if not data.get("t"):
            self.log.error("Ignore notice %s without document type" % oai_id)
            return None
        # check persons data
        persons = data.get("p")
        if not persons or not len(persons) or not len(persons[0]):
            self.log.error("Ignore notice %s without personal data" % oai_id)
            return None
        return {
            "stable_id": values["stable_id"],
            "oai_id": oai_id,
            "service": self.service.eid,
            "json_data": values["json_data"],
        }

    def get_identifier(self, data):
        """get notice identifier

        :param dict data  : processed CSV row
        """
        if "notice_id" in data:
            return data["notice_id"], "notice_id"
        if "oai_id" in data:
            return data["oai_id"], "oai_id"

    def build_nomina_data(self, values, doctype):
        """Build NominaRecord data

        :param dict values  : processed CSV row
        :param dict doctype: document type

        """
        person_data = {}  # there is only one person by record
        complement_data = {}
        locations = defaultdict(dict)  # one event by record
        dates = defaultdict(dict)  # one event by record
        events = defaultdict(dict)
        # build data from values
        uri = values.pop("U", None)
        for key, value in values.items():
            if not value:
                continue
            section, code = key.split("_", 1)
            if section == "P":
                person_data[code] = value
            elif section in ("C"):
                if code == "o":
                    value = [value]
                if code in ("d", "p"):
                    value = str2bool(value)
                complement_data[code] = value
            elif section in "L":
                event, prec = code.split("_")
                locations[event].update({prec: value})
            elif section == "D":
                event, prec = code.split("_")
                dates[event].update({prec: value})
        if not person_data:
            return None
        # build events
        for key, value in dates.items():
            desc = {"d": value}
            loc = locations.pop(key, None)
            if loc:
                desc["l"] = loc
                events[key] = [desc]
        for key, value in locations.items():
            assert key not in events
            events[key] = [{"l": value}]
        json_data = {
            "t": doctype,
            "e": events,
            "p": [person_data],
            "c": complement_data,
            "i": values["notice_id"],
        }
        if uri:
            json_data["u"] = uri
        data = {
            "stable_id": compute_nomina_stable_id(self.service.code, values["notice_id"]),
            "service": self.service.eid,
            "json_data": json.dumps(json_data),
        }
        return data
