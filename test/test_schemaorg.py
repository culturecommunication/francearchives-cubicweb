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
            fadid = cnx.create_entity('Did', unitid=u'maindid',
                                      unittitle=u'maindid-title')
            fcdid = cnx.create_entity('Did', unitid=u'fcdid',
                                      unittitle=u'fcdid-title',
                                      startyear=1234,
                                      stopyear=1245,
                                      origination=u'fc-origination',
                                      repository=u'fc-repo')
            fa = cnx.create_entity('FindingAid', name=u'the-fa',
                                   stable_id=u'FRAD084_xxx',
                                   eadid=u'FRAD084_xxx',
                                   publisher=u'FRAD084',
                                   did=fadid,
                                   fa_header=cnx.create_entity('FAHeader'))
            facomp = cnx.create_entity('FAComponent',
                                       finding_aid=fa,
                                       stable_id=u'fc-stable-id',
                                       did=fcdid,
                                       scopecontent=u'fc-scoppecontent',
                                       description=u'fc-descr')
            cnx.create_entity(
                'Subject',
                role=u'indextest',
                label=u'Paris',
                authority=cnx.create_entity(
                    'SubjectAuthority',
                    label=u'Paris',
                    same_as=cnx.create_entity('ExternalUri',
                                              uri=u'https://fr.wikipedia.org/wiki/Paris')),
                index=fa)
            cnx.create_entity(
                'AgentName',
                role=u'indextest',
                authority=cnx.create_entity(
                    'AgentAuthority',
                    label=u'Jérôme Savonarole',
                    reverse_authority=cnx.create_entity(
                        'Person', name=u'Savonarole',
                        forenames=u'Jérôme',
                        publisher=u'nomina')),
                index=facomp)
            cnx.commit()
            self.fa_eid = fa.eid
            self.facomp_eid = facomp.eid

    def test_facomponent(self):
        with self.admin_access.cnx() as cnx:
            fa = cnx.entity_from_eid(self.fa_eid)
            facomp = cnx.entity_from_eid(self.facomp_eid)
            graph = entity2schemaorg(facomp)
            self.assertDictEqual(json.loads(graph), {
                u'@context': {
                    u'crm': u'http://www.cidoc-crm.org/rdfs/cidoc_crm_v5.0.2_english_label.rdfs#',
                    u'edm': u'http://www.europeana.eu/schemas/edm/',
                    u'ore': u'http://www.openarchives.org/ore/terms/',
                    u'rdaGr2': u'http://rdvocab.info/ElementsGr2',
                    u'dcmitype': u'http://purl.org/dc/dcmitype/',
                    u'dcterms': u'http://purl.org/dc/terms/',
                    u'foaf': u'http://xmlns.com/foaf/0.1/',
                    u'owl': u'http://www.w3.org/2002/07/owl#',
                    u'rdf': u'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
                    u'rdfs': u'http://www.w3.org/2000/01/rdf-schema#',
                    u'schema': u'http://schema.org/',
                    u'skos': u'http://www.w3.org/2004/02/skos/core#',
                },
                u'@id': facomp.absolute_url(),
                u'@type': u'schema:CreativeWork',
                u'schema:contentLocation': u'fc-origination',
                u'schema:mentions': u'fc-scoppecontent',
                u'schema:name': u'fcdid-title',
                u'schema:isPartof': {
                    u'@id': fa.absolute_url(),
                }
            })

    def test_findingaid(self):
        with self.admin_access.cnx() as cnx:
            fa = cnx.entity_from_eid(self.fa_eid)
            facomp = cnx.entity_from_eid(self.facomp_eid)
            authority = cnx.find('SubjectAuthority', label=u'Paris').one()
            exturl = cnx.find('ExternalUri',
                              uri=u'https://fr.wikipedia.org/wiki/Paris').one()
            graph = json.loads(entity2schemaorg(fa))['@graph']
            self.assertCountEqual(graph, [
                {
                    u'@id': authority.absolute_url(),
                    u'schema:sameAs': exturl.uri,
                },
                {
                    u'@id': fa.absolute_url(),
                    u'@type': u'schema:CreativeWork',
                    u'schema:about': authority.absolute_url(),
                    u'schema:name': u'maindid-title',
                    u'schema:hasPart': {
                        u'@id': facomp.absolute_url(),
                    }
                }])


class SchemaOrgTests(testlib.CubicWebTC):

    def test_service(self):
        with self.admin_access.cnx() as cnx:
            s1 = cnx.create_entity('Service',
                                   category=u'?1',
                                   name=u's1',
                                   phone_number=u's1-phone',
                                   fax=u's1-fax',
                                   email=u's1-email',
                                   address=u's1-address',
                                   mailing_address=u's1-maddress',
                                   zip_code=u'75',
                                   city=u'Paris',
                                   website_url=u'http://www.s1.fr',
                                   opening_period=u'op-period',
                                   contact_name=u'jean michel')
            s2 = cnx.create_entity('Service',
                                   category=u'?2',
                                   name=u's2',
                                   phone_number=u's2-phone',
                                   city=u'Paris',
                                   website_url=u'http://www.s2.fr',
                                   opening_period=u'op-period2',
                                   contact_name=u'jean paul',
                                   annex_of=s1)
            graph = json.loads(entity2schemaorg(s1))['@graph']
            # make sure organisation item comes first
            graph = sorted(graph,
                           key=lambda item: not item.get('@type') == 'schema:Organization')
            # can't predict blank node hash strings, just make sure
            # that the same id is used to specify the "address" property
            self.assertEqual(graph[0]['schema:address']['@id'], graph[1]['@id'])
            graph[0]['schema:address']['@id'] = graph[1]['@id'] = u'the-address'
            self.assertEqual(graph, [
                {
                    u'@id': s1.absolute_url(),
                    u'@type': u'schema:Organization',
                    u'schema:address': {u'@id': u'the-address'},
                    u'schema:email': u's1-email',
                    u'schema:employee': u'jean michel',
                    u'schema:faxNumber': u's1-fax',
                    u'schema:legalName': u's1',
                    u'schema:openinghours': u'op-period',
                    u'schema:subOrganization': {u'@id': s2.absolute_url()},
                    u'schema:telephone': u's1-phone',
                }, {
                    u'@id': u'the-address',
                    u'schema:addressCountry': u'fr',
                    u'schema:addressLocality': u'Paris',
                    u'schema:postalCode': u'75',
                    u'schema:streetAddress': u's1-address',
                    u'schema:type': {u'@id': u'schema:PostalAddress'},
                }])


class SchemaOrgBaseContentTests(testlib.CubicWebTC):

    def test_base_content(self):
        base_content_data = {
            'title': u'the-title',
            'keywords': u'the-keywords',
            'content': u'the-content',
            'content_format': u'text/plain',
            'creation_date': u'1970-01-01',
            'modification_date': u'2000-01-01',
            'description': u'the-description',
            'order': 1,
            'uuid': u'the-uuid',
        }

        metadata_data = {
            'creator': u'toto'
        }

        with self.admin_access.cnx() as cnx:
            metadata = cnx.create_entity('Metadata', **metadata_data)
            entity = cnx.create_entity('BaseContent',
                                       metadata=metadata,
                                       **base_content_data)

            cnx.commit()
            entity.cw_clear_all_caches()

            graph = entity2schemaorg(entity)
            data = json.loads(graph)

            # Attributes that should be set
            self.assertEqual(data[u'@context'][u'schema'], u'http://schema.org/')
            self.assertEqual(data[u'@type'], u'schema:Article')
            self.assertEqual(data[u'@id'], entity.absolute_url())
            self.assertEqual(data[u'schema:url'], entity.absolute_url())
            self.assertEqual(data[u'schema:name'], base_content_data['title'])
            self.assertEqual(data[u'schema:dateCreated'], base_content_data['creation_date'])
            self.assertEqual(data[u'schema:datePublished'], base_content_data['creation_date'])
            self.assertEqual(data[u'schema:dateModified'], base_content_data['modification_date'])
            self.assertEqual(data[u'schema:keywords'], base_content_data['keywords'])
            self.assertEqual(data[u'schema:inLanguage'], "FR")
            self.assertEqual(data[u'schema:author'], metadata_data['creator'])

            # Attributes that should not be set
            self.assertNotIn(u'schema:articleBody', data)


class SchemaOrgNewsContentTests(testlib.CubicWebTC):

    def test_news_content(self):
        news_content_data = {
            'title': u'the-title',
            'content': u'the-content',
            'content_format': u'text/plain',
            'creation_date': u'1970-01-01',
            'modification_date': u'2000-01-01',
            'order': 1,
            'uuid': u'the-uuid',
            'start_date': u'2017-03-10',
        }

        metadata_data = {
            'creator': u'toto'
        }

        with self.admin_access.cnx() as cnx:
            metadata = cnx.create_entity('Metadata', **metadata_data)
            entity = cnx.create_entity('NewsContent',
                                       metadata=metadata,
                                       **news_content_data)
            cnx.commit()
            entity.cw_clear_all_caches()

            graph = entity2schemaorg(entity)
            data = json.loads(graph)

            # Attributes that should be set
            self.assertEqual(data[u'@context'][u'schema'], u'http://schema.org/')
            self.assertEqual(data[u'@type'], u'schema:Article')
            self.assertEqual(data[u'@id'], entity.absolute_url())
            self.assertEqual(data[u'schema:url'], entity.absolute_url())
            self.assertEqual(data[u'schema:name'], news_content_data['title'])
            self.assertEqual(data[u'schema:dateCreated'], news_content_data['creation_date'])
            self.assertEqual(data[u'schema:datePublished'], news_content_data['start_date'])
            self.assertEqual(data[u'schema:dateModified'], news_content_data['modification_date'])
            self.assertEqual(data[u'schema:inLanguage'], "FR")
            self.assertEqual(data[u'schema:author'], metadata_data['creator'])

            # Attributes that should not be set
            self.assertNotIn(u'schema:articleBody', data)
            self.assertNotIn(u'schema:keywords', data)


class SchemaOrgCommemorationItemTests(testlib.CubicWebTC):

    def test_commemoration_item(self):
        commemoration_item_data = {
            'title': u'the-title',
            'content': u'the-content',
            'content_format': u'text/plain',
            'order': 1,
            'uuid': u'the-uuid',
            'subtitle': u'the-subtitle',
            'alphatitle': u'the-alphatitle',
            'year': u'1980',
            'commemoration_year': u'2080',
            'on_homepage': True,
            'creation_date': u'1970-01-01',
            'modification_date': u'2000-01-01',
        }

        metadata_data = {
            'creator': u'toto'
        }

        with self.admin_access.cnx() as cnx:
            metadata = cnx.create_entity('Metadata', **metadata_data)

            commemoration = cnx.create_entity('CommemoCollection',
                                              year=commemoration_item_data['year'],
                                              title=commemoration_item_data['year'])

            entity = cnx.create_entity('CommemorationItem',
                                       metadata=metadata,
                                       collection_top=commemoration.eid,
                                       **commemoration_item_data)
            cnx.commit()
            entity.cw_clear_all_caches()

            graph = entity2schemaorg(entity)
            data = json.loads(graph)

            # Attributes that should be set
            self.assertEqual(data[u'@context'][u'schema'], u'http://schema.org/')
            self.assertTrue(u'@graph' in data)

            event = self._get_event(data)

            self.assertEqual(event[u'@type'], u'schema:Event')
            self.assertEqual(event[u'@id'], entity.absolute_url())
            self.assertEqual(event[u'schema:url'], entity.absolute_url())
            self.assertEqual(event[u'schema:name'],
                             commemoration_item_data['title'])
            self.assertEqual(event[u'schema:datePublished'],
                             commemoration_item_data['creation_date'])
            self.assertEqual(event[u'schema:inLanguage'], 'FR')
            self.assertEqual(event[u'schema:author'], metadata_data['creator'])

            super_event = self._get_super_event(data)

            self.assertEqual(super_event[u'schema:url'],
                             commemoration.absolute_url())

    def _get_event(self, data):
        for event in data[u'@graph']:
            if u'@type' in event:
                return event
        raise Exception('No event in data')

    def _get_super_event(self, data):
        for event in data[u'@graph']:
            if u'schema:type' in event:
                return event
        raise Exception('No supEvent in data')


class SchemaOrgCommemoCollectionTests(testlib.CubicWebTC):

    def test_commemo_collection(self):
        nb_sub_events = 10

        commemo_collection_data = {
            'title': u'the-title',
            'content': u'the-content',
            'content_format': u'text/plain',
            'order': 1,
            'uuid': u'the-uuid',
            'subtitle': u'the-subtitle',
            'name': u'name',
            'short_description': u'the-short-description',
            'year': u'1980',
            'creation_date': u'1970-01-01',
            'modification_date': u'2000-01-01',
        }

        metadata_data = {
            'creator': u'toto'
        }

        with self.admin_access.cnx() as cnx:
            metadata = cnx.create_entity('Metadata', **metadata_data)

            entity = cnx.create_entity('CommemoCollection',
                                       metadata=metadata,
                                       **commemo_collection_data)

            for i in range(nb_sub_events):
                cnx.create_entity('CommemorationItem',
                                  commemoration_year=u'2000',
                                  title=u'title-{}'.format(i),
                                  alphatitle=u'alphatitle-{}'.format(i),
                                  collection_top=entity.eid)
            cnx.commit()
            entity.cw_clear_all_caches()

            graph = entity2schemaorg(entity)
            data = json.loads(graph)

            # Attributes that should be set
            self.assertEqual(data[u'@context'][u'schema'], u'http://schema.org/')
            self.assertTrue(u'@graph' in data)

            event = self._get_event(data)

            self.assertEqual(event[u'@type'], u'schema:Event')
            self.assertEqual(event[u'@id'], entity.absolute_url())
            self.assertEqual(event[u'schema:url'], entity.absolute_url())
            self.assertEqual(event[u'schema:name'],
                             commemo_collection_data['title'])
            self.assertEqual(event[u'schema:datePublished'],
                             commemo_collection_data['creation_date'])
            self.assertEqual(event[u'schema:inLanguage'], 'FR')
            self.assertEqual(event[u'schema:author'], metadata_data['creator'])

            sub_events = self._get_sub_events(data)

            self.assertEqual(len(sub_events), nb_sub_events)
            for sub_event in sub_events:
                self.assertTrue(self._graph_contains_id(data[u'@graph'],
                                                        sub_event[u'@id']))

    def _get_event(self, data):
        for event in data[u'@graph']:
            if u'@type' in event:
                return event
        raise Exception('No event in data')

    def _get_sub_events(self, data):
        events = []
        for event in data[u'@graph']:
            if u'schema:type' in event:
                events.append(event)
        return events

    def _graph_contains_id(self, graph, id):
        for node in graph:
            if u'@id' not in node:
                continue
            if node[u'@id'] == id:
                return True
        return False


if __name__ == '__main__':
    unittest.main()
