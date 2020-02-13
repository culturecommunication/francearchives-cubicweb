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
import json

from cubicweb.devtools import testlib

from cubicweb_francearchives.entities import entity2schemaorg

from cubicweb_francearchives.testutils import PostgresTextMixin
from pgfixtures import setup_module, teardown_module  # noqa


class SchemaOrgFindingAidTests(PostgresTextMixin, testlib.CubicWebTC):
    def setup_database(self):
        with self.admin_access.cnx() as cnx:
            fadid = cnx.create_entity("Did", unitid="maindid", unittitle="maindid-title")
            fcdid = cnx.create_entity(
                "Did",
                unitid="fcdid",
                unittitle="fcdid-title",
                startyear=1234,
                stopyear=1245,
                origination="fc-origination",
                repository="fc-repo",
            )
            fa = cnx.create_entity(
                "FindingAid",
                name="the-fa",
                stable_id="FRAD084_xxx",
                eadid="FRAD084_xxx",
                publisher="FRAD084",
                did=fadid,
                fa_header=cnx.create_entity("FAHeader"),
            )
            facomp = cnx.create_entity(
                "FAComponent",
                finding_aid=fa,
                stable_id="fc-stable-id",
                did=fcdid,
                scopecontent="fc-scoppecontent",
                description="fc-descr",
            )
            cnx.create_entity(
                "Subject",
                role="indextest",
                label="Paris",
                authority=cnx.create_entity(
                    "SubjectAuthority",
                    label="Paris",
                    same_as=cnx.create_entity(
                        "ExternalUri", uri="https://fr.wikipedia.org/wiki/Paris"
                    ),
                ),
                index=fa,
            )
            cnx.create_entity(
                "AgentName",
                role="indextest",
                authority=cnx.create_entity(
                    "AgentAuthority",
                    label="Jérôme Savonarole",
                    reverse_authority=cnx.create_entity(
                        "Person", name="Savonarole", forenames="Jérôme", publisher="nomina"
                    ),
                ),
                index=facomp,
            )
            cnx.commit()
            self.fa_eid = fa.eid
            self.facomp_eid = facomp.eid

    def test_facomponent(self):
        with self.admin_access.cnx() as cnx:
            fa = cnx.entity_from_eid(self.fa_eid)
            facomp = cnx.entity_from_eid(self.facomp_eid)
            graph = entity2schemaorg(facomp)
            self.assertDictEqual(
                json.loads(graph.decode("utf-8")),
                {
                    "@context": {
                        "crm": "http://www.cidoc-crm.org/rdfs/cidoc_crm_v5.0.2_english_label.rdfs#",
                        "edm": "http://www.europeana.eu/schemas/edm/",
                        "ore": "http://www.openarchives.org/ore/terms/",
                        "rdaGr2": "http://rdvocab.info/ElementsGr2",
                        "dcmitype": "http://purl.org/dc/dcmitype/",
                        "dcterms": "http://purl.org/dc/terms/",
                        "foaf": "http://xmlns.com/foaf/0.1/",
                        "owl": "http://www.w3.org/2002/07/owl#",
                        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
                        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
                        "schema": "http://schema.org/",
                        "skos": "http://www.w3.org/2004/02/skos/core#",
                    },
                    "@id": facomp.absolute_url(),
                    "@type": "schema:CreativeWork",
                    "schema:contentLocation": "fc-origination",
                    "schema:mentions": "fc-scoppecontent",
                    "schema:name": "fcdid-title",
                    "schema:isPartof": {"@id": fa.absolute_url(),},
                },
            )

    def test_findingaid(self):
        with self.admin_access.cnx() as cnx:
            fa = cnx.entity_from_eid(self.fa_eid)
            facomp = cnx.entity_from_eid(self.facomp_eid)
            authority = cnx.find("SubjectAuthority", label="Paris").one()
            exturl = cnx.find("ExternalUri", uri="https://fr.wikipedia.org/wiki/Paris").one()
            graph = json.loads(entity2schemaorg(fa).decode("utf-8"))["@graph"]
            self.assertCountEqual(
                graph,
                [
                    {"@id": authority.absolute_url(), "schema:sameAs": exturl.uri,},
                    {
                        "@id": fa.absolute_url(),
                        "@type": "schema:CreativeWork",
                        "schema:about": authority.absolute_url(),
                        "schema:name": "maindid-title",
                        "schema:hasPart": {"@id": facomp.absolute_url(),},
                    },
                ],
            )


class SchemaOrgTests(testlib.CubicWebTC):
    def test_service(self):
        with self.admin_access.cnx() as cnx:
            s1 = cnx.create_entity(
                "Service",
                category="?1",
                name="s1",
                phone_number="s1-phone",
                fax="s1-fax",
                email="s1-email",
                address="s1-address",
                mailing_address="s1-maddress",
                zip_code="75",
                city="Paris",
                website_url="http://www.s1.fr",
                opening_period="op-period",
                contact_name="jean michel",
            )
            s2 = cnx.create_entity(
                "Service",
                category="?2",
                name="s2",
                phone_number="s2-phone",
                city="Paris",
                website_url="http://www.s2.fr",
                opening_period="op-period2",
                contact_name="jean paul",
                annex_of=s1,
            )
            graph = json.loads(entity2schemaorg(s1).decode("utf-8"))["@graph"]
            # make sure organisation item comes first
            graph = sorted(graph, key=lambda item: not item.get("@type") == "schema:Organization")
            # can't predict blank node hash strings, just make sure
            # that the same id is used to specify the "address" property
            self.assertEqual(graph[0]["schema:address"]["@id"], graph[1]["@id"])
            graph[0]["schema:address"]["@id"] = graph[1]["@id"] = "the-address"
            self.assertEqual(
                graph,
                [
                    {
                        "@id": s1.absolute_url(),
                        "@type": "schema:Organization",
                        "schema:address": {"@id": "the-address"},
                        "schema:email": "s1-email",
                        "schema:employee": "jean michel",
                        "schema:faxNumber": "s1-fax",
                        "schema:legalName": "s1",
                        "schema:openinghours": "op-period",
                        "schema:subOrganization": {"@id": s2.absolute_url()},
                        "schema:telephone": "s1-phone",
                    },
                    {
                        "@id": "the-address",
                        "schema:addressCountry": "fr",
                        "schema:addressLocality": "Paris",
                        "schema:postalCode": "75",
                        "schema:streetAddress": "s1-address",
                        "schema:type": {"@id": "schema:PostalAddress"},
                    },
                ],
            )


class SchemaOrgBaseContentTests(testlib.CubicWebTC):
    def test_base_content(self):
        base_content_data = {
            "title": "the-title",
            "keywords": "the-keywords",
            "content": "the-content",
            "content_format": "text/plain",
            "creation_date": "1970-01-01",
            "modification_date": "2000-01-01",
            "description": "the-description",
            "order": 1,
            "uuid": "the-uuid",
        }

        metadata_data = {"creator": "toto"}

        with self.admin_access.cnx() as cnx:
            metadata = cnx.create_entity("Metadata", **metadata_data)
            entity = cnx.create_entity("BaseContent", metadata=metadata, **base_content_data)

            cnx.commit()
            entity.cw_clear_all_caches()

            graph = entity2schemaorg(entity)
            data = json.loads(graph.decode("utf-8"))

            # Attributes that should be set
            self.assertEqual(data["@context"]["schema"], "http://schema.org/")
            self.assertEqual(data["@type"], "schema:Article")
            self.assertEqual(data["@id"], entity.absolute_url())
            self.assertEqual(data["schema:url"], entity.absolute_url())
            self.assertEqual(data["schema:name"], base_content_data["title"])
            self.assertEqual(data["schema:dateCreated"], base_content_data["creation_date"])
            self.assertEqual(data["schema:datePublished"], base_content_data["creation_date"])
            self.assertEqual(data["schema:dateModified"], base_content_data["modification_date"])
            self.assertEqual(data["schema:keywords"], base_content_data["keywords"])
            self.assertEqual(data["schema:inLanguage"], "FR")
            self.assertEqual(data["schema:author"], metadata_data["creator"])

            # Attributes that should not be set
            self.assertNotIn("schema:articleBody", data)


class SchemaOrgNewsContentTests(testlib.CubicWebTC):
    def test_news_content(self):
        news_content_data = {
            "title": "the-title",
            "content": "the-content",
            "content_format": "text/plain",
            "creation_date": "1970-01-01",
            "modification_date": "2000-01-01",
            "order": 1,
            "uuid": "the-uuid",
            "start_date": "2017-03-10",
        }

        metadata_data = {"creator": "toto"}

        with self.admin_access.cnx() as cnx:
            metadata = cnx.create_entity("Metadata", **metadata_data)
            entity = cnx.create_entity("NewsContent", metadata=metadata, **news_content_data)
            cnx.commit()
            entity.cw_clear_all_caches()

            graph = entity2schemaorg(entity)
            data = json.loads(graph.decode("utf-8"))

            # Attributes that should be set
            self.assertEqual(data["@context"]["schema"], "http://schema.org/")
            self.assertEqual(data["@type"], "schema:Article")
            self.assertEqual(data["@id"], entity.absolute_url())
            self.assertEqual(data["schema:url"], entity.absolute_url())
            self.assertEqual(data["schema:name"], news_content_data["title"])
            self.assertEqual(data["schema:dateCreated"], news_content_data["creation_date"])
            self.assertEqual(data["schema:datePublished"], news_content_data["start_date"])
            self.assertEqual(data["schema:dateModified"], news_content_data["modification_date"])
            self.assertEqual(data["schema:inLanguage"], "FR")
            self.assertEqual(data["schema:author"], metadata_data["creator"])

            # Attributes that should not be set
            self.assertNotIn("schema:articleBody", data)
            self.assertNotIn("schema:keywords", data)


class SchemaOrgCommemorationItemTests(testlib.CubicWebTC):
    def test_commemoration_item(self):
        commemoration_item_data = {
            "title": "the-title",
            "content": "the-content",
            "content_format": "text/plain",
            "order": 1,
            "uuid": "the-uuid",
            "subtitle": "the-subtitle",
            "alphatitle": "the-alphatitle",
            "year": "1980",
            "commemoration_year": "2080",
            "on_homepage": True,
            "creation_date": "1970-01-01",
            "modification_date": "2000-01-01",
        }

        metadata_data = {"creator": "toto"}

        with self.admin_access.cnx() as cnx:
            metadata = cnx.create_entity("Metadata", **metadata_data)

            commemoration = cnx.create_entity(
                "CommemoCollection",
                year=commemoration_item_data["year"],
                title=commemoration_item_data["year"],
            )

            entity = cnx.create_entity(
                "CommemorationItem",
                metadata=metadata,
                collection_top=commemoration.eid,
                **commemoration_item_data
            )
            cnx.commit()
            entity.cw_clear_all_caches()

            graph = entity2schemaorg(entity)
            data = json.loads(graph.decode("utf-8"))

            # Attributes that should be set
            self.assertEqual(data["@context"]["schema"], "http://schema.org/")
            self.assertTrue("@graph" in data)

            event = self._get_event(data)

            self.assertEqual(event["@type"], "schema:Event")
            self.assertEqual(event["@id"], entity.absolute_url())
            self.assertEqual(event["schema:url"], entity.absolute_url())
            self.assertEqual(event["schema:name"], commemoration_item_data["title"])
            self.assertEqual(
                event["schema:datePublished"], commemoration_item_data["creation_date"]
            )
            self.assertEqual(event["schema:inLanguage"], "FR")
            self.assertEqual(event["schema:author"], metadata_data["creator"])

            super_event = self._get_super_event(data)

            self.assertEqual(super_event["schema:url"], commemoration.absolute_url())

    def _get_event(self, data):
        for event in data["@graph"]:
            if "@type" in event:
                return event
        raise Exception("No event in data")

    def _get_super_event(self, data):
        for event in data["@graph"]:
            if "schema:type" in event:
                return event
        raise Exception("No supEvent in data")


class SchemaOrgCommemoCollectionTests(testlib.CubicWebTC):
    def test_commemo_collection(self):
        nb_sub_events = 10

        commemo_collection_data = {
            "title": "the-title",
            "content": "the-content",
            "content_format": "text/plain",
            "order": 1,
            "uuid": "the-uuid",
            "subtitle": "the-subtitle",
            "name": "name",
            "short_description": "the-short-description",
            "year": "1980",
            "creation_date": "1970-01-01",
            "modification_date": "2000-01-01",
        }

        metadata_data = {"creator": "toto"}

        with self.admin_access.cnx() as cnx:
            metadata = cnx.create_entity("Metadata", **metadata_data)

            entity = cnx.create_entity(
                "CommemoCollection", metadata=metadata, **commemo_collection_data
            )

            for i in range(nb_sub_events):
                cnx.create_entity(
                    "CommemorationItem",
                    commemoration_year="2000",
                    title="title-{}".format(i),
                    alphatitle="alphatitle-{}".format(i),
                    collection_top=entity.eid,
                )
            cnx.commit()
            entity.cw_clear_all_caches()

            graph = entity2schemaorg(entity)
            data = json.loads(graph.decode("utf-8"))

            # Attributes that should be set
            self.assertEqual(data["@context"]["schema"], "http://schema.org/")
            self.assertTrue("@graph" in data)

            event = self._get_event(data)

            self.assertEqual(event["@type"], "schema:Event")
            self.assertEqual(event["@id"], entity.absolute_url())
            self.assertEqual(event["schema:url"], entity.absolute_url())
            self.assertEqual(event["schema:name"], commemo_collection_data["title"])
            self.assertEqual(
                event["schema:datePublished"], commemo_collection_data["creation_date"]
            )
            self.assertEqual(event["schema:inLanguage"], "FR")
            self.assertEqual(event["schema:author"], metadata_data["creator"])

            sub_events = self._get_sub_events(data)

            self.assertEqual(len(sub_events), nb_sub_events)
            for sub_event in sub_events:
                self.assertTrue(self._graph_contains_id(data["@graph"], sub_event["@id"]))

    def _get_event(self, data):
        for event in data["@graph"]:
            if "@type" in event:
                return event
        raise Exception("No event in data")

    def _get_sub_events(self, data):
        events = []
        for event in data["@graph"]:
            if "schema:type" in event:
                events.append(event)
        return events

    def _graph_contains_id(self, graph, id):
        for node in graph:
            if "@id" not in node:
                continue
            if node["@id"] == id:
                return True
        return False


if __name__ == "__main__":
    unittest.main()
