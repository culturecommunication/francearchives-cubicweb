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

import unittest

from cubicweb.devtools.testlib import CubicWebTC

from cubicweb_francearchives.dataimport import (
    load_services_map,
    service_infos_from_service_code,
)
from cubicweb_francearchives.dataimport.oai_nomina import compute_nomina_stable_id

from cubicweb_francearchives.testutils import (
    NominaImportMixin,
    PostgresTextMixin,
)

from pgfixtures import setup_module, teardown_module  # noqa


class CSVNominaImportTC(PostgresTextMixin, NominaImportMixin, CubicWebTC):
    def csv_filepath(self, filepath):
        return self.get_or_create_imported_filepath(f"nomina/{filepath}")

    def setup_database(self):
        super(CSVNominaImportTC, self).setup_database()
        with self.admin_access.cnx() as cnx:
            self.service = cnx.create_entity(
                "Service",
                name="Département des Landes",
                code="FRAD040",
                category="DS",
                short_name="Landes",
            )
            cnx.commit()
            services_map = load_services_map(cnx)
            self.service_infos = service_infos_from_service_code(self.service.code, services_map)

    def test_import_rm_nominarecords(self):
        """Test CSV RM standard importing.

        Trying: valid OAI-PMH
        Expecting: 22 NominaRecords are created
        """
        with self.admin_access.cnx() as cnx:
            filepath = self.csv_filepath("Landes_RM_normalise.csv")
            self.import_filepath(cnx, filepath, doctype="RM")
            rset = cnx.execute("Any X WHERE X is NominaRecord")
            self.assertEqual(22, len(rset))
            for nomina in rset.entities():
                self.assertEqual(nomina.doctype_code, "RM")
                self.assertEqual(nomina.infos["c"], "R P 392")
            stable_id = "dcd84014de91455b33bb622ba969fd828815a7b0"
            nomina = cnx.find("NominaRecord", stable_id=stable_id).one()
            expected = {
                "c": {"c": "R P 392", "e": "3", "n": "1", "o": ["charron"]},
                "e": {
                    "N": [
                        {
                            "d": {"y": "1867"},
                            "l": {
                                "c": "France",
                                "cc": "FR",
                                "d": "Landes",
                                "dc": "40",
                                "p": "Labrit",
                            },
                        }
                    ],
                    "R": [
                        {"l": {"c": "France", "cc": "FR", "d": "Landes", "dc": "40", "p": "Labrit"}}
                    ],
                    "RM": [
                        {
                            "d": {"y": "1887"},
                            "l": {
                                "c": "France",
                                "cc": "FR",
                                "d": "Landes",
                                "dc": "40",
                                "p": "Mont-de-Marsan",
                            },
                        }
                    ],
                },
                "i": "FRAD040_2",
                "p": [{"f": "Jean", "n": "Dubos"}],
                "t": "RM",
                "u": "http://www.archives.landes.fr/ark:/35227/s0052cbf404e1290/52cc0a4a20d4f",
            }
            self.assertEqual(expected, nomina.data)
            self.assertEqual("1867", nomina.birth_date)
            self.assertEqual("", nomina.get_dates("D"))
            self.assertEqual("1887", nomina.get_dates("RM"))
            self.assertEqual([{"y": "1887"}], nomina.get_dates("RM", fmt=False))
            self.assertEqual("1887", nomina.acte_year)
            adapter = nomina.cw_adapt_to("entity.main_props")
            event = adapter.get_event("N")
            self.assertEqual(["1867; Labrit (Landes, France)"], event)
            self.assertEqual(["Labrit (Landes, France)"], adapter.get_event("R"))
            self.assertEqual("Labrit (Landes, France)", nomina.get_locations("N"))
            self.assertEqual(["1887; Mont-de-Marsan (Landes, France)"], adapter.get_event("RM"))
            self.assertEqual("Mont-de-Marsan (Landes, France)", nomina.get_locations("RM"))
            self.assertEqual("", nomina.get_locations("D"))
            self.assertEqual(
                [{"c": "France", "cc": "FR", "d": "Landes", "dc": "40", "p": "Mont-de-Marsan"}],
                nomina.get_locations("RM", fmt=False),
            )
            self.assertEqual("", nomina.get_locations("M"))
            self.assertEqual(
                "http://www.archives.landes.fr/ark:/35227/s0052cbf404e1290/52cc0a4a20d4f",
                nomina.source_url,
            )
            self.assertEqual(["charron"], nomina.occupations)
            self.assertEqual("NMN_E_3", nomina.education)
            self.assertEqual("FRAD040_2", nomina.notice_id)
            stable_id = "d0d3c2e7cc1c96232f942996a593354891cc5fbb"
            nomina = cnx.find("NominaRecord", stable_id=stable_id).one()
            expected = {
                "c": {"c": "R P 392", "e": "0", "n": "15", "o": ["domestique"]},
                "e": {
                    "N": [
                        {
                            "d": {"y": "1867"},
                            "l": {
                                "c": "France",
                                "cc": "FR",
                                "d": "Landes",
                                "dc": "40",
                                "p": "Canenx (Canenx-et-Réaut)",
                            },
                        }
                    ],
                    "R": [
                        {
                            "l": {
                                "c": "France",
                                "cc": "FR",
                                "d": "Landes",
                                "dc": "40",
                                "p": "Canenx (Canenx-et-Réaut)",
                            }
                        }
                    ],
                    "RM": [
                        {
                            "d": {"y": "1887"},
                            "l": {
                                "c": "France",
                                "cc": "FR",
                                "d": "Landes",
                                "dc": "40",
                                "p": "Mont-de-Marsan",
                            },
                        }
                    ],
                },
                "i": "FRAD040_16",
                "p": [{"f": "Pierre", "n": "Béton"}],
                "t": "RM",
                "u": "http://www.archives.landes.fr/ark:/35227/s0052cbf404e1290/52cc0a4a252be",
            }
            self.assertEqual(expected, nomina.data)
            self.assertEqual("FRAD040_16", nomina.notice_id)
            stable_id = "ece2263be36ad30e199786adf79c9d161361ba8d"
            nomina = cnx.find("NominaRecord", stable_id=stable_id).one()
            expected = {
                "c": {"c": "R P 392", "e": "0", "n": "22", "o": ["laboureur"]},
                "e": {
                    "N": [
                        {
                            "d": {"y": "1867"},
                            "l": {
                                "c": "France",
                                "cc": "FR",
                                "d": "Landes",
                                "dc": "40",
                                "p": "Arue",
                            },
                        }
                    ],
                    "R": [
                        {"l": {"c": "France", "cc": "FR", "d": "Landes", "dc": "40", "p": "Cère"}}
                    ],
                    "RM": [
                        {
                            "d": {"y": "1887"},
                            "l": {
                                "c": "France",
                                "cc": "FR",
                                "d": "Landes",
                                "dc": "40",
                                "p": "Mont-de-Marsan",
                            },
                        }
                    ],
                },
                "i": "FRAD040_23",
                "p": [{"f": "Barthélémy", "n": "Duprat"}],
                "t": "RM",
                "u": "http://www.archives.landes.fr/ark:/35227/s0052cbf404e1290/52cc0a4a27570",
            }
            self.assertEqual(expected, nomina.data)
            self.assertEqual("FRAD040_23", nomina.notice_id)

    def test_import_mpf1418_nominarecords(self):
        """Test CSV MPF14-18 standard importing.

        Trying: import 23 NominaRecords one of which is duplicated
        Expecting: 22 NominaRecords are created
        """
        with self.admin_access.cnx() as cnx:
            filepath = self.csv_filepath("Landes_RM_normalise.csv")
            self.import_filepath(cnx, filepath, doctype="MPF14-18")
            rset = cnx.execute("Any X WHERE X is NominaRecord")
            self.assertEqual(22, len(rset))
            for nomina in rset.entities():
                self.assertEqual(nomina.doctype_code, "MPF14-18")
            stable_id = "dcd84014de91455b33bb622ba969fd828815a7b0"
            nomina = cnx.find("NominaRecord", stable_id=stable_id).one()
            self.assertEqual("", nomina.get_dates("D"))
            self.assertEqual("1887", nomina.get_dates("RM"))
            self.assertEqual("", nomina.acte_year)

    def test_import_nominarecords_wrong_headers(self):
        """Test CSV RM standard importing.

        Trying: import a CSV file with wrong headers
        Expecting: No NominaRecords are created
        """
        with self.admin_access.cnx() as cnx:
            filepath = self.csv_filepath("Landes_RM_normalise_ko.csv")
            self.import_filepath(cnx, filepath, doctype="RM")
            rset = cnx.execute("Any X WHERE X is NominaRecord")
            self.assertFalse(rset)

    def test_update_nominarecords(self):
        """Test CSV RM standard importing.

        Trying: create 20 new NominaRecords and update 2 existigs NominaRecords
        Expecting: 22 NominaRecords are created/updated
        """
        with self.admin_access.cnx() as cnx:
            stable_id_16 = compute_nomina_stable_id(self.service.code, "16")
            cnx.create_entity(
                "NominaRecord",
                stable_id=stable_id_16,
                json_data={"p": [{"n": "Valjean"}], "t": "RM"},
                service=self.service.eid,
            )
            stable_id_23 = compute_nomina_stable_id(self.service.code, "23")
            cnx.create_entity(
                "NominaRecord",
                stable_id=stable_id_23,
                json_data={"p": [{"n": "Valjean"}], "t": "RM"},
                service=self.service.eid,
            )
            cnx.commit()
            self.assertEqual(2, len(cnx.find("NominaRecord")))
            filepath = self.csv_filepath("Landes_RM_normalise.csv")
            self.import_filepath(cnx, filepath, doctype="RM")
            rset = cnx.execute("Any X WHERE X is NominaRecord")
            self.assertEqual(22, len(rset))
            nomina = cnx.find("NominaRecord", stable_id=stable_id_16).one()
            expected = {
                "c": {"c": "R P 392", "e": "0", "n": "15", "o": ["domestique"]},
                "e": {
                    "N": [
                        {
                            "d": {"y": "1867"},
                            "l": {
                                "c": "France",
                                "cc": "FR",
                                "d": "Landes",
                                "dc": "40",
                                "p": "Canenx (Canenx-et-Réaut)",
                            },
                        }
                    ],
                    "R": [
                        {
                            "l": {
                                "c": "France",
                                "cc": "FR",
                                "d": "Landes",
                                "dc": "40",
                                "p": "Canenx (Canenx-et-Réaut)",
                            }
                        }
                    ],
                    "RM": [
                        {
                            "d": {"y": "1887"},
                            "l": {
                                "c": "France",
                                "cc": "FR",
                                "d": "Landes",
                                "dc": "40",
                                "p": "Mont-de-Marsan",
                            },
                        }
                    ],
                },
                "i": "FRAD040_16",
                "p": [{"f": "Pierre", "n": "Béton"}],
                "t": "RM",
                "u": "http://www.archives.landes.fr/ark:/35227/s0052cbf404e1290/52cc0a4a252be",
            }
            self.assertEqual(expected, nomina.data)
            nomina = cnx.find("NominaRecord", stable_id=stable_id_23).one()
            expected = {
                "c": {"c": "R P 392", "e": "0", "n": "22", "o": ["laboureur"]},
                "e": {
                    "N": [
                        {
                            "d": {"y": "1867"},
                            "l": {
                                "c": "France",
                                "cc": "FR",
                                "d": "Landes",
                                "dc": "40",
                                "p": "Arue",
                            },
                        }
                    ],
                    "R": [
                        {"l": {"c": "France", "cc": "FR", "d": "Landes", "dc": "40", "p": "Cère"}}
                    ],
                    "RM": [
                        {
                            "d": {"y": "1887"},
                            "l": {
                                "c": "France",
                                "cc": "FR",
                                "d": "Landes",
                                "dc": "40",
                                "p": "Mont-de-Marsan",
                            },
                        }
                    ],
                },
                "i": "FRAD040_23",
                "p": [{"f": "Barthélémy", "n": "Duprat"}],
                "t": "RM",
                "u": "http://www.archives.landes.fr/ark:/35227/s0052cbf404e1290/52cc0a4a27570",
            }
            self.assertEqual(expected, nomina.data)

    def test_delete_nominarecords(self):
        """Test OAI nomina standard importing.


        Trying: import 22 new NominaRecords and reimport same data with 1 NominaRecord deleted
        Expecting: 21 NominaRecords are found after reimport
        """
        with self.admin_access.cnx() as cnx:
            filepath = self.csv_filepath("Landes_RM_normalise.csv")
            self.import_filepath(cnx, filepath, doctype="RM")
            self.assertEqual(22, cnx.execute("Any COUNT(X) WHERE X is NominaRecord")[0][0])
            stable_id = "d0d3c2e7cc1c96232f942996a593354891cc5fbb"
            self.assertTrue(cnx.find("NominaRecord", stable_id=stable_id).one())
            print(cnx.find("NominaRecord", stable_id=stable_id).one().json_data)
            # reimport with deleted FRAD040_16
            filepath = self.csv_filepath("Landes_RM_normalise_delete.csv")
            self.import_filepath(cnx, filepath, delimiter=",", doctype="RM")
            self.assertEqual(21, cnx.execute("Any COUNT(X) WHERE X is NominaRecord")[0][0])
            self.assertFalse(cnx.find("NominaRecord", stable_id=stable_id))

    def test_import_nominarecords_csv_oai(self):
        """Test CSV nomina importing with data in OAI CSV form.

        Trying: import 5 NominaRecords one of which is duplicated
        Expecting: 4 NominaRecords are created
        """
        with self.admin_access.cnx() as cnx:
            filepath = self.csv_filepath("FRAD003_oai.csv")
            self.import_filepath(cnx, filepath, doctype="OAI")
            rset = cnx.execute("Any X WHERE X is NominaRecord")
            self.assertEqual(4, len(rset))
            for nomina in rset.entities():
                self.assertEqual(nomina.doctype_code, "RM")
            stable_id = "299648bc990b977d5ee1852ffad08d5840b36985"
            nomina = cnx.find("NominaRecord", stable_id=stable_id).one()
            expected = {
                "c": {"c": "1 R 453", "e": "0", "n": "21", "o": ["Charretier"]},
                "e": {
                    "N": {
                        "d": [{"y": "1872"}],
                        "l": [{"c": "France", "d": "Eure-et-Loir", "p": "Illiers"}],
                    },
                    "R": {"l": [{"d": "Eure-et-Loir", "p": "Epernon"}]},
                    "RM": {
                        "d": [{"y": "1892"}],
                        "l": [{"c": "France", "cc": "FR", "d": "Eure-et-Loir", "dc": "28"}],
                    },
                },
                "p": [{"f": "Isidore Louis Alexandre", "n": "Ratier"}],
                "t": "RM",
                "u": "http://www.archives28.fr/ark:/66007/s0054c63a21de1d9/54e8ac05dec3e",
            }
            self.assertEqual(expected, nomina.data)
            self.assertEqual("34", nomina.oai_id)

    def test_import_nominarecords_csv_oai_no_doctype(self):
        """Test CSV nomina importing with data in OAI CSV form without doctype.

        Trying: valid CSV
        Expecting: 0 NominaRecords are created
        """
        with self.admin_access.cnx() as cnx:
            filepath = self.csv_filepath("FRAD003_oai_no_doctype.csv")
            self.import_filepath(cnx, filepath, doctype="OAI")
            self.assertFalse(cnx.execute("Any X WHERE X is NominaRecord"))

    def test_import_nominarecords_csv_oai_no_person(self):
        """Test CSV nomina importing with data in OAI CSV form without person data.

        Trying: valid CSV
        Expecting: 0 NominaRecords are created
        """
        with self.admin_access.cnx() as cnx:
            filepath = self.csv_filepath("FRAD003_oai_no_person.csv")
            self.import_filepath(cnx, filepath, doctype="OAI")
            self.assertFalse(cnx.execute("Any X WHERE X is NominaRecord"))

    def test_esdocs_nominarecord(self):
        """Test OAI nomina standard importing.


        Trying: import 23 NominaRecords one of which is duplicated
        Expecting: ES documents are generated as expected
        """
        with self.admin_access.cnx() as cnx:
            filepath = self.csv_filepath("Landes_RM_normalise.csv")
            es_docs = self.import_filepath(cnx, filepath, doctype="RM")
            self.assertEqual(22, len(es_docs))
            stable_id = "d0d3c2e7cc1c96232f942996a593354891cc5fbb"
            es_doc = [doc for doc in es_docs if doc["_id"] == stable_id][0]
            nomina = cnx.find("NominaRecord", stable_id=stable_id).one()
            expected = {
                "_id": stable_id,
                "_index": "dummy_nomina",
                "_op_type": "index",
                "_source": {
                    "acte_type": "RM",
                    "alltext": "R P 392 domestique NMN_E_0 15 NMN_RM 1887 NMN_BN 1867 NMN_R",
                    "creation_date": nomina.creation_date,
                    "cw_etype": "NominaRecord",
                    "cwuri": f"http://testing.fr/cubicweb/basedenoms/{stable_id}",
                    "dates": {"gte": "1887", "lte": "1887"},
                    "eid": nomina.eid,
                    "forenames": ["Pierre"],
                    "names": ["Béton"],
                    "locations": [
                        "Canenx (Canenx-et-Réaut)",
                        "France",
                        "Landes",
                        "Mont-de-Marsan",
                    ],
                    "modification_date": nomina.creation_date,
                    "service": self.service.eid,
                    "stable_id": stable_id,
                    "authority": [],
                },
                "_type": "_doc",
            }
            self.assertEqual(expected, es_doc)

    def test_imported_nominarecord_indexation(self):
        """Test import nomina ES indexation.

        Trying: import NominaRecord
        Expecting: generated ES documents has same data as INominaIndexSerializable.serialize
        """
        with self.admin_access.cnx() as cnx:
            filepath = self.csv_filepath("Landes_RM_normalise.csv")
            es_docs = self.import_filepath(cnx, filepath, doctype="RM")
            self.assertEqual(22, len(es_docs))
            stable_id = "81035229fd3d8cfcdc443c955f28113c01da5f0d"
            es_doc = [doc for doc in es_docs if doc["_id"] == stable_id][0]["_source"]
            nomina = cnx.find("NominaRecord", stable_id=stable_id).one()
            es_json = nomina.cw_adapt_to("INominaIndexSerializable").serialize()
            for attr in ("creation_date", "modification_date"):
                # thoses value may be slightly different
                es_doc.pop(attr)
                es_json.pop(attr)
            self.assertEqual(es_json["dates"], None)
            self.assertDictEqual(es_doc, es_json)

    def test_reimported_nominarecord_indexation(self):
        """Test nomina standard importing.

        Trying: create a NominaRecord and link it to an Agent. Import NominaRecords
        Expecting: the linked authority is present in generated es_docs and
                   generated ES documents has same data as INominaIndexSerializable.serialize
        """
        with self.admin_access.cnx() as cnx:
            stable_id = "d0d3c2e7cc1c96232f942996a593354891cc5fbb"
            auth = cnx.create_entity("AgentAuthority", label="Pierre Béton")
            # create a NominaRecord that will be reimported later
            nomina = cnx.create_entity(
                "NominaRecord", service=self.service.eid, stable_id=stable_id, same_as=auth.eid
            )
            cnx.commit()
            self.assertEqual(nomina.stable_id, stable_id)
            self.assertEqual([a.eid for a in nomina.same_as], [auth.eid])
            filepath = self.csv_filepath("Landes_RM_normalise.csv")
            es_docs = self.import_filepath(cnx, filepath, doctype="RM")
            self.assertEqual(22, cnx.execute("Any COUNT(X) WHERE X is NominaRecord")[0][0])
            es_doc = [doc for doc in es_docs if doc["_id"] == stable_id][0]["_source"]
            # assert authority in es_document
            self.assertEqual(es_doc["authority"], [auth.eid])
            nomina = cnx.find("NominaRecord", stable_id=stable_id).one()
            es_json = nomina.cw_adapt_to("INominaIndexSerializable").serialize()
            for attr in ("creation_date", "modification_date"):
                # thoses value may be slightly different
                es_doc.pop(attr)
                es_json.pop(attr)
            self.assertDictEqual(es_doc, es_json)


if __name__ == "__main__":
    unittest.main()
