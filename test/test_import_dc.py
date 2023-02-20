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
import unittest
from lxml import etree

import os
from os import path as osp

from cubicweb.devtools import testlib

from cubicweb.dataimport.stores import RQLObjectStore

from cubicweb_francearchives.testutils import PostgresTextMixin, format_date, S3BfssStorageTestMixin
from cubicweb_francearchives.utils import pick
from cubicweb_francearchives.dataimport import dc, usha1, CSVIntegrityError, load_services_map

from pgfixtures import setup_module, teardown_module  # noqa


class CSVImportMixIn(S3BfssStorageTestMixin):
    def setUp(self):
        super(CSVImportMixIn, self).setUp()
        import_dir = self.datapath("tmp")
        self.config.set_option("appfiles-dir", import_dir)
        if not osp.isdir(import_dir):
            os.mkdir(import_dir)

    def csv_filepath(self, filepath):
        return self.get_or_create_imported_filepath(f"csv/{filepath}")

    def _test_medatadata_csv(self, cnx, service=None, fa=None):
        if not service:
            service = self.service
        if fa is None:
            fa = cnx.execute("Any FA WHERE FA is FindingAid").one()
            fac_count = cnx.execute("Any COUNT(FA) WHERE FA is FAComponent")[0][0]
            self.assertEqual(10, fac_count)
        self.assertEqual(fa.name, "FRAD092_9FI_cartes-postales.csv")
        self.assertEqual(fa.eadid, "FRAD092_9FI_cartes-postales")
        self.assertEqual(fa.fatype, None)
        self.assertEqual(fa.did[0].unitid, None)
        self.assertEqual(fa.did[0].unittitle, "Cartes postales anciennes")
        self.assertEqual(fa.did[0].unitdate, "1900 - 1944-05-31")
        self.assertEqual(fa.did[0].startyear, 1900)
        self.assertEqual(fa.did[0].stopyear, 1944)
        self.assertEqual(fa.did[0].origination, "Archives des Hauts-de-Seine")
        self.assertEqual(fa.did[0].lang_description, "italien")
        self.assertEqual(
            fa.did[0].extptr, "https://opendata.hauts-de-seine.fr/explore/dataset/cartes-postales/"
        )
        self.assertEqual(fa.fa_header[0].titleproper, "Cartes postales anciennes")
        self.assertIn('<div class="ead-p">5 cartons</div>', fa.did[0].physdesc)
        self.assertIn(
            '<div class="ead-p">Cartes postales anciennes (1900-1944)</div>', fa.scopecontent
        )
        self.assertIn(
            '<div class="ead-p">Collection photographie département Essonne.</div>',
            fa.additional_resources,
        )
        self.assertIn('<div class="ead-p">Libre accès</div>', fa.accessrestrict)
        self.assertIn('<div class="ead-p">Libre de droit</div>', fa.userestrict)
        self.assertEqual(fa.publisher, "AD 92")
        self.assertEqual(fa.service[0].eid, service.eid)
        self.assertEqual(fa.findingaid_support[0].data_name, "FRAD092_9FI_cartes-postales.csv")
        self.assertEqual(fa.findingaid_support[0].data_format, "text/csv")
        index_entries = sorted(
            [(ie.authority[0].cw_etype, ie.authority[0].label) for ie in fa.reverse_index]
        )
        self.assertCountEqual(
            index_entries,
            [
                ("AgentAuthority", "Alphonse Germain"),
                ("AgentAuthority", "Jules Ferry"),
                ("AgentAuthority", "Service des postes"),
                ("LocationAuthority", "Antony (Hauts-de-Seine)"),
                ("LocationAuthority", "Corse (France ; département)"),
                (
                    "LocationAuthority",
                    "Digne-les-Bains (Alpes-de-Haute-Provence, France ; arrondissement )",
                ),
                ("LocationAuthority", "Digne-les-Bains (Alpes-de-Haute-Provence, France)"),
                ("LocationAuthority", "Hauts-de-Seine"),
                ("LocationAuthority", "Paris"),
                (
                    "LocationAuthority",
                    "Sisteron (Alpes-de-Haute-Provence, France ; arrondissement)",
                ),
                ("LocationAuthority", "méditerranée (mer)"),
                ("SubjectAuthority", "Cartes postales"),
                ("SubjectAuthority", "photographie"),
                ("SubjectAuthority", "urbanisation"),
            ],
        )
        facs_rset = cnx.execute("Any FA WHERE FA finding_aid F, F eid %(e)s", {"e": fa.eid})
        self.assertEqual(facs_rset.rowcount, 10)
        facs = sorted(facs_rset.entities(), key=lambda fac: fac.did[0].unitid)
        fac1 = facs[0]
        self.assertIn('<div class="ead-p">Est développée la notion', fac1.scopecontent)
        self.assertIn('<div class="ead-p">Collection photographie, BNF', fac1.additional_resources)
        self.assertIn('<div class="ead-p">Libre accès</div>', fac1.accessrestrict)
        self.assertIn('<div class="ead-p">Libre de droit</div>', fac1.userestrict)
        self.assertEqual(fac1.did[0].unitid, "9FI/BAG_10")
        self.assertEqual(fac1.did[0].unittitle, "Le Dépot des Tramways")
        self.assertEqual(fac1.did[0].unitdate, "1900")
        self.assertEqual(fac1.did[0].startyear, 1900)
        self.assertEqual(fac1.did[0].stopyear, 1900)
        self.assertEqual(fac1.did[0].origination, "Archives privées Mr X")
        self.assertEqual(fac1.did[0].lang_description, None)
        self.assertIn('<div class="ead-p">12x19 cm</div>', fac1.did[0].physdesc)
        self.assertEqual(len(fac1.digitized_versions), 1)
        self.assertEqual(
            fac1.digitized_versions[0].url,
            "https://opendata.hauts-de-seine.fr/explore/dataset/cartes-postales/table/?sort=id",
        )
        self.assertEqual(
            fac1.digitized_versions[0].illustration_url,
            "https://opendata.hauts-de-seine.fr/api/datasets/1.0/cartes-postales/images/8ee3d34b124926666f78afa361566542",  # noqa
        )
        index_entries = [
            (ie.authority[0].cw_etype, ie.authority[0].label) for ie in fac1.reverse_index
        ]
        self.assertCountEqual(
            index_entries,
            [
                ("SubjectAuthority", "Bâtiment public > Gare"),
                ("AgentAuthority", "Charles Baudelaire"),
                ("LocationAuthority", "Bagneux"),
                ("SubjectAuthority", "photographie"),
            ],
        )
        fac5 = facs[5]
        self.assertIn('<div class="ead-p">Duis aute irure dolor in', fac5.scopecontent)
        self.assertEqual(fac5.additional_resources, None)
        self.assertIn('<div class="ead-p">Libre accès</div>', fac5.accessrestrict)
        self.assertIn('<div class="ead-p">Libre de droit</div>', fac5.userestrict)
        self.assertEqual(fac5.did[0].unitid, "9FI/BAG_21")
        self.assertEqual(fac5.did[0].unittitle, "La Sous-Station Electrique")
        self.assertEqual(fac5.did[0].unitdate, "1900")
        self.assertEqual(fac5.did[0].startyear, 1900)
        self.assertEqual(fac5.did[0].stopyear, 1900)
        self.assertEqual(fac5.did[0].origination, "Entreprise Pajol")
        self.assertEqual(fac5.did[0].lang_description, None)
        self.assertIn('<div class="ead-p">17x19 cm</div>', fac5.did[0].physdesc)
        self.assertEqual(len(fac5.digitized_versions), 1)
        self.assertEqual(
            fac5.digitized_versions[0].url,
            "https://opendata.hauts-de-seine.fr/explore/dataset/cartes-postales/table/?sort=id",
        )  # noqa

        self.assertEqual(fac5.digitized_versions[0].illustration_url, None)
        index_entries = [
            (ie.authority[0].cw_etype, ie.authority[0].label) for ie in fac5.reverse_index
        ]
        self.assertCountEqual(
            index_entries,
            [
                ("SubjectAuthority", "Bâtiment public"),
                ("AgentAuthority", "Emma Bovary"),
                ("AgentAuthority", "Claudette Levy"),
                ("AgentAuthority", "Société Beguin-Say"),
                ("LocationAuthority", "Bagneux"),
                ("SubjectAuthority", "photographie"),
            ],
        )


class CSVDCImportTC(CSVImportMixIn, PostgresTextMixin, testlib.CubicWebTC):
    readerconfig = {
        "noes": True,
        "esonly": False,
        "appid": "data",
        "nodrop": False,
        "dc_no_cache": True,
        "index-name": "dummy",
    }

    def setUp(self):
        super(CSVDCImportTC, self).setUp()
        with self.admin_access.cnx() as cnx:
            self.service = cnx.create_entity(
                "Service", code="FRAD092", short_name="AD 92", level="level-D", category="foo"
            )
            cnx.commit()

    def test_import_findingaid_esonly(self):
        with self.admin_access.cnx() as cnx:
            fpath = self.csv_filepath("frmaee_findingaid.csv")
            config = self.readerconfig.copy()
            config["esonly"] = True
            store = RQLObjectStore(cnx)
            importer = dc.CSVReader(config, store)
            services_map = load_services_map(cnx)
            es_docs = [e["_source"] for e in importer.import_filepath(services_map, fpath)]
            self.assertEqual(len(es_docs), 4)
            fa_docs = [
                e for e in es_docs if e["stable_id"] == "d8e6d65766871576a026b2a75b3fc2fa349d6040"
            ]
            service = fa_docs[0].pop("service")
            self.assertEqual(set(service.keys()), {"code", "eid", "level", "title"})
            self.assertEqual(
                set(fa_docs[0].keys()),
                {
                    "escategory",
                    "publisher",
                    "name",
                    "cw_etype",
                    "did",
                    "year",
                    "eid",
                    "stable_id",
                    "fa_stable_id",
                    "fatype",
                    "index_entries",
                    "scopecontent",
                    "eadid",
                    "creation_date",
                    "sortdate",
                    "startyear",
                    "stopyear",
                },
            )

    def test_import_one_facomponent_esonly(self):
        with self.admin_access.cnx() as cnx:
            fpath = self.csv_filepath("frmaee_findingaid.csv")
            config = self.readerconfig.copy()
            config["esonly"] = True
            store = RQLObjectStore(cnx)
            importer = dc.CSVReader(config, store)
            services_map = load_services_map(cnx)
            es_docs = [e["_source"] for e in importer.import_filepath(services_map, fpath)]
            es_docs = [e for e in es_docs if e["cw_etype"] == "FAComponent"]
            self.assertEqual(len(es_docs), 3)
            es_doc = [e for e in es_docs if e["did"]["unitid"] == "TRA13680001"][0]
            self.assertEqual(
                set(es_doc.keys()),
                {
                    "escategory",
                    "publisher",
                    "name",
                    "eid",
                    "cw_etype",
                    "did",
                    "year",
                    "stable_id",
                    "fa_stable_id",
                    "index_entries",
                    "eadid",
                    "scopecontent",
                    "digitized",
                    "creation_date",
                    "sortdate",
                    "startyear",
                    "stopyear",
                    "dates",
                    "service",
                },
            )
            es_index_entries = es_doc["index_entries"]
            self.assertTrue(all("type" in i and "label" in i for i in es_index_entries))
            self.assertEqual(len(es_index_entries), 5)
            es_doc = pick(es_doc, *(set(es_doc) - {"extid", "stable_id"}))
            # ensure `index_entries` list is alway in same order
            es_doc["index_entries"] = sorted(es_doc["index_entries"], key=lambda k: k["normalized"])
            self.assertTrue(es_doc.pop("creation_date"))
            self.assertCountEqual(
                es_doc,
                {
                    "cw_etype": "FAComponent",
                    "dates": {"gte": 1500, "lte": 1500},
                    "did": {
                        "unitid": "TRA13680001",
                        "unittitle": "Recueil de traités (1368-1408)",
                        "eid": None,
                    },
                    "digitized": True,
                    "eadid": None,
                    "eid": None,
                    "escategory": "archives",
                    "fa_stable_id": "d8e6d65766871576a026b2a75b3fc2fa349d6040",
                    "index_entries": [
                        {
                            "label": "Clermont-Ferrand",
                            "normalized": "clermont ferrand",
                            "type": "geogname",
                            "role": "index",
                            "authority": None,
                            "authfilenumber": None,
                        },
                        {
                            "label": "corporname",
                            "normalized": "corporname",
                            "type": "corpname",
                            "role": "index",
                            "authority": None,
                            "authfilenumber": None,
                        },
                        {
                            "label": "Henri VII",
                            "normalized": "henri vii",
                            "type": "persname",
                            "role": "index",
                            "authority": None,
                            "authfilenumber": None,
                        },
                        {
                            "label": "subject",
                            "normalized": "subject",
                            "type": "subject",
                            "role": "index",
                            "authority": None,
                            "authfilenumber": None,
                        },
                        {
                            "authfilenumber": None,
                            "authority": None,
                            "label": "type1",
                            "normalized": "type1",
                            "role": "index",
                            "type": "genreform",
                        },
                    ],
                    "name": "frmaee_findingaid",
                    "publisher": "FRMAEE",
                    "scopecontent": "Validit\xe9 du trait\xe9 : historique.",
                    "year": 1500,
                    "sortdate": "1500-01-01",
                    "startyear": 1500,
                    "stopyear": 1500,
                    "service": {"eid": None, "level": "None", "code": "FRMAEE", "title": "FRMAEE"},
                },
            )

    def test_import_filepath(self):
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                fpath = self.csv_filepath("frmaee_findingaid.csv")
                config = self.readerconfig.copy()
                dc.import_filepath(cnx, config, fpath)
                fa = cnx.execute("Any FA WHERE FA is FindingAid").one()
                did = fa.did[0]
                self.assertEqual(fa.name, "frmaee_findingaid")
                self.assertEqual(fa.eadid, "frmaee_findingaid")
                self.assertEqual(fa.publisher, "FRMAEE")
                self.assertFalse(fa.fatype)
                self.assertEqual(fa.scopecontent, None)
                self.assertEqual(fa.additional_resources, None)
                self.assertEqual(fa.accessrestrict, None)
                self.assertEqual(fa.userestrict, None)
                self.assertEqual(did.unitid, None)
                self.assertEqual(did.unittitle, "frmaee_findingaid")
                self.assertEqual(did.unitdate, None)
                self.assertEqual(did.startyear, None)
                self.assertEqual(did.stopyear, None)
                self.assertEqual(did.origination, "frmaee")
                self.assertEqual(did.lang_description, None)
                self.assertEqual(fa.fa_header[0].titleproper, "frmaee_findingaid")
                self.assertEqual(fa.findingaid_support[0].data_name, "frmaee_findingaid.csv")
                self.assertEqual(fa.findingaid_support[0].data_format, "text/csv")
                dids_rset = cnx.execute("Any D WHERE D is Did")
                self.assertEqual(len(dids_rset), 4)
                ies_rset = cnx.execute("Any X WHERE X is IN (AgentName, Geogname, Subject)")
                self.assertEqual(len(ies_rset), 10)
                dvs_rset = cnx.execute("Any D WHERE D is DigitizedVersion")
                self.assertEqual(len(dvs_rset), 3)
                facs_rset = cnx.execute("Any F WHERE F is FAComponent")
                self.assertEqual(len(facs_rset), 3)
                facs = list(facs_rset.entities())
                facs.sort(key=lambda fac: fac.did[0].unitid)
                fac1, fac2, fac3 = facs
                fac1_did = fac1.did[0]
                self.assertIn("Validité du traité : historique.", fac1.scopecontent)
                self.assertIn("Ressource complementaire 1", fac1.additional_resources)
                self.assertIn('<div class="ead-p">Libre accès</div>', fac1.accessrestrict)
                self.assertIn('<div class="ead-p">Libre de droit</div>', fac1.userestrict)
                self.assertEqual(fac1_did.unitid, "TRA13680001")
                self.assertEqual(fac1_did.unittitle, "Recueil de traités (1368-1408)")
                self.assertEqual(fac1_did.unitdate, "1500-01-01")
                self.assertEqual(fac1_did.startyear, 1500)
                self.assertEqual(fac1_did.stopyear, 1500)
                self.assertEqual(fac1_did.origination, "origine1")
                self.assertIn('<div class="ead-p">fra</div>', fac1_did.lang_description)
                self.assertIn('<div class="ead-p">Format 1</div>', fac1_did.physdesc)
                self.assertEqual(len(fac1.digitized_versions), 1)
                self.assertEqual(
                    fac1.digitized_versions[0].url,
                    "http://www.diplomatie.gouv.fr/traites/affichetraite.do?accord=TRA13680001",
                )
                self.assertEqual(fac1.digitized_versions[0].illustration_url, "img1")
                index_entries = [
                    (ie.authority[0].cw_etype, ie.authority[0].label) for ie in fac1.reverse_index
                ]
                self.assertCountEqual(
                    index_entries,
                    [
                        ("SubjectAuthority", "type1"),
                        ("SubjectAuthority", "subject"),
                        ("AgentAuthority", "corporname"),
                        ("AgentAuthority", "Henri VII"),
                        ("LocationAuthority", "Clermont-Ferrand"),
                    ],
                )
                self.assertIn(
                    "Validité du traité : historique. Lieu de signature : Vincennes.",
                    fac2.scopecontent,
                )
                self.assertIn("Ressource complementaire 2", fac2.additional_resources)
                self.assertIn('<div class="ead-p">Libre accès</div>', fac2.accessrestrict)
                self.assertIn('<div class="ead-p">Libre de droit</div>', fac2.userestrict)
                self.assertEqual(fac1.component_order, 0)
                fac2_did = fac2.did[0]
                self.assertEqual(fac2_did.unitid, "TRA13690001")
                self.assertEqual(fac2_did.unittitle, "Lettres patentes de Charles V, roi de France")
                self.assertEqual(fac2_did.unitdate, "1671-07-11 - 1683-09-13")
                self.assertEqual(fac2_did.startyear, 1671)
                self.assertEqual(fac2_did.stopyear, 1683)
                self.assertIn("Format 2", fac2_did.physdesc)
                self.assertIn('<div class="ead-p">eng</div>', fac2_did.lang_description)
                self.assertIn('<div class="ead-p">Format 2</div>', fac2_did.physdesc)
                self.assertEqual(fac2_did.origination, "origine2")
                self.assertEqual(len(fac2.digitized_versions), 1)
                self.assertEqual(
                    fac2.digitized_versions[0].url,
                    "http://www.diplomatie.gouv.fr/traites/affichetraite.do?accord=TRA13690001",
                )
                self.assertEqual(fac2.digitized_versions[0].illustration_url, "img2")
                self.assertEqual(len(fac2.reverse_index), 5)
                index_entries = [
                    (a.cw_etype, a.label)
                    for a in cnx.execute(
                        "Any A WHERE X eid %(e)s, I index X, I authority A", {"e": fac2.eid}
                    ).entities()
                ]
                self.assertCountEqual(
                    index_entries,
                    [
                        ("SubjectAuthority", "type2"),
                        ("SubjectAuthority", "subject2"),
                        ("AgentAuthority", "corporname2"),
                        ("AgentAuthority", "Charles V"),
                        ("LocationAuthority", "Paris"),
                    ],
                )
                fac3_did = fac3.did[0]
                self.assertEqual(fac2.component_order, 1)
                self.assertEqual(fac3_did.physdesc, None)
                self.assertEqual(fac3_did.lang_description, None)
                self.assertEqual(fac3.additional_resources, None)
                self.assertEqual(fac3_did.origination, None)
                self.assertEqual(fac3_did.unitid, "TRA13690003")
                self.assertEqual(
                    fac3.digitized_versions[0].url,
                    "http://www.diplomatie.gouv.fr/traites/affichetraite.do?accord=TRA15590001",
                )
                self.assertEqual(fac3.digitized_versions[0].illustration_url, None)
                self.assertEqual(fac3.component_order, 2)
                self.assertEqual(len(fac3.reverse_index), 0)

    def test_findingaid_support_hash_csv_without_metadatafile(self):
        """
        Trying: import csv file without metadata
        Expecting: findingaid_support data_hash is correctly set
        """
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales.csv")
                config = self.readerconfig.copy()
                dc.import_filepath(cnx, config, fpath)
                fa_support = cnx.execute("Any X WHERE F findingaid_support X").one()
                self.assertEqual(fa_support.data_hash, fa_support.compute_hash())
                self.assertTrue(fa_support.check_hash())

    def test_import_csv_without_metadatafile(self):
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                config = self.readerconfig.copy()
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales.csv")
                dc.import_filepath(cnx, config, fpath)
                self._test_medatadata_csv(cnx)

    def test_import_csv_with_metadatafile_symlink(self):
        """
        Trying: import csv file with metadata
        Expecting: a symlink to the appfiles-dir is set for the csv file
        """
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales.csv")
                meta_fpath = self.csv_filepath("metadata.csv")
                config = self.readerconfig.copy()
                config["dc_no_cache"] = False
                config["appfiles-dir"] = self.config["appfiles-dir"]
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                csvfile = cnx.execute("Any F WHERE X findingaid_support F").one()
                self.assertEqual(csvfile.data_hash, csvfile.compute_hash())
                self.assertTrue(csvfile.check_hash())
                destpath = f"{csvfile.data_hash}_{osp.basename(fpath)}"
                if not self.s3_bucket_name:
                    destpath = osp.join(self.config["appfiles-dir"], destpath)
                self.assertNotEqual(destpath, fpath)
                self.assertTrue(self.fileExists(destpath))
                if not self.s3_bucket_name:
                    self.assertTrue(osp.islink(destpath))

    def test_findingaid_support_hash_csv_with_metadatafile(self):
        """
        Trying: import csv file with metadata
        Expecting: findingaid_support data_hash is correctly set
        """
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales.csv")
                meta_fpath = self.csv_filepath("metadata.csv")
                config = self.readerconfig.copy()
                config["dc_no_cache"] = False
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                fa_support = cnx.execute("Any X WHERE F findingaid_support X").one()
                self.assertEqual(fa_support.data_hash, fa_support.compute_hash())
                self.assertTrue(fa_support.check_hash())

    def test_import_csv_with_metadatafile(self):
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales.csv")
                meta_fpath = self.csv_filepath("metadata.csv")
                config = self.readerconfig.copy()
                config["dc_no_cache"] = False
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                self._test_medatadata_csv(cnx)

    def test_metadata_csv_failed(self):
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                config = self.readerconfig.copy()
                config["dc_no_cache"] = False
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales.csv")
                meta_fpath = self.csv_filepath("metadata.csv")
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                # reimport a similar but same file
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales-ko.csv")
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                fa_rset = cnx.execute("Any COUNT(FA) WHERE FA is FindingAid")
                self.assertEqual(fa_rset[0][0], 2)
                facs_rset = cnx.execute("Any COUNT(FA) WHERE FA is FAComponent")
                self.assertEqual(facs_rset[0][0], 18)
                fa = cnx.find("FindingAid", eadid="FRAD092_9FI_cartes-postales").one()
                self._test_medatadata_csv(cnx, fa=fa)

    def test_metadata_reimport_csv_tab_dialect(self):
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                config = self.readerconfig.copy()
                config["dc_no_cache"] = False
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales.csv")
                meta_fpath = self.csv_filepath("metadata.csv")
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                fa_rset = cnx.execute("Any COUNT(FA) WHERE FA is FindingAid")
                self.assertEqual(fa_rset[0][0], 1)
                facs_rset = cnx.execute("Any COUNT(FA) WHERE FA is FAComponent")
                self.assertEqual(facs_rset[0][0], 10)
                # reimport a file with data separated by a tabulation
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales-tab.csv")
                meta_fpath = self.csv_filepath("metadata.csv")
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                fa_rset = cnx.execute("Any COUNT(FA) WHERE FA is FindingAid")
                self.assertEqual(fa_rset[0][0], 1)
                facs_rset = cnx.execute("Any COUNT(FA) WHERE FA is FAComponent")
                self.assertEqual(facs_rset[0][0], 10)

    def test_metadata_csv_wrong_identifier(self):
        """
        Trying: process a fname which not exists in "identifiant_fichier" column of metadata.csv
        Expecting: CSVIntegrityError is raised
        """
        metadata_filepath = self.csv_filepath("metadata.csv")
        with self.assertRaises(CSVIntegrityError):
            fname = "FRAD092_9F2_cartes-postales.csv"
            dc.csv_metadata_without_cache(fname, metadata_filepath)

    def test_metadata_csv_reimport(self):
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales.csv")
                meta_fpath = self.csv_filepath("metadata.csv")
                config = self.readerconfig.copy()
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                self._test_medatadata_csv(cnx)
                fa = cnx.execute("Any FA WHERE FA is FindingAid").one()
                self.assertEqual(2, cnx.execute("Any COUNT(X) WHERE X is File")[0][0])
                fa.cw_set(name="toto", publisher="titi", fatype=None)
                cnx.commit()
                self.assertEqual(fa.name, "toto")
                # reimport the same file
                config.update({"dc_no_cache": False, "reimport": True, "force_delete": True})
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                self._test_medatadata_csv(cnx)
                self.assertEqual(2, cnx.execute("Any COUNT(X) WHERE X is File")[0][0])
                for row in cnx.execute(f"Any {self.fkeyfunc}(D) WHERE X data D, X is File"):
                    fkey = row[0].getvalue()
                    self.assertTrue(self.fileExists(fkey))

    def test_create_ape_ead_file(self):
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales.csv")
                meta_fpath = self.csv_filepath("metadata.csv")
                config = self.readerconfig.copy()
                config["dc_no_cache"] = False
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                # reimport the same file
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                fa = cnx.execute("Any FA WHERE FA is FindingAid").one()
                ape_ead_file = fa.ape_ead_file[0]
                filepath = cnx.execute(
                    "Any FSPATH(D) WHERE X eid %(e)s, X data D", {"e": ape_ead_file.eid}
                )[0][0].getvalue()
                expected_filepath = self.get_filepath_by_storage(
                    f"{self.config['appfiles-dir']}/ape-ead/FRAD092/ape-FRAD092_9FI_cartes-postales.xml"  # noqa
                )
                self.assertEqual(filepath.decode("utf-8"), expected_filepath)
                self.assertTrue(self.fileExists(filepath))
                content = ape_ead_file.data.read()
                tree = etree.fromstring(content)
                eadid = tree.xpath("//e:eadid", namespaces={"e": tree.nsmap[None]})[0]
                self.assertEqual(
                    eadid.attrib["url"], "https://francearchives.fr/{}".format(fa.rest_path())
                )
                self.assertEqual(eadid.attrib["countrycode"], "FR")

    def test_name_stable_id_dc_with_metadata(self):
        """stable_id is based in the filename with extension:
        - column 'identifiant_fichier' of metadata file with extension:"""
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales.csv")
                meta_fpath = self.csv_filepath("metadata.csv")
                config = self.readerconfig.copy()
                config["dc_no_cache"] = False
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                fa = cnx.find("FindingAid").one()
                self.assertEqual("FRAD092_9FI_cartes-postales", fa.eadid)
                self.assertEqual("FRAD092_9FI_cartes-postales.csv", fa.name)
                self.assertEqual(fa.stable_id, usha1(fa.name))

    def test_name_stable_id_dc_without_metadata(self):
        """stable id is based on filename without extension"""
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales.csv")
                config = self.readerconfig.copy()
                config["dc_no_cache"] = False
                dc.import_filepath(cnx, config, fpath)
                fa = cnx.find("FindingAid").one()
                self.assertEqual("FRAD092_9FI_cartes-postales", fa.eadid)
                self.assertEqual("FRAD092_9FI_cartes-postales", fa.name)
                self.assertEqual(fa.stable_id, usha1(fa.name))

    def test_import_csv_with_metadatafile_faprops(self):
        """
        Trying: import a FindingAid with dates
        Expecting: displayed FindingAid dates are the same as FindingAid unitdate
        """
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales.csv")
                meta_fpath = self.csv_filepath("metadata.csv")
                config = self.readerconfig.copy()
                config["dc_no_cache"] = False
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                fa = cnx.execute("Any FA WHERE FA is FindingAid").one()
                self.assertEqual(fa.did[0].unitdate, "1900 - 1944-05-31")
                self.assertEqual(fa.did[0].period, "1900 - 1944")
                adapter = fa.cw_adapt_to("entity.main_props")
                self.assertEqual(adapter.formatted_dates, "Date : 1900 - 1944-05-31")

    def test_import_csv_authorities_facomponent(self):
        """
        Trying: import a FindingComponent with authorities with ";" in labels
        Expecting: Authorities are correctly parsed
        """
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                config = self.readerconfig.copy()
                fpath = self.csv_filepath("FRAM059017_data_archives_anciennes.csv")
                meta_fpath = self.csv_filepath("metadata.csv")
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                fc = cnx.execute("Any FA WHERE FA is FAComponent").one()
                index_entries = sorted(
                    [(ie.authority[0].cw_etype, ie.authority[0].label) for ie in fc.reverse_index]
                )
                from pprint import pprint

                pprint(index_entries)
                expected = [
                    ("AgentAuthority", "Egmont (famille d’)"),
                    ("AgentAuthority", "Jacques III de Luxembourg-Fiennes (12..-1530)"),
                    ("AgentAuthority", "Jean Ier de Bourgogne (1371-1419\xa0; dit Jean Sans Peur)"),
                    ("LocationAuthority", "Armentières (Nord, France)"),
                    ("LocationAuthority", "Bois-Grenier (Nord, France)"),
                    ("LocationAuthority", "Fleurbaix (Pas-de-Calais, France)"),
                    ("LocationAuthority", "Frelinghien\xa0(Nord, France)"),
                    ("LocationAuthority", "Houplines (Nord, France)"),
                    ("LocationAuthority", "La Chapelle-d’Armentières (Nord, France)"),
                ]
                self.assertCountEqual(expected, index_entries)


class CSVDCReImportTC(CSVImportMixIn, PostgresTextMixin, testlib.CubicWebTC):
    readerconfig = {
        "noes": True,
        "esonly": False,
        "appid": "data",
        "nodrop": True,
        "dc_no_cache": True,
        "reimport": True,
        "force_delete": True,
        "index-name": "dummy",
    }

    def setUp(self):
        super(CSVDCReImportTC, self).setUp()
        with self.admin_access.cnx() as cnx:
            self.service = cnx.create_entity(
                "Service", code="FRAD092", short_name="AD 92", level="level-D", category="foo"
            )
            cnx.commit()

    def test_index_reimport(self):
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales.csv")
                config = self.readerconfig.copy()
                dc.import_filepath(cnx, config, fpath)
                ferry = cnx.execute(
                    "Any X WHERE X is AgentAuthority, X label %(e)s", {"e": "Jules Ferry"}
                ).one()
                self.assertEqual(len(ferry.reverse_authority[0].index), 1)
                # reimport the same file
                dc.import_filepath(cnx, config, fpath)
                # we shell have only one AgentAuthority for Jules Ferry
                new_ferry = cnx.execute(
                    "Any X WHERE X is AgentAuthority, X label %(e)s", {"e": "Jules Ferry"}
                ).one()
                self.assertEqual(ferry.eid, new_ferry.eid)

    def test_reimport_csv_with_files(self):
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                fpaths = [
                    self.csv_filepath("FRAD092_9FI_cartes-postales.csv"),
                    self.csv_filepath("FRAD092_affiches_culture.csv"),
                    self.csv_filepath("FRAD092_affiches_anciennes.csv"),
                ]
                config = self.readerconfig.copy()
                config["dc_no_cache"] = False
                dc.import_filepaths(cnx, config, fpaths)
                fa1, fa2, f3 = cnx.find("FindingAid").entities()

    def test_reimport_csv_without_metadatafile(self):
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales.csv")
                config = self.readerconfig.copy()
                dc.import_filepath(cnx, config, fpath)
                # reimport the same file
                dc.import_filepath(cnx, config, fpath)
                self._test_medatadata_csv(cnx)

    def test_reimport_csv_with_metadatafile(self):
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales.csv")
                meta_fpath = self.csv_filepath("metadata.csv")
                config = self.readerconfig.copy()
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                # reimport the same file
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                self._test_medatadata_csv(cnx)

    def test_creation_date_dc_import(self):
        """Test FindingAid, FAComponent creation date is keept between reimports

        Trying: import and reimport a FindingAid
        Expecting: reimported FindingAid and FAComponent have original creation_date
        """
        with self.admin_access.cnx() as cnx:
            cnx.create_entity(
                "Service", code="FRAD092", short_name="AD 92", level="level-D", category="foo"
            )
            cnx.commit()
            fpath = self.csv_filepath("FRAD092_9FI_cartes-postales.csv")
            meta_fpath = self.csv_filepath("metadata.csv")
            config = self.readerconfig.copy()
            dc.import_filepath(cnx, config, fpath, meta_fpath)
            fa_old = cnx.execute("Any X WHERE X is FindingAid").one()
            comp_stable_id = "e3de7aefc6f62dfea3a5026232d5f295f388cedf"
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
            config.update({"dc_no_cache": False, "reimport": True, "force_delete": True})
            dc.import_filepath(cnx, config, fpath, meta_fpath)
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


if __name__ == "__main__":
    unittest.main()
