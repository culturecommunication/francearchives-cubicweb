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
from datetime import datetime
from os import path as osp
import os
import glob

import unittest
from lxml import etree


from cubicweb.devtools.testlib import CubicWebTC

from cubicweb_francearchives.testutils import (
    S3BfssStorageTestMixin,
    PostgresTextMixin,
    OaiSickleMixin,
    format_date,
)

from cubicweb_francearchives.dataimport import (
    oai,
    oai_dc,
    oai_utils,
    usha1,
    sqlutil,
    load_services_map,
    service_infos_from_service_code,
)
from cubicweb_francearchives.dataimport.scripts.generate_ape_ead import (
    generate_ape_ead_other_sources_from_eids,
)
from cubicweb_francearchives.dataimport.importer import import_filepaths

from pgfixtures import setup_module, teardown_module  # noqa


class OaiDcImportTC(S3BfssStorageTestMixin, PostgresTextMixin, OaiSickleMixin, CubicWebTC):
    @classmethod
    def init_config(cls, config):
        """Initialize configuration."""
        super(OaiDcImportTC, cls).init_config(config)
        config.set_option("ead-services-dir", "/tmp")

    def setUp(self):
        super(OaiDcImportTC, self).setUp()
        self.oai_dc_dir = self.datapath("oai_dc")

    def tearDown(self):
        """Tear down test cases."""
        super(OaiDcImportTC, self).tearDown()
        directories = [
            self.path.format(ead_services_dir=self.config["ead-services-dir"], code=code)
            for code in ("FRAD034", "FRAD055")
        ]
        for directory in directories:
            if osp.exists(directory):
                for filename in glob.glob(osp.join(directory, "*")):
                    os.remove(filename)
                os.removedirs(directory)

    def filepath(self):
        assert self.filename is not None
        return self.datapath("{}/{}".format(self.oai_dc_dir, self.filename))

    @property
    def path(self):
        return "{ead_services_dir}/{code}/oaipmh/dc"

    def setup_database(self):
        super(OaiDcImportTC, self).setup_database()
        with self.admin_access.cnx() as cnx:
            self.service = cnx.create_entity(
                "Service", code="FRAD055", level="level-D", name="Service", category="test"
            )
            cnx.commit()
            services_map = load_services_map(cnx)
            self.service_infos = service_infos_from_service_code(self.service.code, services_map)

    def test_no_service_eid(self):
        """Test import OAI-PMH with a service without eid .

        Trying: importing records
        Expecting: import aborted
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_dc_sample.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=oai_dc".format(self.filepath())
            service_infos = {"code": "FRAD055", "eid": None}
            oai.import_oai(cnx, url, service_infos)
            self.assertEqual(cnx.find("FindingAid").rowcount, 0)

    def test_write(self):
        """Test writing OAI-PMH records to backup file.

        Trying: importing records
        Expecting: backup file
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_dc_sample.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=oai_dc".format(self.filepath())
            oai.import_oai(cnx, url, self.service_infos)
            path = self.path.format(
                ead_services_dir=self.config["ead-services-dir"], **self.service_infos
            )
            fpath = self.get_filepath_by_storage(osp.join(path, "FRAD055_REC.xml"))
            self.assertTrue(self.fileExists(fpath))

    def test_reimport_findingaid_support(self):
        """Test re-import of OAI-PMH records from backup file.

        Trying: re-import based on backup file created during import
        Expecting: the same data
        """
        url_str = "file://{}?verb=ListRecords&metadataPrefix=oai_dc"
        with self.admin_access.cnx() as cnx:
            # import
            self.filename = "oai_dc_sample.xml"
            url = url_str.format(self.filepath())
            oai.import_oai(cnx, url, self.service_infos)
            fi_rql = "Any X, E, FSPATH(D) WHERE X findingaid_support F, F data D," " X eadid E"
            fi_eid, fi_eadid, fs_path = [
                (eid, eadid, fpath.getvalue()) for eid, eadid, fpath in cnx.execute(fi_rql)
            ][0]
            # import the findingaid_support file
            url = url_str.format(fs_path.decode("utf-8"))
            oai.import_oai(cnx, url, self.service_infos)
            self.assertEqual(cnx.find("FindingAid").rowcount, 1)
            nfi_eid, nfi_eadid, nfs_path = [
                (eid, eadid, fpath.getvalue()) for eid, eadid, fpath in cnx.execute(fi_rql)
            ][0]
            self.assertNotEqual(fi_eid, nfi_eid)
            self.assertEqual(fi_eadid, nfi_eadid)
            self.assertEqual(fs_path, nfs_path)

    def test_eadid_legacy_compliance(self):
        """Test Findinding (and thus FAComponent) of harvested files are always based on
        <name> value which value is the same as the filename
        now stored on FindingAid.name
        """
        url_str = "file://{}?verb=ListRecords&metadataPrefix=oai_dc"
        with self.admin_access.cnx() as cnx:
            # import
            self.filename = "oai_dc_sample.xml"
            url = url_str.format(self.filepath())
            oai.import_oai(cnx, url, self.service_infos)
            fi = cnx.find("FindingAid").one()
            self.assertEqual("{}.xml".format(fi.eadid), fi.name)
            self.assertEqual(fi.stable_id, usha1(fi.name))
            fs_path = cnx.execute("Any FSPATH(D) WHERE X findingaid_support F, " "F data D")[0][
                0
            ].getvalue()
            # import the findingaid_support file
            url = url_str.format(fs_path.decode("utf-8"))
            oai.import_oai(cnx, url, self.service_infos)
            fi = cnx.find("FindingAid").one()
            self.assertEqual(fi.stable_id, usha1(fi.name))

    def test_name_stable_id_oai_dc(self):
        url_str = "file://{}?verb=ListRecords&metadataPrefix=oai_dc"
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_dc_sample.xml"
            url = url_str.format(self.filepath())
            oai.import_oai(cnx, url, self.service_infos)
            fi = cnx.find("FindingAid").one()
            self.assertEqual("FRAD055_REC.xml", fi.name)
            self.assertEqual("FRAD055_REC", fi.eadid)
            self.assertEqual(fi.stable_id, usha1(fi.name))

    def test_facomponent_stable_id(self):
        with self.admin_access.cnx() as cnx:
            cnx.commit()
            self.filename = "oai_dc_meuse_sample.xml"
            path = "file://{path}?verb=ListRecords&metadataPrefix=oai_dc".format(
                path=self.filepath()
            )
            with cnx.allow_all_hooks_but("es"):
                oai.import_oai(cnx, path, self.service_infos)
                fc_rql = "Any X WHERE X is FAComponent, X did D, D unittitle %(u)s"
                fac = cnx.execute(fc_rql, {"u": "Naissances  (1813-1832)"}).one()
                self.assertEqual("700cef882045b97dfacec5850aa58721fc394cd9", fac.stable_id)

    def test_findingaid_es_document(self):
        """Test findingaid has an EsDocument.

        Trying: importing records
        Expecting: FindingAid and FAComponent have related EsDocument
        """
        with self.admin_access.cnx() as cnx:
            cnx.commit()
            self.filename = "oai_dc_meuse_rec_sample.xml"
            path = "file://{path}?verb=ListRecords&metadataPrefix=oai_dc".format(
                path=self.filepath()
            )
            with cnx.allow_all_hooks_but("es"):
                oai.import_oai(cnx, path, self.service_infos)
                fi = cnx.execute("Any X WHERE X is FindingAid").one()
                es_doc = fi.reverse_entity[0]
                self.assertEqual(es_doc.doc["eadid"], "FRAD055_REC")
                for fa in cnx.execute("Any X WHERE X is FAComponent").entities():
                    es_doc = fa.reverse_entity[0]
                    self.assertEqual(es_doc.doc["stable_id"], fa.stable_id)

    def test_es_documents(self):
        """Test FAComponent and Findinaid EsDocuments are well formed.

        Trying: importing records
        Expecting:  ESDocument are well formed
        """
        with self.admin_access.cnx() as cnx:
            cnx.commit()
            self.filename = "oai_dc_meuse_rec_sample.xml"
            path = "file://{path}?verb=ListRecords&metadataPrefix=oai_dc".format(
                path=self.filepath()
            )
            with cnx.allow_all_hooks_but("es"):
                oai.import_oai(cnx, path, self.service_infos)
                fi = cnx.execute("Any X WHERE X is FindingAid").one()
                fi_es_doc = fi.reverse_entity[0].doc
                fa = cnx.execute("Any X LIMIT 1 WHERE X is FAComponent").one()
                fa_es_doc = fa.reverse_entity[0].doc
                for es_doc in (fi_es_doc, fa_es_doc):
                    for attr in ("_id", "_type", "_index"):
                        self.assertNotIn(attr, es_doc)
                        for attr in ("stable_id", "index_entries", "publisher", "escategory"):
                            self.assertIn(attr, es_doc)
                self.assertIn("fa_stable_id", fa_es_doc)

    def test_metadata(self):
        self.filename = "oai_dc_sample.xml"
        path = "file://{path}".format(path=osp.join(self.filepath()))
        client = oai_utils.PniaSickle(path)
        records = client.ListRecords(metadataPrefix="oai_dc")
        record = next(records)
        header = oai_dc.build_header(record.header)
        metadata = oai_dc.build_metadata(record.metadata)
        self.assertEqual(
            header,
            {"eadid": "FRAD055_REC", "identifier": "86869/a011349628476eWWr7u", "name": "FRAD055"},
        )
        self.assertEqual(
            metadata,
            {
                "contributor": ["Jean Valjean", "Victor Hugo"],
                "coverage": ["France"],
                "creator": ["Archives départementales de la Meuse"],
                "date1": "1865",
                "date2": "1981",
                "description": ["description"],
                "format": ["8.0"],
                "identifier": [
                    "https://recherche-archives.doubs.fr/ark:/25993/a011369750208WU2TRM"
                ],
                "language": ["eng"],
                "publisher": ["Archives départementales du Doubs"],
                "relation": ["vignette 1", "vignette 2"],
                "rights": [
                    "Les documents peuvent être reproduits sous réserve de leur bon état de conservation. La reproduction et la réutilisation des documents sont soumises aux dispositions du règlement général de réutilisation des informations publiques des Archives départementales du Doubs. "  # noqa
                ],
                "source": ["62J-105"],
                "subject": ["Architecture", "Livre"],
                "title": ["62J Ordre et syndicat des architectes"],
                "type": ["fonds", "fake type"],
            },
        )

    def test_import_meuse_extentities(self):
        with self.admin_access.cnx() as cnx:
            cnx.commit()
            self.filename = "oai_dc_meuse_sample.xml"
            path = "file://{path}?verb=ListRecords&metadataPrefix=oai_dc".format(
                path=self.filepath()
            )
            with cnx.allow_all_hooks_but("es"):
                oai.import_oai(cnx, path, self.service_infos)
                fa_rset = cnx.execute("Any X WHERE X is FindingAid")
                self.assertEqual(len(fa_rset), 1)
                es_fa_rset = cnx.execute("Any ES WHERE X is FindingAid, ES entity X")
                self.assertEqual(len(es_fa_rset), 1)
                fac_rset = cnx.execute("Any X WHERE X is FAComponent")
                self.assertEqual(len(fac_rset), 20)
                es_fac_rset = cnx.execute("Any ES WHERE X is FAComponent, ES entity X")
                self.assertEqual(len(es_fac_rset), 20)

    def test_import_extentities(self):
        with self.admin_access.cnx() as cnx:
            cnx.commit()
            self.filename = "oai_dc_sample.xml"
            path = "file://{path}?verb=ListRecords&metadataPrefix=oai_dc".format(
                path=self.filepath()
            )
            with cnx.allow_all_hooks_but("es"):
                oai.import_oai(cnx, path, self.service_infos)
                fa_rset = cnx.execute("Any X WHERE X is FindingAid")
                self.assertEqual(len(fa_rset), 1)
                fa = fa_rset.one()
                self.assertEqual(fa.eadid, "FRAD055_REC")
                self.assertEqual(fa.name, "FRAD055_REC.xml")
                self.assertEqual(fa.publisher, "Service")
                self.assertEqual(fa.service[0].eid, self.service.eid)
                self.assertEqual(fa.scopecontent, None)
                self.assertFalse(fa.fatype, None)
                self.assertEqual(fa.did[0].unitid, None)
                self.assertEqual(fa.did[0].unittitle, "FRAD055")
                self.assertEqual(fa.did[0].startyear, None)
                self.assertEqual(fa.did[0].stopyear, None)
                self.assertEqual(fa.did[0].unitdate, None)
                self.assertEqual(fa.did[0].origination, None)
                self.assertEqual(fa.did[0].lang_code, None)
                self.assertEqual(fa.fa_header[0].titleproper, "FRAD055")
                facs_rset = cnx.execute("Any F WHERE F is FAComponent")
                facs = list(facs_rset.entities())
                facs.sort(key=lambda fac: fac.did[0].unitid)
                fac1, fac2 = facs
                fac1_did = fac1.did[0]
                self.assertEqual(fac1_did.unittitle, "62J Ordre et syndicat des architectes")
                self.assertEqual(fac1_did.unitid, "62J-105")
                self.assertEqual(fac1_did.origination, "Archives départementales de la Meuse")
                self.assertEqual(fac1_did.unitdate, "1865 - 1981")
                self.assertEqual(fac1_did.startyear, 1865)
                self.assertEqual(fac1_did.stopyear, 1981)
                self.assertEqual(fac1.did[0].lang_code, "eng")
                self.assertEqual(fac1.did[0].lang_description, None)
                self.assertIn('<div class="ead-p">8.0</div>', fac1_did.physdesc)
                self.assertIn('<div class="ead-p">description</div>', fac1.scopecontent)
                self.assertIn('<div class="ead-p">Les documents peuvent', fac1.userestrict)
                self.assertEqual(len(fac1.digitized_versions), 3)
                self.assertCountEqual(
                    [dao.url for dao in fac1.digitized_versions if dao.url],
                    ["https://recherche-archives.doubs.fr/ark:/25993/a011369750208WU2TRM"],
                )
                self.assertCountEqual(
                    [
                        dao.illustration_url
                        for dao in fac1.digitized_versions
                        if dao.illustration_url
                    ],
                    ["vignette 1", "vignette 2"],
                )
                index_entries = [
                    (ie.authority[0].cw_etype, ie.authority[0].label) for ie in fac1.reverse_index
                ]
                self.assertCountEqual(
                    index_entries,
                    [
                        ("SubjectAuthority", "Architecture"),
                        ("SubjectAuthority", "Livre"),
                        ("AgentAuthority", "Jean Valjean"),
                        ("AgentAuthority", "Victor Hugo"),
                        ("LocationAuthority", "France"),
                    ],
                )
                fac2_did = fac2.did[0]
                self.assertEqual(fac2_did.unittitle, "62J1 Ordre et syndicat des architectes")
                self.assertEqual(fac2_did.unitid, "62J1-205")
                self.assertEqual(fac2_did.origination, "Archives départementales de la Meuse")
                self.assertEqual(fac2_did.unitdate, "1865")
                self.assertEqual(fac2_did.startyear, 1865)
                self.assertEqual(fac2_did.stopyear, None)
                self.assertEqual(fac2.did[0].lang_code, None)
                self.assertIn('<div class="ead-p">eng ; fra</div>', fac2.did[0].lang_description)
                self.assertIn('<div class="ead-p">12.19 ; text/html</div>', fac2_did.physdesc)
                self.assertIn('<div class="ead-p">description</div>', fac2.scopecontent)
                self.assertIn('<div class="ead-p">Les documents peuvent', fac2.userestrict)
                self.assertEqual(len(fac2.digitized_versions), 1)
                self.assertCountEqual(
                    [dao.url for dao in fac2.digitized_versions if dao.url],
                    ["https://recherche-archives.doubs.fr/ark:/25993/a011369750208WU2TRT"],
                )
                index_entries = [
                    (ie.authority[0].cw_etype, ie.authority[0].label) for ie in fac2.reverse_index
                ]
                self.assertCountEqual(
                    index_entries,
                    [
                        ("SubjectAuthority", "France"),
                        ("AgentAuthority", "Jean Marais"),
                        ("LocationAuthority", "Paris"),
                    ],
                )
                # ape_ead_file must be created
                ape_ead_file = fa.ape_ead_file[0]
                content = ape_ead_file.data.read()
                tree = etree.fromstring(content)
                eadid = tree.xpath("//e:eadid", namespaces={"e": tree.nsmap[None]})[0]
                self.assertEqual(
                    eadid.attrib["url"], "https://francearchives.fr/{}".format(fa.rest_path())
                )

    def test_unique_indexes(self):
        """Test that no duplicate authorities are created during oai_dc import"""
        with self.admin_access.cnx() as cnx:
            cnx.create_entity("LocationAuthority", label="Paris")
            cnx.create_entity("AgentAuthority", label="Jean Valjean")
            cnx.create_entity("SubjectAuthority", label="Architecture")
            cnx.create_entity("SubjectAuthority", label="Livre")
            cnx.commit()
            cnx.commit()
            self.filename = "oai_dc_sample.xml"
            path = "file://{path}?verb=ListRecords&metadataPrefix=oai_dc".format(
                path=self.filepath()
            )
            with cnx.allow_all_hooks_but("es"):
                oai.import_oai(cnx, path, self.service_infos)
                self.assertEqual(
                    ["Architecture", "France", "Livre"],
                    sorted([e.label for e in cnx.find("SubjectAuthority").entities()]),
                )
                self.assertEqual(
                    ["Jean Marais", "Jean Valjean", "Victor Hugo"],
                    sorted([e.label for e in cnx.find("AgentAuthority").entities()]),
                )
                self.assertEqual(
                    ["France", "Paris"],
                    sorted([e.label for e in cnx.find("LocationAuthority").entities()]),
                )

    def test_generate_ape_ead_utils(self):
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity("Service", code="FRAD034", name="Service", category="test")
            fadid = cnx.create_entity("Did", unitid="maindid", unittitle="maindid-title")
            fa = cnx.create_entity(
                "FindingAid",
                name="the-fa",
                stable_id="FRAD051_xxx",
                eadid="FRAD051_xxx",
                publisher="FRAD051",
                service=service,
                did=fadid,
                fa_header=cnx.create_entity("FAHeader"),
            )
            cnx.commit()
            generate_ape_ead_other_sources_from_eids(cnx, [str(fa.eid)])
            fa = cnx.entity_from_eid(fa.eid)
            ape_filepath = cnx.execute(
                "Any FSPATH(D) WHERE X ape_ead_file F, F data D, X eid %(x)s", {"x": fa.eid}
            )[0][0].getvalue()
            self.assertTrue(self.fileExists(ape_filepath))
            content = fa.ape_ead_file[0].data.read()
            tree = etree.fromstring(content)
            eadid = tree.xpath("//e:eadid", namespaces={"e": tree.nsmap[None]})[0]
            self.assertEqual(
                eadid.attrib["url"], "https://francearchives.fr/{}".format(fa.rest_path())
            )

    def test_oai_dc_reimport(self):
        """Test OAI DC re-import
        Trying: reimport the same file
        Expecting: no error is raised and no extra FindingAids created
        """
        with self.admin_access.cnx() as cnx:
            cnx.commit()
            self.filename = "oai_dc_meuse_sample.xml"
            path = "file://{path}?verb=ListRecords&metadataPrefix=oai_dc".format(
                path=self.filepath()
            )
            oai.import_oai(cnx, path, self.service_infos)
            fi = cnx.execute("Any X WHERE X is FindingAid").one()
            # reimport the same file
            oai.import_oai(cnx, path, self.service_infos)
            new_fi = cnx.execute("Any X WHERE X is FindingAid").one()
            self.assertNotEqual(fi.eid, new_fi.eid)
            self.assertEqual(new_fi.stable_id, new_fi.stable_id)
            fac_rset = cnx.execute("Any X WHERE X is FAComponent")
            self.assertEqual(len(fac_rset), 20)
            self.assertEqual(len(set(f.dc_title() for f in fac_rset.entities())), 18)

    def test_findingaid_support_hash_import_oai_dc(self):
        """
        Trying: OAI DC standard import
        Expecting: findingaid_support data_hash is correctly set
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_dc_sample.xml"
            url = "file://{path}?verb=ListRecords&metadataPrefix=oai_dc".format(
                path=self.filepath()
            )
            oai.import_oai(cnx, url, self.service_infos)
            fa_support = cnx.execute("Any X WHERE F findingaid_support X").one()
            self.assertTrue(fa_support.data_hash)
            self.assertEqual(fa_support.data_hash, fa_support.compute_hash())
            self.assertTrue(fa_support.check_hash())

    def test_oai_dc_reimport_from_file(self):
        """Test OAI DC re-import from file.

        Trying: re-importing from file after deleting harvested FindingAid
        Expecting: same FindingAid is re-created
        """
        readerconfig = {
            "esonly": False,
            "index-name": "dummy",
            "appid": "data",
            "nodrop": False,
            "noes": True,
        }
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_dc_sample.xml"
            url = "file://{path}?verb=ListRecords&metadataPrefix=oai_dc".format(
                path=self.filepath()
            )
            oai.import_oai(cnx, url, self.service_infos)
            rql = "Any E,FSPATH(D) WHERE X findingaid_support F, F data D, X eadid E"
            rset = [(row[0], row[1].read()) for row in cnx.execute(rql)]
            filepaths = [row[1] for row in rset]
            self.assertEqual(len(filepaths), 1)
            eadids = [row[0] for row in rset]
            for filename in [row[1] for row in rset]:
                sqlutil.delete_from_filename(cnx, filename, interactive=False, esonly=False)
            cnx.commit()
            assert not cnx.find("FindingAid"), "at least one FindingAid in database"
            assert not cnx.find("File"), "at least one CWFile in database"
            self.assertFalse(cnx.execute(rql).rows)
            for filepath in filepaths:
                self.assertTrue(self.fileExists(filepath))
            import_filepaths(cnx, filepaths, readerconfig)
            actual = [row[0] for row in cnx.execute("Any E WHERE X is FindingAid, X eadid E")]
            self.assertCountEqual(actual, eadids)

    def test_creation_date_dc_import(self):
        """Test FindingAid, FAComponent creation date is keept between reimports

        Trying: import and reimport a FindingAid
        Expecting: reimported FindingAid and FAComponent have original creation_date
        """
        with self.admin_access.cnx() as cnx:
            cnx.commit()
            self.filename = "oai_dc_meuse_sample.xml"
            path = "file://{path}?verb=ListRecords&metadataPrefix=oai_dc".format(
                path=self.filepath()
            )
            oai.import_oai(cnx, path, self.service_infos)
            fa_old = cnx.execute("Any X WHERE X is FindingAid").one()
            comp_stable_id = "1375ca056f49fec4548296908363d30ac653f2d1"
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
            fa_old = cnx.execute("Any X WHERE X is FindingAid").one()
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
            oai.import_oai(cnx, path, self.service_infos)
            fa = cnx.execute("Any X WHERE X is FindingAid").one()
            self.assertNotEqual(fa_old.eid, fa.eid)
            adapter = fa.cw_adapt_to("IFullTextIndexSerializable")
            self.assertEqual(
                format_date(adapter.serialize()["creation_date"]),
                format_date(fa.creation_date),
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

    def test_multiple_setSpec(self):
        """Test the case where several FindingAid are created from the same harvesting
        Trying: import a oai_dc file with 2 different <setSpec>
        Expecting: 2 FindingAid are created with one and two FAComponents
        """
        with self.admin_access.cnx() as cnx:
            cnx.commit()
            self.filename = "oai_dc_multiple_set.xml"
            path = "file://{path}?verb=ListRecords&metadataPrefix=oai_dc".format(
                path=self.filepath()
            )
            oai.import_oai(cnx, path, self.service_infos)
            self.assertEqual(len(cnx.execute("Any X WHERE X is FindingAid")), 2)
            self.assertEqual(len(cnx.execute("Any X WHERE X is FAComponent")), 3)
            fi_ec = cnx.execute('Any X WHERE X is FindingAid, X eadid "FRAD055_EC"').one()
            self.assertEqual(len(fi_ec.reverse_finding_aid), 2)
            fi_rec = cnx.execute('Any X WHERE X is FindingAid, X eadid "FRAD055_REC"').one()
            self.assertEqual(len(fi_rec.reverse_finding_aid), 1)

    def test_multiple_findingaind_support(self):
        """Test each FindingAid created from the same harvesting has
        a separate findingaid_support file
        Trying: import a oai_dc file with 2 different <setSpec>
        Expecting: both FindingAid have different findingaid_support files
        """
        with self.admin_access.cnx() as cnx:
            cnx.commit()
            self.filename = "oai_dc_multiple_set.xml"
            path = "file://{path}?verb=ListRecords&metadataPrefix=oai_dc".format(
                path=self.filepath()
            )
            oai.import_oai(cnx, path, self.service_infos)
            rset = cnx.execute(
                "DISTINCT Any E, FSPATH(D) WHERE X findingaid_support F, F data D," " X eadid E"
            )
            self.assertEqual(rset.rowcount, 2)
            for eid, fpath in rset:
                fpath = fpath.getvalue()
                expected = "{}/FRAD055/oaipmh/dc/{}.xml".format(
                    self.config["ead-services-dir"], eid
                )
                if self.s3_bucket_name:
                    expected = expected.lstrip("/")
                self.assertEqual(expected.encode("utf-8"), fpath)
                self.assertTrue(self.fileExists(fpath))

    def test_ape_ead_path(self):
        with self.admin_access.cnx() as cnx:
            cnx.commit()
            self.filename = "oai_dc_sample.xml"
            path = "file://{path}?verb=ListRecords&metadataPrefix=oai_dc".format(
                path=self.filepath()
            )
            oai.import_oai(cnx, path, self.service_infos)
            fa = cnx.find("FindingAid").one()
            self.assertEqual(fa.related_service.code, "FRAD055")
            self.assertEqual(fa.eadid, "FRAD055_REC")
            ape_filepath = cnx.execute(
                "Any FSPATH(D) WHERE X ape_ead_file F, F data D, X eid %(x)s", {"x": fa.eid}
            )[0][0].getvalue()
            expected_filepath = self.get_filepath_by_storage(
                f"{self.config['appfiles-dir']}/ape-ead/FRAD055/ape-FRAD055_REC.xml"
            )
            self.assertEqual(ape_filepath.decode("utf-8"), expected_filepath)

    def test_oai_dc_deleted(self):
        """Test OAI DC reimport with a deleted record

        Trying: reimport a file with a deleted record
        Expecting: a FinadingAid is deleted
        """
        with self.admin_access.cnx() as cnx:
            cnx.commit()
            self.filename = "oai_dc_sample.xml"
            path = "file://{path}?verb=ListRecords&metadataPrefix=oai_dc".format(
                path=self.filepath()
            )
            service_infos = self.service_infos.copy()
            service_infos["oai_url"] = "http://portail.cg51.mnesys.fr/oai_pmh.cgi"
            oai.import_oai(cnx, path, service_infos)
            fi_count = cnx.execute("Any X WHERE X is FindingAid").rowcount
            # reimport a file with the sames record (one deleted)
            self.filename = "oai_dc_sample_deleted.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filename)
            oai.import_oai(cnx, url, service_infos)
            new_fi_count = cnx.execute("Any X WHERE X is FindingAid").rowcount
            self.assertEqual(new_fi_count, fi_count - 1)
            self.assertFalse(
                cnx.execute("Any X WHERE X eadid %(e)s", {"e": "FRAD051_000000028_203M"})
            )

    def test_es_dates_infos(self):
        """Test OAI harvest es data

        Trying: harvest some records
        Expecting: dates infos are found in FAComponent and FindingAid es indexes
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_dc_sample.xml"
            path = "file://{path}?verb=ListRecords&metadataPrefix=oai_dc".format(
                path=self.filepath()
            )
            oai.import_oai(cnx, path, self.service_infos)
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
            self.filename = "oai_dc_sample.xml"
            path = "file://{path}?verb=ListRecords&metadataPrefix=oai_dc".format(
                path=self.filepath()
            )
            oai.import_oai(cnx, path, self.service_infos)
            fa = cnx.execute("Any X WHERE X is FindingAid").one()
            adapted = fa.cw_adapt_to("IFullTextIndexSerializable")
            expected = {
                "eid": self.service.eid,
                "level": "level-D",
                "code": "FRAD055",
                "title": "Service",
            }
            self.assertEqual(expected, adapted.serialize()["service"])
            comp = cnx.execute("Any X LIMIT 1 WHERE X is FAComponent").one()
            adapted = comp.cw_adapt_to("IFullTextIndexSerializable")
            self.assertEqual(expected, adapted.serialize()["service"])


if __name__ == "__main__":
    unittest.main()
