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
import glob

from lxml import etree

import logging

from mock import patch

import unittest
import os
import os.path

from datetime import datetime

from cubicweb_francearchives.testutils import EADImportMixin, PostgresTextMixin, OaiSickleMixin
from cubicweb_francearchives.dataimport import oai


from cubicweb.devtools.testlib import CubicWebTC
from cubicweb_francearchives.testutils import format_date
from cubicweb_francearchives.dataimport import (
    sqlutil,
    usha1,
    load_services_map,
    service_infos_from_service_code,
)

from pgfixtures import setup_module, teardown_module  # noqa


class OaiEadImportTC(EADImportMixin, PostgresTextMixin, OaiSickleMixin, CubicWebTC):
    def filepath(self):
        assert self.filename is not None
        return self.datapath(os.path.join("oai_ead", self.filename))

    def tearDown(self):
        """Tear down test cases."""
        super(OaiEadImportTC, self).tearDown()
        if os.path.exists(self.path):
            for filename in glob.glob(os.path.join(self.path, "*")):
                os.remove(filename)
            os.removedirs(self.path)

    @classmethod
    def init_config(cls, config):
        super(OaiEadImportTC, cls).init_config(config)
        config.set_option(
            "consultation-base-url",
            "https://francearchives.fr",
        )
        config.set_option("ead-services-dir", "/tmp")

    def create_repo(self, cnx, url):
        return cnx.create_entity(
            "OAIRepository", name="{} repo".format(self.service.code), service=self.service, url=url
        )

    @property
    def path(self):
        return "{ead_services_dir}/{code}/oaipmh/ead".format(
            ead_services_dir=self.config["ead-services-dir"], **self.service_infos
        )

    def setup_database(self):
        super(OaiEadImportTC, self).setup_database()
        with self.admin_access.cnx() as cnx:
            self.service = cnx.create_entity(
                "Service", name="Marne", code="FRAD051", category="foo"
            )
            cnx.commit()
            services_map = load_services_map(cnx)
            self.service_infos = service_infos_from_service_code(self.service.code, services_map)

    def test_service_infos(self):
        self.assertEqual(set(self.service_infos.keys()), {"code", "name", "eid", "level", "title"})

    def test_dump(self):
        """Test OAI EAD standard importing.

        Trying: valid OAI-PMH
        Expecting: corresponding XML files
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_ead_sample.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filepath())
            oai.import_oai(cnx, url, self.service_infos)
            rql = "Any E WHERE X is FindingAid, X eadid E"
            result_set = [result[0] for result in cnx.execute(rql)]
        for eadid in result_set:
            prefix = self.service_infos["code"] + "_"
            if eadid.startswith(prefix):
                filename = eadid + ".xml"
            else:
                filename = prefix + ".xml"
            file_path = os.path.join(self.path, filename)
            self.assertTrue(self.fileExists(file_path))

    def test_import_no_header(self):
        """Test OAI EAD standard importing.

        Trying: import 3 records one of which has no header tag
        Expecting: 2 FindingAids are created
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "no_header.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filepath())
            oai.import_oai(cnx, url, self.service_infos)
            self.assertEqual(2, cnx.find("FindingAid").rowcount)

    def test_import_no_metadata(self):
        """Test OAI EAD standard importing.

        Trying: import 3 records one of which has no metadata tag
        Expecting: 2 FindingAids are created
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "no_metadata.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filepath())
            oai.import_oai(cnx, url, self.service_infos)
            with open(self.filepath()) as fp:
                element_tree = etree.parse(fp)
            eadids = [eadid.text for eadid in element_tree.findall(".//{*}eadid")]
            rql = "Any E WHERE X is FindingAid, X eadid E"
            result_set = [result[0] for result in cnx.execute(rql)]
            self.assertCountEqual(eadids, result_set)
            self.assertEqual(2, len(result_set))

    def test_import_https(self):
        """Test OAI EAD standard importing.

        Trying: import a file with a OAI namespace starting with https.
        Expecting: 1 FindingAid is created
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_namespace_with_https.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filepath())
            oai.import_oai(cnx, url, self.service_infos)
            with open(self.filepath()) as fp:
                element_tree = etree.parse(fp)
            eadids = [eadid.text for eadid in element_tree.findall(".//{*}eadid")]
            rql = "Any E WHERE X is FindingAid, X eadid E"
            result_set = [result[0] for result in cnx.execute(rql)]
            self.assertCountEqual(eadids, result_set)
            self.assertEqual(1, len(result_set))

    def test_import_no_eadid(self):
        """Test OAI EAD standard importing.

        Trying: import 3 records one of which has no eadid tag
        Expecting: 2 FindingAids are created
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "no_eadid.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filepath())
            oai.import_oai(cnx, url, self.service_infos)
            with open(self.filepath()) as fp:
                element_tree = etree.parse(fp)
            eadids = [eadid.text for eadid in element_tree.findall(".//{*}eadid")]
            rql = "Any E WHERE X is FindingAid, X eadid E"
            result_set = [result[0] for result in cnx.execute(rql)]
            self.assertCountEqual(eadids, result_set)
            self.assertEqual(2, cnx.find("FindingAid").rowcount)

    def test_import_duplicate_c_id(self):
        """Test OAI EAD standard importing.

        Trying: import 2 records one of which has a duplicate c@id
        Expecting: 1 FindingAid is created
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "duplicate_c_id.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filepath())
            oai.import_oai(cnx, url, self.service_infos)
            with open(self.filepath()) as fp:
                element_tree = etree.parse(fp)
            self.assertEqual(2, len(element_tree.findall(".//{*}c[@id='the-id']")))
            fi = cnx.find("FindingAid").one()
            self.assertEqual("FRAD051_204M", fi.eadid)

    def test_import_no_archdesc(self):
        """Test OAI EAD standard importing.

        Trying: import 2 records one of which has no archdesc tag
        Expecting: 1 FindingAid is created
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "no_archdesc.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filepath())
            oai.import_oai(cnx, url, self.service_infos)
            with open(self.filepath()) as fp:
                element_tree = etree.parse(fp)
            self.assertEqual(1, len(element_tree.findall(".//{*}archdesc")))
            fi = cnx.find("FindingAid").one()
            self.assertEqual("FRAD051_204M", fi.eadid)

    def test_import_no_did(self):
        """Test OAI EAD standard importing.

        Trying: import 2 records one of which has no archdesc/did tag
        Expecting: 1 FindingAid is created
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "no_did.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filepath())
            oai.import_oai(cnx, url, self.service_infos)
            with open(self.filepath()) as fp:
                element_tree = etree.parse(fp)
            self.assertEqual(1, len(element_tree.findall(".//{*}archdesc/{*}did")))
            fi = cnx.find("FindingAid").one()
            self.assertEqual("FRAD051_204M", fi.eadid)

    def test_import_wrong_eadid(self):
        """Test OAI EAD standard importing.
            For now we accept records with not well formed eadid

        Trying: import 2 records one of which <eadid> value is not well formed
        Expecting: 2 FindingAids are nevertheless created
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "wrong_eadid.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filepath())
            oai.import_oai(cnx, url, self.service_infos)
            with open(self.filepath()) as fp:
                element_tree = etree.parse(fp)
            eadids = [eadid.text for eadid in element_tree.findall(".//{*}eadid")]
            rql = "Any E WHERE X is FindingAid, X eadid E"
            result_set = [result[0] for result in cnx.execute(rql)]
            self.assertCountEqual(eadids, result_set)
            self.assertEqual(2, cnx.find("FindingAid").rowcount)

    def test_empty_header(self):
        """Test OAI EAD standard importing.

        Trying: import 3 records one of which has an empty header tag
        Expecting: 2 FindingAids are created
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "empty_header.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filepath())
            oai.import_oai(cnx, url, self.service_infos)
            self.assertEqual(2, cnx.find("FindingAid").rowcount)

    def test_empty_metadata(self):
        """Test OAI EAD standard importing.

        Trying: import 3 records one of which has an empty metadata tag
        Expecting: 2 FindingAids are created
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "empty_metadata.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filepath())
            oai.import_oai(cnx, url, self.service_infos)
            self.assertEqual(2, cnx.find("FindingAid").rowcount)

    def test_empty_eadid(self):
        """Test OAI EAD standard importing.

        Trying:  import 3 records one of which has empty <eadid> tag
        Expecting:  2 FindingAids are created
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "empty_eadid.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filepath())
            oai.import_oai(cnx, url, self.service_infos)
            with open(self.filepath()) as fp:
                element_tree = etree.parse(fp)
            eadids = [eadid.text for eadid in element_tree.findall(".//{*}eadid") if eadid.text]
            rql = "Any E WHERE X is FindingAid, X eadid E"
            result_set = [result[0] for result in cnx.execute(rql)]
            self.assertCountEqual(eadids, result_set)

    def test_repeated_eadid(self):
        """Test OAI EAD standard importing.

        Trying: import 3 records two of which have the same <eadid> value
        Expecting: only one FindingAid is created for each unique <eadid> value
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "repeated_eadid.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filepath())
            oai.import_oai(cnx, url, self.service_infos)
            with open(self.filepath()) as fp:
                element_tree = etree.parse(fp)
            eadids = [eadid.text for eadid in element_tree.findall(".//{*}eadid")]
            self.assertCountEqual(
                ["FRAD051_000000028_203M", "FRAD051_204M", "FRAD051_000000028_203M"], eadids
            )
            # assert that for each EAD ID is only one entry in the database
            rql = "Any E WHERE X is FindingAid, X eadid E"
            self.assertCountEqual(list(set(eadids)), [result[0] for result in cnx.execute(rql)])

    def test_oai_ead_deleted(self):
        """Test OAI EAD reimport with a deleted record

        Trying: reimport a file with a deleted record
        Expecting: a FinadingAid is deleted
        """
        with self.admin_access.cnx() as cnx:
            cnx.commit()
            self.filename = "oai_ead_sample.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filename)
            service_infos = self.service_infos.copy()
            service_infos["oai_url"] = "http://portail.cg51.mnesys.fr/oai_pmh.cgi"
            oai.import_oai(cnx, url, service_infos)
            cnx.execute("Any X WHERE X eadid %(e)s", {"e": "FRAD051_000000028_203M"}).one()
            fi_count = cnx.execute("Any X WHERE X is FindingAid").rowcount
            # reimport a file with the sames record (one deleted)
            self.filename = "oai_ead_sample_deleted.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filename)
            oai.import_oai(cnx, url, service_infos)
            new_fi_count = cnx.execute("Any X WHERE X is FindingAid").rowcount
            self.assertEqual(new_fi_count, fi_count - 1)
            self.assertFalse(
                cnx.execute("Any X WHERE X eadid %(e)s", {"e": "FRAD051_000000028_203M"})
            )

    def test_deleted_record(self):
        """Test OAI EAD standard importing.

        Trying: import a recordList with one deleted record
        Expecting: nothing is created
        """
        with self.admin_access.cnx() as cnx:
            cnx.commit()
            self.filename = "deleted_record.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead&set=ead".format(self.filepath())
            oai.import_oai(cnx, url, self.service_infos)
            self.assertFalse(cnx.find("FindingAid"))

    def test_fa_audience_internal(self):
        """The content of tags with audience="internal" attribute is not imported

        Trying: import FRAD051_12Fi.xml

        Expecting: FAComponent with unitid='12 Fi 15' from <c audience="internal"> is not created

        """
        with self.admin_access.cnx() as cnx:
            self.filename = "FRAD051_12Fi.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filepath())
            oai.import_oai(cnx, url, self.service_infos)
            fc_rql = "Any X WHERE X is FAComponent, X did D, D unitid %(u)s"
            rset = cnx.execute(fc_rql, {"u": "12 Fi 15"})
            self.assertFalse(rset)
            # check we still have some FAComponent
            self.assertEqual(15, cnx.find("FAComponent").rowcount)

    def test_findingaid_support(self):
        """Test OAI EAD standard importing.

        Trying: OAI EAD standard import
        Expecting: findingaid_support attributes correspond to XML file paths
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_ead_sample.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filepath())
            oai.import_oai(cnx, url, self.service_infos)
            self.assertEqual(2, cnx.find("FindingAid").rowcount)
            if self.s3_bucket_name:
                expected_fpaths = [
                    b"tmp/FRAD051/oaipmh/ead/FRAD051_000000028_203M.xml",
                    b"tmp/FRAD051/oaipmh/ead/FRAD051_204M.xml",
                ]
            else:
                expected_fpaths = [
                    f.encode("utf-8") for f in glob.glob(os.path.join(self.path, "*.xml"))
                ]
            fpaths = [
                row[0].getvalue()
                for row in cnx.execute("Any FSPATH(D) WHERE X findingaid_support F, F data D")
            ]
            self.assertCountEqual(expected_fpaths, fpaths)
            for fpath in fpaths:
                self.assertTrue(self.fileExists(fpath))

    def test_findingaid_support_hash_import_oai(self):
        """
        Trying: OAI EAD standard import
        Expecting: findingaid_support data_hash is correctly set
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_ead_sample.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filepath())
            oai.import_oai(cnx, url, self.service_infos)
            fa_supports = list(cnx.execute("Any X WHERE F findingaid_support X").entities())
            self.assertEqual(2, len(fa_supports))
            for fa_support in fa_supports:
                self.assertEqual(fa_support.data_hash, fa_support.compute_hash())
                self.assertTrue(fa_support.check_hash())

    def test_reimport_findingaid_support(self):
        """Test EAD re-import based on XML files.

        Trying: re-import based on XML files created during OAI EAD import
        Expecting: the same data
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_ead_sample.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filepath())
            oai.import_oai(cnx, url, self.service_infos)
            rql = "Any E, FSPATH(D) WHERE X findingaid_support F, F data D, X eadid E"
            result_set = [(result[0], result[1].read()) for result in cnx.execute(rql)]
            filepaths = [result[1] for result in result_set]
            eadids = [result[0] for result in result_set]
            for filepath in filepaths:
                sqlutil.delete_from_filename(cnx, filepath, interactive=False, esonly=False)
            cnx.commit()
            assert not cnx.find("FindingAid"), "at least one FindingAid in database"
            assert not cnx.find("File"), "at least one CWFile in database"
            rql = "Any E WHERE X is FindingAid, X eadid E"
            for filepath in filepaths:
                self.assertTrue(self.fileExists(filepath))
                self.import_filepath(cnx, filepath.decode("utf-8"))
            actual = [row[0] for row in cnx.execute(rql)]
            self.assertEqual(actual, eadids)

    def test_FR_920509801_service_code(self):
        """Test EAD re-import based on XML files.

        Trying: import a stored OAI EAD file from `FR_920509801` service
        Expecting: the created FindingAid is related to right `FR_920509801` service
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity("Service", code="FR_920509801", category="foo")
            cnx.commit()
            self.filename = "FR_920509801_3000_3.xml"
            fpath = self.get_filepath_by_storage(os.path.join("oai_ead", self.filename))
            self.import_filepath(cnx, fpath)
            fa = cnx.find("FindingAid").one()
            self.assertEqual(fa.related_service, service)
            self.assertEqual(fa.reverse_entity[0].doc["publisher"], service.code)

    def test_eadid_legacy_compliance(self):
        """Test Findinding harvested files `name`attrubute (and thus `stable_id`)
        is computed as <eadid>.xml
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_ead_sample.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filepath())
            oai.import_oai(cnx, url, self.service_infos)
            rql = """Any E, FSPATH(D) WHERE X findingaid_support F,
                     F data D, X eadid E"""
            for fi in cnx.find("FindingAid").entities():
                self.assertEqual(fi.stable_id, usha1(fi.name))
            rset = cnx.execute(rql).rows
            fs_paths = [row[1].read() for row in rset]
            eadids = [row[0] for row in rset]
            # import the findingaid_support file
            for fs_path in fs_paths:
                sqlutil.delete_from_filename(cnx, fs_path, interactive=False, esonly=False)
            cnx.commit()
            for fs_path in fs_paths:
                self.import_filepath(cnx, fs_path.decode("utf-8"))
            actual = [row[0] for row in cnx.execute("Any E WHERE X is FindingAid, X eadid E")]
            self.assertEqual(actual, eadids)

    def test_name_stable_id_oai_ead(self):
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_ead_sample.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filepath())
            oai.import_oai(cnx, url, self.service_infos)
            fi1 = cnx.find("FindingAid", eadid="FRAD051_000000028_203M").one()
            self.assertEqual(fi1.name, "FRAD051_000000028_203M.xml")
            self.assertEqual(fi1.stable_id, usha1(fi1.name))
            fi2 = cnx.find("FindingAid", eadid="FRAD051_204M").one()
            self.assertEqual(fi2.name, "FRAD051_204M.xml")
            self.assertEqual(fi2.stable_id, usha1(fi2.name))

    def test_oai_ead_reimport(self):
        """Test OAI EAD re-import

        Trying: reimport the same file
        Expecting: no error is raised and no extra FindingAids created
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_ead_sample.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filepath())
            oai.import_oai(cnx, url, self.service_infos)
            expected_fi_count = cnx.execute("Any X WHERE X is FindingAid").rowcount
            self.assertEqual(expected_fi_count, 2)
            # reimport the same file
            oai.import_oai(cnx, url, self.service_infos)
            new_fi_count = cnx.execute("Any X WHERE X is FindingAid").rowcount
            self.assertEqual(expected_fi_count, new_fi_count)

    def test_creation_date_ead_import(self):
        """Test FindingAid, FAComponent creation date is keept between reimports

        Trying: import and reimport a FindingAid
        Expecting: reimported FindingAid and FAComponent have original creation_date
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_ead_sample.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filepath())
            oai.import_oai(cnx, url, self.service_infos)
            fa_stable_id = "060b7c36d487ba217d46f8fdfe3e7e40084f90d2"
            fa_old = cnx.execute("Any X WHERE X stable_id %(s)s", {"s": fa_stable_id}).one()
            comp_stable_id = "2696ef61cfafde6fab2e8ca4df9da094015fa444"
            comp_old = cnx.execute("Any X WHERE X stable_id %(s)s", {"s": comp_stable_id}).one()
            # FindingAid
            adapter = fa_old.cw_adapt_to("IFullTextIndexSerializable")
            self.assertEqual(
                format_date(adapter.serialize()["creation_date"]),
                format_date(fa_old.creation_date),
            )
            creation_date = datetime(1914, 4, 5)
            fmt = "%a %b %d %H:%M:%S %Y"
            fa_old.cw_set(creation_date=creation_date)
            comp_old.cw_set(creation_date=creation_date)
            cnx.commit()
            fa_old = cnx.execute("Any X WHERE X stable_id %(s)s", {"s": fa_stable_id}).one()
            fa_old_date = fa_old.creation_date
            comp_old_date = comp_old.creation_date
            self.assertEqual(
                creation_date.strftime(fmt),
                fa_old_date.strftime(fmt),
            )
            adapter = fa_old.cw_adapt_to("IFullTextIndexSerializable")
            self.assertEqual(
                format_date(adapter.serialize()["creation_date"]),
                format_date(fa_old.creation_date),
            )
            # reimport the same file
            oai.import_oai(cnx, url, self.service_infos)
            fa = cnx.execute("Any X WHERE X stable_id %(s)s", {"s": fa_stable_id}).one()
            self.assertNotEqual(fa_old.eid, fa.eid)
            adapter = fa.cw_adapt_to("IFullTextIndexSerializable")
            self.assertEqual(
                format_date(fa.creation_date),
                format_date(adapter.serialize()["creation_date"]),
            )
            self.assertEqual(fa_old_date, fa.creation_date)
            # FAComponent
            comp = cnx.execute("Any X WHERE X stable_id %(s)s", {"s": comp_stable_id}).one()
            adapter = comp.cw_adapt_to("IFullTextIndexSerializable")
            self.assertEqual(
                format_date(adapter.serialize()["creation_date"]),
                format_date(comp.creation_date),
            )
            self.assertEqual(comp.creation_date, comp_old_date)

    def test_import_extentities(self):
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_ead_sample.xml"
            path = "file://{path}?verb=ListRecords&metadataPrefix=ead".format(path=self.filepath())
            oai.import_oai(cnx, path, self.service_infos)
            fas = cnx.find("FindingAid")
            self.assertEqual(2, len(fas))
            fa = cnx.find("FindingAid", eadid="FRAD051_000000028_203M").one()
            self.assertEqual(4, len(fa.reverse_finding_aid))
            comp_rset = cnx.execute(
                "Any X WHERE X is FAComponent, X did D, D unittitle %(id)s",
                {"id": "Administration générale"},
            )
            self.assertEqual(1, len(comp_rset))
            comp = comp_rset.one()
            self.assertEqual(
                comp.digitized_versions[0].illustration_url,
                "http://portail.cg51.mnesys.fr/ark:/86869/a011401093704slpxLP/1/1.thumbnail",
            )  # noqa

    def test_import_new_findingaids_only(self):
        """Test OAI EAD delta import

        Trying: first import 2 records and reimport two slightly different records
                to simulate changes
        Expecting: one new FindingAid is created, one FindingAid is changed
                   and FindingAid remains unchanged
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_ead_sample.xml"
            repo = self.create_repo(
                cnx,
                url="file://{path}?verb=ListRecords&metadataPrefix=ead".format(
                    path=self.filepath()
                ),
            )
            cnx.commit()
            oai.import_delta(cnx, repo.eid)
            self.assertEqual(
                {fa.eadid for fa in cnx.find("FindingAid").entities()},
                {"FRAD051_000000028_203M", "FRAD051_204M"},
            )
            fa = cnx.find("FindingAid", eadid="FRAD051_204M").one()
            self.assertCountEqual(
                {"GUERRE 1939-1945", "Recherche détaillée", "Document d'archives"},
                {subject.label for subject in fa.subject_indexes().entities()},
            )
            self.assertIn("BAUDIN", fa.bibliography)
            self.assertEqual(
                fa.dc_title(), "204 M - Organisation économique pendant la guerre 1939-1945"
            )
            # now reimport a slightly different file to simulate changes
            # and check updates
            self.filename = "oai_ead_sample_updated.xml"
            repo.cw_set(
                url=repo.url.replace(
                    "oai_ead/oai_ead_sample.xml", "oai_ead/oai_ead_sample_updated.xml"
                )
            )
            oai.import_delta(cnx, repo.eid)
            # we should have :
            # FRAD051_000000028_203M untouched
            # FRAD051_204M updated (title changed, bibliography removed and
            #                       indexation changed)
            # FRAD051_205M created
            self.assertEqual(
                {fa.eadid for fa in cnx.find("FindingAid").entities()},
                {"FRAD051_000000028_203M", "FRAD051_204M", "FRAD051_205M"},
            )
            fa = cnx.find("FindingAid", eadid="FRAD051_204M").one()
            self.assertEqual(
                fa.dc_title(), "MAJ - 204 M - Organisation économique pendant la guerre 1939-1945"
            )
            self.assertEqual(fa.bibliography, None)
            self.assertCountEqual(
                {subject.label for subject in fa.subject_indexes().entities()},
                {
                    "GUERRE 1939-1945",
                    "La guerre de 39",
                    "Recherche détaillée",
                    "Document d'archives",
                },
            )

    def test_create_ape_ead_file(self):
        """test specific francearchive ape_ead transformations"""
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_ead_sample.xml"
            repo = self.create_repo(
                cnx,
                url="file://{path}?verb=ListRecords&metadataPrefix=ead".format(
                    path=self.filepath()
                ),
            )
            cnx.commit()
            oai.import_delta(cnx, repo.eid)
            fa = cnx.find("FindingAid", eadid="FRAD051_204M").one()
            ape_ead_filepath = fa.ape_ead_file[0]
            content = ape_ead_filepath.data.read()
            tree = etree.fromstring(content)
            eadid = tree.xpath("//e:eadid", namespaces={"e": tree.nsmap[None]})[0]
            self.assertEqual(
                eadid.attrib["url"], "https://francearchives.fr/{}".format(fa.rest_path())
            )
            extptrs = tree.xpath("//e:extptr", namespaces={"e": tree.nsmap[None]})
            self.assertEqual(len(extptrs), 5)
            for xlink in extptrs:
                self.assertTrue(
                    xlink.attrib["{{{e}}}href".format(e=tree.nsmap["xlink"])].startswith("http")
                )
                self.assertEqual(eadid.attrib["countrycode"], "FR")

    def test_unique_indexes(self):
        """Test that no duplicate authorities are created during oai_ead import"""
        with self.admin_access.cnx() as cnx:
            location_label = "Paris (Île-de-France, Paris)"
            cnx.create_entity("LocationAuthority", label=location_label)
            cnx.create_entity("AgentAuthority", label="Préfecture de la Marne")
            cnx.commit()
            self.filename = "oai_ead_sample.xml"
            repo = self.create_repo(
                cnx,
                url="file://{path}?verb=ListRecords&metadataPrefix=ead".format(
                    path=self.filepath()
                ),
            )
            with open(self.filepath()) as fp:
                element_tree = etree.parse(fp)
            geognames = [geogname.text for geogname in element_tree.findall(".//{*}geogname")]
            self.assertEqual([location_label], geognames)
            cnx.commit()
            oai.import_delta(cnx, repo.eid)
            fa = cnx.find("FindingAid", eadid="FRAD051_000000028_203M").one()
            self.assertCountEqual(
                [
                    "Préfecture de la Marne",
                    (
                        "Préfecture régionale de Châlons-sur-Marne, "
                        "devenue Commissariat de la République française "
                        "pour la Région de Châlons-sur-Marne."
                    ),
                ],
                [e.label for e in cnx.find("AgentAuthority").entities()],
            )
            self.assertEqual(
                "Paris (Île-de-France, Paris)", cnx.find("LocationAuthority").one().label
            )
            # we test a fa has only one Geogname linked to the LocationAuthority
            # Paris (Île-de-France, Paris)
            geogname = cnx.find("Geogname").one()
            self.assertEqual(location_label, geogname.label)
            self.assertEqual(fa.eid, geogname.index[0].eid)

    def create_findingaid(self, cnx, eadid, service):
        return cnx.create_entity(
            "FindingAid",
            name=eadid,
            stable_id="stable_id{}".format(eadid),
            eadid=eadid,
            publisher="publisher",
            did=cnx.create_entity(
                "Did", unitid="unitid{}".format(eadid), unittitle="title{}".format(eadid)
            ),
            fa_header=cnx.create_entity("FAHeader"),
            service=service,
        )

    def test_unique_grouped_indexes(self):
        """Test that no duplicate authorities are created
        during oai_ead import"""
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_ead_sample.xml"
            repo = self.create_repo(
                cnx,
                url="file://{path}?verb=ListRecords&metadataPrefix=ead".format(
                    path=self.filepath()
                ),
            )
            service = self.service
            location_label = "Paris (Île-de-France, Paris)"
            loc1 = cnx.create_entity("LocationAuthority", label=location_label)
            loc2 = cnx.create_entity("LocationAuthority", label=location_label)
            fa1 = self.create_findingaid(cnx, "eadid1", service)
            cnx.create_entity("Geogname", label="index location 1", index=fa1, authority=loc1)
            fa2 = self.create_findingaid(cnx, "eadid2", service)
            cnx.create_entity("Geogname", label="index location 2", index=fa2, authority=loc2)
            cnx.commit()
            loc1.group([loc2.eid])
            cnx.commit()
            self.assertEqual(2, cnx.find("LocationAuthority", label=location_label).rowcount)
            oai.import_delta(cnx, repo.eid)
            self.assertEqual(2, cnx.find("LocationAuthority", label=location_label).rowcount)
            fa = cnx.find("FindingAid", eadid="FRAD051_000000028_203M").one()
            locations = [ie.authority[0] for ie in fa.reverse_index if ie.cw_etype == "Geogname"]
            self.assertEqual(1, len(locations))
            self.assertEqual(loc1.eid, locations[0].eid)

    @patch("cubicweb_francearchives.dataimport.oai.import_oai")
    def test_from_parameter_first_import(self, import_oai):
        """check _from parameter is not set on first harvesting pass"""
        with self.admin_access.cnx() as cnx:
            url = "http://oai.frad051.fr/?verb=ListRecords&metadataPrefix=ape_ead"
            repo = self.create_repo(cnx, url=url)
            oai.import_delta(cnx, repo.eid)
            import_oai.assert_called_with(
                cnx,
                url,
                index_policy=None,
                records_limit=None,
                dry_run=False,
                log=logging.getLogger("rq.task"),
                service_infos=self.service_infos,
            )
            self.assertEqual(len(repo.tasks), 1, "we should have exactly one import task")
            twf = repo.tasks[0].cw_adapt_to("IWorkflowable")
            twf.entity.cw_clear_all_caches()
            self.assertEqual(twf.state, "wfs_oaiimport_completed")

    @patch("cubicweb_francearchives.dataimport.oai.import_oai")
    def test_from_parameter_last_succcessful_import(self, import_oai):
        """check _from parameter is inserted when re-harvesting"""
        with self.admin_access.cnx() as cnx:
            # the last successful import date is set in the frarchives-edition
            # oai import scripts
            repo = self.create_repo(
                cnx, url="http://oai.frad051.fr/?verb=ListRecords&metadataPrefix=ape_ead"
            )
            repo.cw_set(last_successful_import=datetime(2001, 2, 3))
            cnx.commit()
            oai.import_delta(cnx, repo.eid)
            import_oai.assert_called_with(
                cnx,
                "http://oai.frad051.fr/?verb=ListRecords&metadataPrefix=ape_ead&from=2001-02-03",
                index_policy=None,
                records_limit=None,
                dry_run=False,
                log=logging.getLogger("rq.task"),
                service_infos=self.service_infos,
            )

    def test_facomponents_es_document(self):
        """Test FAComponent EsDocument
        Trying: import FRAD051_12Fi.xml

        Expecting: ESDocument is well formed

        """
        with self.admin_access.cnx() as cnx:
            self.filename = "FRAD051_12Fi.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filepath())
            oai.import_oai(cnx, url, self.service_infos)
            fa = cnx.execute("Any X LIMIT 1 WHERE X is FAComponent").one()
            es_doc = fa.reverse_entity[0].doc
            for attr in ("_id", "_type", "_index"):
                self.assertNotIn(attr, es_doc)
            for attr in ("stable_id", "index_entries", "publisher", "escategory", "fa_stable_id"):
                self.assertIn(attr, es_doc)

    def test_es_dates_infos(self):
        """Test OAI harvest es data

        Trying: harvest some records
        Expecting: dates infos are found in FAComponent and FindingAid es indexes
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "FRAD051_12Fi.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filepath())
            oai.import_oai(cnx, url, self.service_infos)
            fa = cnx.execute("Any X WHERE X is FindingAid").one()
            adapted = fa.cw_adapt_to("IFullTextIndexSerializable")
            comp = cnx.execute("Any X LIMIT 1 WHERE X is FAComponent").one()
            comp_adapted = comp.cw_adapt_to("IFullTextIndexSerializable")
            for attr in ("sortdate", "stopyear", "startyear"):
                self.assertIn(attr, adapted.serialize())
                self.assertIn(attr, comp_adapted.serialize())

    def test_es_service_infos(self):
        """Test OAI harvest es data

        Trying: harvest some records
        Expecting: service infos are found in FAComponent and FindingAid es indexes
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "FRAD051_12Fi.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filepath())
            oai.import_oai(cnx, url, self.service_infos)
            fa = cnx.execute("Any X WHERE X is FindingAid").one()
            adapted = fa.cw_adapt_to("IFullTextIndexSerializable")
            expected = {
                "eid": self.service.eid,
                "level": "None",
                "code": "FRAD051",
                "title": "Marne",
            }
            self.assertEqual(expected, adapted.serialize()["service"])
            comp = cnx.execute("Any X LIMIT 1 WHERE X is FAComponent").one()
            adapted = comp.cw_adapt_to("IFullTextIndexSerializable")
            self.assertEqual(expected, adapted.serialize()["service"])


if __name__ == "__main__":
    unittest.main()
