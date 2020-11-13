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

import csv
import os.path as osp

import logging

from cubicweb.utils import json_dumps
from cubicweb.dataimport.stores import RQLObjectStore

from cubicweb_francearchives import init_bfss
from cubicweb_francearchives.dataimport import (
    clean_row,
    strip_html,
    default_csv_metadata,
    get_date,
    get_year,
    clean_values,
    usha1,
    facomponent_stable_id,
    load_metadata_file,
    sqlutil,
    es_bulk_index,
    remove_extension,
    log_in_db,
    service_infos_from_filepath,
    load_services_map,
)
from cubicweb_francearchives.dataimport.ead import (
    Reader,
    capture_exception,
    service_infos_for_es_doc,
)

from cubicweb_francearchives.dataimport.stores import create_massive_store
from cubicweb_francearchives.dataimport.scripts.generate_ape_ead import (
    generate_ape_ead_from_other_sources,
)
from cubicweb_francearchives.dataimport.sqlutil import ead_foreign_key_tables

LOGGER = logging.getLogger()
CSV_METADATA_CACHE = {}


def parse_dc_csv(fpath):
    """Generate a data dict by CSV entry of `fpath`"""
    with open(fpath) as csvfile:
        dcreader = csv.DictReader(csvfile)
        for row in dcreader:
            # remove possible whitespaces in header names
            for key in list(row.keys()):
                value = row.pop(key) or ""
                row[key.strip()] = value.strip()
            yield row


def csv_metadata_without_cache(filepath, metadata_filepath=None):
    """if import is done from cms interface:
    - dont look for the metadata in the same direcrtory
    - dont use the cache"""
    filename = osp.basename(filepath)
    if not metadata_filepath:
        return default_csv_metadata(remove_extension(filename))
    return load_metadata_file(metadata_filepath, csv_filename=filename)[filename]


def csv_metadata_from_cache(filepath, metadata_filepath=None):
    """if import is done from CWCcommand `import_dc`:
    - look for the metadata in the same direcrtory
    - use the cache"""
    if metadata_filepath:
        return load_metadata_file(metadata_filepath)[osp.basename(filepath)]
    directory = osp.dirname(filepath)
    metadata_file = osp.join(directory, "metadata.csv")
    all_metadata = {}
    if not osp.isfile(metadata_file):
        LOGGER.warning("metadata.csv file is missing in directory %s", directory)
    elif metadata_file not in CSV_METADATA_CACHE:
        all_metadata = load_metadata_file(metadata_file)
        CSV_METADATA_CACHE[metadata_file] = all_metadata
    else:
        all_metadata = CSV_METADATA_CACHE[metadata_file]
    filename = osp.basename(filepath)
    if filename not in all_metadata:
        LOGGER.info("using dummy metadata for %s", filename)
        return default_csv_metadata(remove_extension(filename))
    return all_metadata[filename]


class CSVReader(Reader):
    """expected columns for FAComoponents are:
    ['identifiant_cote', 'date1', 'date2',
     'description', 'format', 'langue', 'index_collectivite',
     'index_lieu', 'conditions_acces', 'index_personne',
     'identifiant_URI', 'origine', 'conditions_utilisation',
     'source_complementaire', 'titre', 'type', 'source_image',
     'index_matiere']
    """

    def cleaned_rows(self, filepath):
        """check rows/files integrity"""
        csv_empty_value = 'Skip row  {row}: missing required value for column "{col}" \n'
        csv_missing_col = 'The required column "{col}" is missing \n'
        mandatory_columns = ("titre", "identifiant_cote")
        res = []
        for i, row in enumerate(parse_dc_csv(filepath)):
            errors = []
            if i == 0:
                errors.extend(
                    [csv_missing_col.format(col=col) for col in mandatory_columns if col not in row]
                )
                if errors:
                    break
            else:
                errors.extend(
                    [
                        csv_empty_value.format(row=i, col=col)
                        for col in mandatory_columns
                        if not row[col]
                    ]
                )
            if not errors:
                res.append(clean_row(row))
            else:
                self.log.warning(" ".join(errors))
        return res

    def import_filepath(self, services_map, filepath, metadata_filepath=None):
        service_infos = service_infos_from_filepath(filepath, services_map)
        self._stable_id_map = None
        sha1 = usha1(open(filepath).read())
        if not self.config["esonly"] and self.ignore_filepath(filepath, sha1):
            return []
        fa_support = self.create_file(filepath, sha1=sha1)
        if fa_support is None:
            return []
        if not self.config.get("dc_no_cache"):
            metadata = csv_metadata_without_cache(filepath, metadata_filepath)
        else:
            metadata = csv_metadata_from_cache(filepath, metadata_filepath)
        self.update_authorities_cache(service_infos.get("eid"))
        creation_date = self.creation_date_from_filepath(filepath)
        metadata["creation_date"] = creation_date
        fa_es_doc = self.import_findingaid(service_infos, metadata, fa_support)
        es_docs = [fa_es_doc]
        # findingaid_attrs should probably not be based on es_documents, but
        # so far it contains all needed values except "service" needed for "index_entries"
        # method
        findingaid_attrs = {k: v for k, v in fa_es_doc["_source"].items()}
        findingaid_attrs.update(
            {"service": service_infos.get("eid"), "creation_date": creation_date}
        )
        for order, row in enumerate(self.cleaned_rows(filepath)):
            es_docs.append(self.import_facomponent(row, findingaid_attrs, order, service_infos))
        self.delete_from_filename(filepath)
        return es_docs

    def import_facomponent(self, entry, findingaid_data, order, service_infos):
        fa_stable_id = findingaid_data["stable_id"]
        cote = entry["identifiant_cote"]
        did_attrs = {
            "unitid": cote,
            "unittitle": entry["titre"],
            "unitdate": get_date(entry.get("date1"), entry.get("date2")),
            "startyear": get_year(entry.get("date1")),
            "stopyear": get_year(entry.get("date2")),
            "physdesc": self.richstring_html(entry.get("format"), "physdesc"),
            "physdesc_format": "text/html",
            "origination": entry.get("origine"),
            "lang_description": self.richstring_html(entry.get("langue"), "language"),
            "lang_description_format": "text/html",
        }
        did_data = self.create_entity("Did", clean_values(did_attrs))
        comp_attrs = {
            "finding_aid": findingaid_data["eid"],
            "stable_id": facomponent_stable_id(cote, fa_stable_id),
            "did": did_data["eid"],
            "scopecontent": self.richstring_html(entry.get("description"), "scopecontent"),
            "scopecontent_format": "text/html",
            "additional_resources": self.richstring_html(
                entry.get("source_complementaire"), "additional_resources"
            ),
            "additional_resources_format": "text/html",
            "accessrestrict": self.richstring_html(entry.get("conditions_acces"), "accessrestrict"),
            "accessrestrict_format": "text/html",
            "userestrict": self.richstring_html(entry.get("conditions_utilisation"), "userestrict"),
            "userestrict_format": "text/html",
            "component_order": order,
        }
        comp_attrs["creation_date"] = findingaid_data["creation_date"]
        comp_data = self.create_entity("FAComponent", clean_values(comp_attrs))
        comp_eid = comp_data["eid"]
        # add daos
        daodef = self.digitized_version(entry)
        if daodef:
            digit_ver_attrs = self.create_entity("DigitizedVersion", clean_values(daodef))
            self.add_rel(comp_eid, "digitized_versions", digit_ver_attrs["eid"])
        es_doc = self.build_complete_es_doc(
            "FAComponent",
            comp_data,
            did_data,
            name=findingaid_data["name"],
            fa_stable_id=findingaid_data["stable_id"],
            publisher=findingaid_data["publisher"],
            scopecontent=strip_html(comp_attrs.get("scopecontent")),
            index_entries=self.index_entries(entry, comp_eid, findingaid_data),
            digitized=bool(daodef),
            digitized_versions=daodef,
            **service_infos_for_es_doc(self.store._cnx, service_infos),
        )
        self.create_entity("EsDocument", {"doc": json_dumps(es_doc["_source"]), "entity": comp_eid})
        return es_doc

    def digitized_version(self, entry):
        identifiant_uri = entry.get("identifiant_uri")
        source_image = entry.get("source_image")
        if any((identifiant_uri, source_image)):
            return {"url": identifiant_uri, "illustration_url": source_image}
        return {}


def import_filepaths(cnx, config, filepaths, metadata_filepath=None):
    for filepath in filepaths:
        import_filepath(cnx, config, filepath, metadata_filepath=None)


@log_in_db
def import_filepath(cnx, config, filepath, metadata_filepath=None):
    foreign_key_tables = ead_foreign_key_tables(cnx.vreg.schema)
    if not config["esonly"]:
        store = create_massive_store(cnx, nodrop=config["nodrop"])
        store.master_init()
        if config["nodrop"]:
            with sqlutil.sudocnx(cnx, interactive=False) as su_cnx:
                sqlutil.disable_triggers(su_cnx, foreign_key_tables)
        cnx.commit()
    csv_import_filepath(cnx, config, filepath, metadata_filepath)
    if not config["esonly"]:
        store.finish()
        store.commit()
    if config["nodrop"]:
        with sqlutil.sudocnx(cnx, interactive=False) as su_cnx:
            sqlutil.enable_triggers(su_cnx, foreign_key_tables)
    generate_ape_ead_from_other_sources(cnx)


def csv_import_filepath(cnx, config, filepath, metadata_filepath=None):
    """Import a finding aid from `fpath` CSV file possibly using `metadata_filepath`
    CSV file"""

    services_map = load_services_map(cnx)
    # bfss should be initialized to enable `FSPATH` in rql
    init_bfss(cnx.repo)
    if not config["esonly"]:
        store = create_massive_store(cnx, slave_mode=True)
    else:
        store = RQLObjectStore(cnx)
    readercls = config.get("readercls", CSVReader)
    reader = readercls(config, store)
    es_docs = []
    try:
        es_docs = reader.import_filepath(services_map, filepath, metadata_filepath)
    except Exception as exc:
        import traceback

        traceback.print_exc()
        print("failed to import", repr(filepath))
        LOGGER.exception("failed to import %r", filepath)
        capture_exception(exc, filepath)
        return
    if not config["esonly"]:
        store.flush()
        store.commit()
    if es_docs and not config["noes"]:
        indexer = cnx.vreg["es"].select("indexer", cnx)
        es = indexer.get_connection()
        es_bulk_index(es, es_docs)
