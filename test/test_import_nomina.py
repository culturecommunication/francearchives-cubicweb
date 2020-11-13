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
import unittest
from lxml import etree
from itertools import chain
import io

from cubicweb.devtools.testlib import CubicWebTC
from cubicweb.dataimport.stores import RQLObjectStore

from cubicweb_francearchives.testutils import PostgresTextMixin
from cubicweb_francearchives.dataimport import oai, oai_nomina, create_ead_index_table


from pgfixtures import setup_module, teardown_module  # noqa


class NominaImportTC(PostgresTextMixin, CubicWebTC):
    def setUp(self):
        super(NominaImportTC, self).setUp()

    def test_import_persons(self):
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
            oai_nomina.build_persons(tree.getroot()),
            [
                {
                    "name": "MARGUERITAT",
                    "document_uri": "http://bla.org/6",
                    "death_year": None,
                    "dates_description": None,
                    "locations_description": None,
                    "forenames": "Jean Pierre",
                },
                {
                    "name": "PATUREAU",
                    "document_uri": "http://bla.org/6",
                    "death_year": None,
                    "dates_description": None,
                    "locations_description": None,
                    "forenames": "Roberte Marie Jacqueline",
                },
            ],
        )

    def test_import_dates(self):
        document = io.StringIO(
            """
<nomina:document xmlns:nomina="http://www.france-genealogie.fr/ns/nomina/1.0"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
xsi:schemaLocation="http://www.france-genealogie.fr/ns/nomina/1.0 genealogie1.4.xsd"
id="6" uri="">
    <nomina:personne>
     <nomina:nom>MARGUERITAT</nomina:nom>
     <nomina:prenoms>Jean</nomina:prenoms>
    </nomina:personne>
    <nomina:localisation code="RM">
     <nomina:precision/>
    </nomina:localisation>
    <nomina:date annee="1868" code="D">1868</nomina:date>
    <nomina:date annee="1880/12/11" code="M"/>
    <nomina:date>18?4</nomina:date>
    <nomina:date annee="1882">1882</nomina:date>
</nomina:document>
                                     """
        )
        tree = etree.parse(document)
        self.assertCountEqual(
            oai_nomina.build_dates(tree),
            (
                1868,
                '<ul><li class="M">1880/12/11</li><li class="">18?4</li><li class="">1882</li></ul>',  # noqa
            ),
        )

    def test_generate_extentities(self):
        documents = [
            io.StringIO(
                """
<metadata>
  <nomina:document xmlns:nomina="http://www.france-genealogie.fr/ns/nomina/1.0"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.france-genealogie.fr/ns/nomina/1.0 genealogie1.4.xsd"
  id="6" uri="http://bla.org/6">
      <nomina:personne>
       <nomina:nom>MARGUERITAT</nomina:nom>
       <nomina:prenoms>Jean</nomina:prenoms>
      </nomina:personne>
      <nomina:localisation code="N">
       <nomina:precision>Saint-Martin-d</nomina:precision>
       <nomina:departement>Cher</nomina:departement>
       <nomina:pays>France</nomina:pays>
      </nomina:localisation>
      <nomina:date code="N">18?4</nomina:date>
  </nomina:document>
</metadata>
            """
            ),
            io.StringIO(
                """
<metadata>
  <nomina:document xmlns:nomina="http://www.france-genealogie.fr/ns/nomina/1.0"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.france-genealogie.fr/ns/nomina/1.0 genealogie1.4.xsd"
  id="6" uri="">
      <nomina:personne>
       <nomina:nom>PATUREAU</nomina:nom>
       <nomina:prenoms>Roberte Marie Jacqueline</nomina:prenoms>
      </nomina:personne>
      <nomina:localisation code="RM">
       <nomina:precision/>
      </nomina:localisation>
      <nomina:date annee="1868" code="D">1868</nomina:date>
  </nomina:document>
</metadata>
            """
            ),
        ]
        reader = oai_nomina.OAINominaReader()
        extentities = []
        for doc in documents:
            extentities.extend(reader(etree.parse(doc).getroot()[0], {"name": "LE_SERVICE"}))
        self.assertEqual(len(extentities), 2)
        extentities = [(ee.etype, ee.extid, ee.values) for ee in extentities]
        self.assertCountEqual(
            extentities,
            [
                (
                    "Person",
                    1,
                    {
                        "name": {"MARGUERITAT"},
                        "forenames": {"Jean"},
                        "document_uri": {"http://bla.org/6"},
                        "publisher": {"LE_SERVICE"},
                        "locations_description": {
                            '<ul><li class="N">France, Cher, Saint-Martin-d</li></ul>'
                        },
                        "death_year": {None},
                        "dates_description": {'<ul><li class="N">18?4</li></ul>'},
                    },
                ),
                (
                    "Person",
                    2,
                    {
                        "name": {"PATUREAU"},
                        "forenames": {"Roberte Marie Jacqueline"},
                        "document_uri": {None},
                        "publisher": {"LE_SERVICE"},
                        "locations_description": {None},
                        "death_year": {1868},
                        "dates_description": {None},
                    },
                ),
            ],
        )

    def test_import_extentities(self):
        documents = [
            io.StringIO(
                """
<metadata>
  <nomina:document xmlns:nomina="http://www.france-genealogie.fr/ns/nomina/1.0"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.france-genealogie.fr/ns/nomina/1.0 genealogie1.4.xsd"
  id="6" uri="http://blabla.org/12">
  <nomina:personne>
   <nomina:nom>MARGUERITAT</nomina:nom>
   <nomina:prenoms>Jean</nomina:prenoms>
  </nomina:personne>
  <nomina:localisation code="RM">
   <nomina:precision/>
  </nomina:localisation>
  <nomina:date code="N">18?4</nomina:date>
  </nomina:document>
</metadata>
            """
            ),
            io.StringIO(
                """
<metadata>
  <nomina:document xmlns:nomina="http://www.france-genealogie.fr/ns/nomina/1.0"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.france-genealogie.fr/ns/nomina/1.0 genealogie1.4.xsd"
  id="6">
  <nomina:personne>
   <nomina:nom>PATUREAU</nomina:nom>
   <nomina:prenoms>Roberte Marie Jacqueline</nomina:prenoms>
  </nomina:personne>
  <nomina:localisation code="RM">
   <nomina:precision/>
  </nomina:localisation>
  <nomina:date annee="1868" code="D">1868</nomina:date>
  </nomina:document>
</metadata>
            """
            ),
        ]
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                ce = cnx.create_entity
                service = cnx.create_entity(
                    "Service", code="FRAD085", short_name="Dept du 85", category="test"
                )
                margueritat_authority = ce("AgentAuthority", label="margueritat jean")
                ce(
                    "Person",
                    name="Jean",
                    service=service,
                    publisher="FRAD085",
                    authority=margueritat_authority,
                )
                cnx.commit()
                store = RQLObjectStore(cnx)
                create_ead_index_table(cnx)
                reader = oai_nomina.OAINominaReader()
                service_infos = {
                    "name": "Dept du 85",
                    "code": "FRAD085",
                    "eid": service.eid,
                }
                entities = chain(
                    *(
                        reader(etree.parse(document).getroot()[0], service_infos)
                        for document in documents
                    )
                )
                oai.import_record_entities(
                    cnx,
                    entities,
                    store=store,
                    service_infos=service_infos,
                    index_policy={"autodedupe_authorities": "service/normalize"},
                )
                persons_rset = cnx.execute("Any P WHERE P is Person")
                self.assertEqual(len(persons_rset), 3)
                authorities = sorted(cnx.find("AgentAuthority").entities(), key=lambda e: e.eid)
                self.assertEqual(len(authorities), 2)
                # since Magueritat's authority was created first, patureau's one will have
                # a greater eid
                patureau_authority = authorities[1]
                persons = sorted(persons_rset.entities(), key=lambda e: e.eid)
                self.assertEqual(
                    [
                        (
                            p.name,
                            p.forenames,
                            p.death_year,
                            p.dates_description,
                            p.document_uri,
                            p.authority[0].eid,
                        )
                        for p in persons
                    ],
                    [
                        ("Jean", None, None, None, None, margueritat_authority.eid),
                        (
                            "MARGUERITAT",
                            "Jean",
                            None,
                            '<ul><li class="N">18?4</li></ul>',
                            "http://blabla.org/12",
                            margueritat_authority.eid,
                        ),
                        (
                            "PATUREAU",
                            "Roberte Marie Jacqueline",
                            1868,
                            None,
                            None,
                            patureau_authority.eid,
                        ),
                    ],
                )
                self.assertEqual(persons[1].service[0].eid, service.eid)
                self.assertEqual(persons[1].publisher, "Dept du 85")

    @unittest.skip("coucou")
    def test_import_arkotheque_url(self):
        # XXX TODO: write a web test
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                store = RQLObjectStore(cnx)
                url = (
                    "http://www.archives28.fr/arkotheque/oai-pmh-2/oai2.php?"
                    "from=2015-10-01T14:15:00Z&set=ad28_registres_matricules"
                    "&verb=ListRecords&metadataPrefix=nomina"
                )
                oai.import_oai(cnx, url, store=store)


if __name__ == "__main__":
    unittest.main()
