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

import io
from lxml import etree

import unittest
import os
import os.path

from cubicweb.devtools.testlib import CubicWebTC

from cubicweb_francearchives.dataimport import oai
from cubicweb_francearchives.dataimport import (
    load_services_map,
    service_infos_from_service_code,
)
from cubicweb_francearchives.dataimport.oai_nomina import compute_nomina_stable_id, build_persons

from cubicweb_francearchives.dataimport.csv_nomina import CSVNominaReader
from cubicweb_francearchives.dataimport.stores import create_massive_store

from cubicweb_francearchives.testutils import (
    NominaImportMixin,
    PostgresTextMixin,
    OaiSickleMixin,
)

from pgfixtures import setup_module, teardown_module  # noqa


class OaiNominaUtilsTest(CubicWebTC):
    def test_compute_nomina_stable_id_with_service_code(self):
        expected = "299648bc990b977d5ee1852ffad08d5840b36985"
        self.assertEqual(expected, compute_nomina_stable_id("FRAD003", "FRAD003_34"))

    def test_compute_nomina_stable_id_without_noservice(self):
        expected = "299648bc990b977d5ee1852ffad08d5840b36985"
        self.assertEqual(expected, compute_nomina_stable_id("FRAD003", "34"))


class OaiNominaImportTC(PostgresTextMixin, NominaImportMixin, OaiSickleMixin, CubicWebTC):
    def filepath(self):
        assert self.filename is not None
        return self.datapath(os.path.join("oai_nomina", self.filename))

    def create_repo(self, cnx, url):
        return cnx.create_entity(
            "OAIRepository", name="{} repo".format(self.service.code), service=self.service, url=url
        )

    @property
    def path(self):
        return "{nomina_services_dir}/{code}/oaipmh/".format(
            nomina_services_dir=self.config["nomina-services-dir"], **self.service_infos
        )

    def setup_database(self):
        super(OaiNominaImportTC, self).setup_database()
        with self.admin_access.cnx() as cnx:
            self.service = cnx.create_entity(
                "Service", name="Département des Ardennes", code="FRAD008", category="DS"
            )
            cnx.commit()
            services_map = load_services_map(cnx)
            self.service_infos = service_infos_from_service_code(self.service.code, services_map)

    def test_build_persons(self):
        """
        Trying: parse a valid OAI-PMH recorde
        Expecting: persons data are build as expected
        """
        document = io.StringIO(
            """
<nomina:document xmlns:nomina="http://www.france-genealogie.fr/ns/nomina/1.0"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
xsi:schemaLocation="http://www.france-genealogie.fr/ns/nomina/1.0 genealogie1.4.xsd"
id="6" uri="http://bla.org/6">
    <nomina:personne>
     <nomina:nom>MARGUERITAT</nomina:nom>
     <nomina:prenoms>Jean</nomina:prenoms>
     <nomina:prenoms>Pierre</nomina:prenoms>
    </nomina:personne>
    <nomina:personne>
     <nomina:nom>PATUREAU</nomina:nom>
    <nomina:prenoms>Roberte Marie Jacqueline</nomina:prenoms>
    </nomina:personne>
    <nomina:localisation code="RM">
     <nomina:precision/>
    </nomina:localisation>
    <nomina:date annee="1868">1868</nomina:date>
</nomina:document>
                                     """
        )
        tree = etree.parse(document)
        self.assertCountEqual(
            build_persons(tree.getroot()),
            [
                {"f": "Jean Pierre", "n": "MARGUERITAT"},
                {"f": "Roberte Marie Jacqueline", "n": "PATUREAU"},
            ],
        )

    def test_harvest_nominarecords(self):
        """Test OAI nomina harvesting.

        Trying: valid OAI-PMH
        Expecting: import and create 7 NominaRecords
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "archives_cd08_simple.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=nomina&set=ad08_registres_matricules"  # noqa
            service_infos = self.service_infos.copy()
            service_infos["oai_url"] = f"file://{self.filepath()}"
            filepaths = oai.harvest_oai_nomina(
                cnx, url, service_infos, dry_run=True, csv_rows_limit=3
            )
            filpathes = sorted(filepaths)
            self.assertEqual(3, len(filpathes))
            for i, filepath in enumerate(filpathes, start=1):
                self.assertRegex(
                    filepath, r"tmp/FRAD008/oaipmh/FRAD008_nomina_\d+_{i}.csv".format(i=i)
                )

    def test_import_nominarecords(self):
        """Test OAI nomina standard importing.

        Trying: valid OAI-PMH
        Expecting: import and create 7 NominaRecords created
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "archives_cd08_simple.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=nomina&set=ad08_registres_matricules"  # noqa
            filepaths = oai.harvest_oai_nomina(cnx, url, self.service_infos, dry_run=False)
            self.assertEqual(1, len(filepaths))
            filepath = filepaths[0]
            self.assertTrue(self.fileExists(self.get_filepath_by_storage(filepath)))
            self.import_filepath(cnx, filepath, doctype="OAI")
            rset = cnx.execute("Any X WHERE X is NominaRecord")
            self.assertEqual(7, len(rset))
            expected = [
                "Ratier, Isidore Louis Alexandre",
                "Suquez, Léon Gustave; Suquez, Jean Gustave",
                "Christel, Alcide Fernand",
                "Mathieu, Jean Louis Auguste",
                "Buzy, Léon Charles",
                "Croïet, Alexandre Théophile",
                "Renel, Jules Nicolas",
            ]
            for nomina in rset.entities():
                self.assertEqual(nomina.doctype_code, "RM")
                self.assertEqual(nomina.acte_year, nomina.get_dates(nomina.doctype_code))
                self.assertIn(nomina.dc_title(), expected)
            stable_id = compute_nomina_stable_id(self.service_infos["code"], "5")
            nomina = cnx.find("NominaRecord", stable_id=stable_id).one()
            expected = {
                "c": {"c": "1R 013", "e": "2", "n": "53", "o": ["charpentier"]},
                "e": {
                    "N": {"d": [{"y": "1851"}], "l": [{"d": "Ardennes", "p": "Gespunsart"}]},
                    "R": {"l": [{"d": "Ardennes", "p": "Gespunsart"}]},
                    "RM": {
                        "d": [{"y": "1871"}],
                        "l": [{"c": "France", "cc": "FR", "d": "Ardennes", "p": "Mézières"}],
                    },
                },
                "p": [{"f": "Jean Louis Auguste", "n": "Mathieu"}],
                "t": "RM",
                "u": "https://archives.cd08.fr/ark:/75583/s005328744149810/532874414b2bd",
            }
            self.assertEqual(expected, nomina.data)
            self.assertEqual("5", nomina.oai_id)
            adapter = nomina.cw_adapt_to("entity.main_props")
            self.assertEqual("Gespunsart (Ardennes)", adapter.get_event("R"))
            self.assertEqual("1871; Mézières (Ardennes, France)", adapter.get_event("RM"))
            self.assertEqual("1851", nomina.birth_date)
            self.assertEqual("", nomina.get_dates("D"))
            self.assertEqual("1871", nomina.get_dates("RM"))
            self.assertEqual([{"y": "1871"}], nomina.get_dates("RM", fmt=False))
            self.assertEqual("", nomina.get_locations("D"))
            self.assertEqual("Gespunsart (Ardennes)", nomina.get_locations("R"))
            self.assertEqual("Mézières (Ardennes, France)", nomina.get_locations("RM"))
            self.assertCountEqual(
                [{"c": "France", "cc": "FR", "d": "Ardennes", "p": "Mézières"}],
                nomina.get_locations("RM", fmt=False),
            )
            self.assertEqual("NMN_E_2", nomina.education)
            self.assertFalse(nomina.digitized)
            stable_id = compute_nomina_stable_id(self.service_infos["code"], "888")
            nomina = cnx.find("NominaRecord", stable_id=stable_id).one()
            expected = {
                "c": {"c": "1R 155", "n": "110", "o": ["ferronnier"]},
                "e": {
                    "N": {"d": [{"y": "1880"}], "l": [{"d": "Ardennes", "p": "Renwez"}]},
                    "R": {
                        "l": [{"d": "Ardennes", "p": "Château-Regnault-Bogny (Bogny-sur-Meuse)"}]
                    },
                    "RM": {
                        "d": [{"y": "1900"}],
                        "l": [{"c": "France", "cc": "FR", "d": "Ardennes", "p": "Mézières"}],
                    },
                },
                "p": [{"f": "Léon Gustave", "n": "Suquez"}, {"f": "Jean Gustave", "n": "Suquez"}],
                "t": "RM",
                "u": "https://archives.cd08.fr/ark:/75583/s0053eb9b6047b1f/53eb9b604f5b9",
            }
            self.assertEqual(expected, nomina.data)
            self.assertEqual("888", nomina.oai_id)
            self.assertEqual("1880", nomina.birth_date)
            self.assertEqual("1900", nomina.get_dates("RM"))
            self.assertEqual("Mézières (Ardennes, France)", nomina.get_locations("RM"))
            adapter = nomina.cw_adapt_to("entity.main_props")
            self.assertEqual("1880; Renwez (Ardennes)", adapter.get_event("N"))
            self.assertEqual(
                "Château-Regnault-Bogny (Bogny-sur-Meuse) (Ardennes)", adapter.get_event("R")
            )
            # test MARGUERITAT is not imported (no doctype)
            stable_id = compute_nomina_stable_id(self.service_infos["code"], "5121")
            self.assertFalse(cnx.find("NominaRecord", stable_id=stable_id))

    def test_import_wrong_namespace(self):
        """Test OAI nomina standard importing.

        Trying: valid OAI-PMH
        Expecting: do not import record with wrong namespace
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "archives_cd08_wrong_namespace.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=nomina&set=ad08_registres_matricules"  # noqa
            filepaths = oai.harvest_oai_nomina(cnx, url, self.service_infos, dry_run=False)
            self.assertEqual(0, len(filepaths))

    def test_import_no_doctype(self):
        """Test OAI nomina standard importing.

        Trying: valid OAI-PMH
        Expecting: do not import record without doctype
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "archives_cd08_no_doctype.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=nomina&set=ad08_registres_matricules"  # noqa
            filepaths = oai.harvest_oai_nomina(cnx, url, self.service_infos, dry_run=False)
            self.assertEqual(0, len(filepaths))

    def test_import_no_person_data(self):
        """Test OAI nomina standard importing.

        Trying: valid OAI-PMH
        Expecting: do not import record without person_data
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "archives_cd08_no_person.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=nomina&set=ad08_registres_matricules"  # noqa
            filepaths = oai.harvest_oai_nomina(cnx, url, self.service_infos, dry_run=False)
            self.assertEqual(0, len(filepaths))

    def test_deleted_nominarecord(self):
        """Test OAI nomina standard importing.

        Trying: valid OAI-PMH
        Expecting: import 10 NominaRecords with only 7 valid and delete one of them
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "archives_cd08_simple.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=nomina&set=ad08_registres_matricules"  # noqa
            filepaths = oai.harvest_oai_nomina(cnx, url, self.service_infos, dry_run=False)
            self.import_filepath(cnx, filepaths[0], doctype="OAI")
            stable_id = compute_nomina_stable_id(self.service_infos["code"], "888")
            self.assertTrue(cnx.find("NominaRecord", stable_id=stable_id))
            self.filename = "archives_cd08_delete.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=nomina&set=ad08_registres_matricules"  # noqa
            filepaths = oai.harvest_oai_nomina(cnx, url, self.service_infos, dry_run=False)
            store = create_massive_store(cnx, nodrop=True)
            reader = CSVNominaReader(self.readerconfig, store, self.service.code)
            reader.import_records(filepaths[0], doctype="OAI")
            self.assertFalse(cnx.find("NominaRecord", stable_id=stable_id))


if __name__ == "__main__":
    unittest.main()
