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
from mock import patch

import os.path as osp

import unittest

from cubicweb import Binary
from cubicweb.devtools import testlib

from cubicweb_francearchives.testutils import (PostgresTextMixin,
                                               EsSerializableMixIn)

from pgfixtures import setup_module, teardown_module as pg_teardown_module  # noqa

from esfixtures import teardown_module as es_teardown_module  # noqa


def teardown_module(module):
    pg_teardown_module(module)
    es_teardown_module(module)


class IFullTextIndexSerializableTC(EsSerializableMixIn, PostgresTextMixin,
                                   testlib.CubicWebTC):

    @patch('elasticsearch.client.indices.IndicesClient.exists')
    @patch('elasticsearch.client.Elasticsearch.index')
    def test_circular_file(self, index, exists):
        with self.admin_access.cnx() as cnx:
            with open(osp.join(self.datadir, 'pdf.pdf'), 'rb') as pdf:
                ce = cnx.create_entity
                attachment = ce('File',
                                data_name=u'pdf',
                                data_format=u'application/pdf',
                                data=Binary(pdf.read()))
                circular = ce('Circular',
                              circ_id=u'circ01', title=u'Circular',
                              status=u'in-effect',
                              attachment=attachment)
                cnx.commit()
                pdf_text = u'Test\nCirculaire chat\n\n\x0c'
                # pdf text is not indexed on File
                rset = cnx.execute('Any X ORDERBY FTIRANK(X) DESC '
                                   'WHERE X has_text %(q)s',
                                   {'q': pdf_text})
                self.assertEqual(rset.rows, [])
                rset = cnx.execute('Any X ORDERBY FTIRANK(X) DESC '
                                   'WHERE X has_text %(q)s',
                                   {'q': 'chat'})
                self.assertEqual(rset.rows, [])
                es_json = circular.cw_adapt_to(
                    'IFullTextIndexSerializable').serialize()
                self.assertEqual(pdf_text, es_json['attachment'])

    @patch('elasticsearch.client.indices.IndicesClient.exists')
    @patch('elasticsearch.client.Elasticsearch.index')
    def test_modify_circular_file(self, index, exists):
        """ tests RelationsUpdateIndexES is called on File"""
        with self.admin_access.cnx() as cnx:
            with open(osp.join(self.datadir, 'pdf.pdf'), 'rb') as pdf:
                ce = cnx.create_entity
                circular = ce('Circular',
                              circ_id=u'circ01', title=u'Circular',
                              status=u'in-effect')
                cnx.commit()
                es_json = circular.cw_adapt_to(
                    'IFullTextIndexSerializable').serialize()
                self.assertEqual(None, es_json.get('attachment'))
                attachement = ce('File',
                                 data_name=u'pdf',
                                 data_format=u'application/pdf',
                                 data=Binary(pdf.read()),
                                 reverse_attachment=circular)
                cnx.commit()
                pdf_text = u'Test\nCirculaire chat\n\n\x0c'
                circular = cnx.find('Circular', eid=circular.eid).one()
                es_json = circular.cw_adapt_to(
                    'IFullTextIndexSerializable').serialize()
                self.assertEqual(pdf_text, es_json['attachment'])
                es_json_file = attachement.cw_adapt_to(
                    'IFullTextIndexSerializable').serialize()
                self.assertEqual(pdf_text, es_json_file['attachment'])

    @patch('elasticsearch.client.indices.IndicesClient.exists')
    @patch('elasticsearch.client.Elasticsearch.index')
    def test_circular_attachment_indexed_as_circular(self, index, exists):
        """check circular attachments are indexed as circulars"""
        with self.admin_access.cnx() as cnx:
            with open(osp.join(self.datadir, 'pdf.pdf'), 'rb') as pdf:
                ce = cnx.create_entity
                attachment = ce(
                    'File',
                    data_name=u'pdf',
                    data_format=u'application/pdf',
                    data=Binary(pdf.read()))
                circular = ce(
                    'Circular',
                    circ_id=u'circ01',
                    title=u'Circular',
                    status=u'in-effect',
                    attachment=attachment)
                cnx.commit()
                circ_ift = circular.cw_adapt_to('IFullTextIndexSerializable')
                f_ift = attachment.cw_adapt_to('IFullTextIndexSerializable')
                self.assertEqual(f_ift.es_id, circular.eid)
                self.assertEqual(f_ift.es_doc_type, '_doc')
                self.assertEqual(f_ift.serialize(), circ_ift.serialize())

    @patch('elasticsearch.client.indices.IndicesClient.exists')
    @patch('elasticsearch.client.Elasticsearch.index')
    def test_circular_additional_attachment_indexed_as_circular(self, index, exists):
        """check circular additional attachments are indexed as circulars"""
        with self.admin_access.cnx() as cnx:
            with open(osp.join(self.datadir, 'pdf.pdf'), 'rb') as pdf:
                ce = cnx.create_entity
                attachment = ce(
                    'File',
                    data_name=u'pdf',
                    data_format=u'application/pdf',
                    data=Binary(pdf.read()))
                circular = ce(
                    'Circular',
                    circ_id=u'circ01',
                    title=u'Circular',
                    status=u'in-effect',
                    additional_attachment=attachment)
                cnx.commit()
                circ_ift = circular.cw_adapt_to('IFullTextIndexSerializable')
                f_ift = attachment.cw_adapt_to('IFullTextIndexSerializable')
                self.assertEqual(f_ift.es_id, circular.eid)
                self.assertEqual(f_ift.es_doc_type, '_doc')
                self.assertEqual(f_ift.serialize(), circ_ift.serialize())

    @patch('elasticsearch.client.indices.IndicesClient.exists')
    @patch('elasticsearch.client.Elasticsearch.index')
    def test_commemo_manif_prog(self, index, exists):
        """tests IFullTextIndexSerializable adaptors on CommemorationItem and

        its manif_prog BaseContent
        """
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            basecontent = ce('BaseContent', title=u'program',
                             content=u'31 juin')
            cnx.commit()
            es_json = basecontent.cw_adapt_to(
                'IFullTextIndexSerializable').serialize()
            self.assertEqual(u'31 juin', es_json['content'])
            # link the basecontent to a CommemorationItem
            commemo_item = ce('CommemorationItem', title=u'Commemoration',
                              alphatitle=u'commemoration',
                              content=u'content',
                              commemoration_year=1500,
                              manif_prog=basecontent,
                              collection_top=ce('CommemoCollection',
                                                title=u'Moyen Age',
                                                year=1500))
            cnx.commit()
            basecontent = cnx.find('BaseContent',
                                   eid=basecontent.eid).one()
            es_json_commemo = commemo_item.cw_adapt_to(
                'IFullTextIndexSerializable').serialize()
            self.assertEqual('31 juin', es_json_commemo['manif_prog'])
            es_json_bc = basecontent.cw_adapt_to(
                'IFullTextIndexSerializable').serialize()
            self.assertEqual(commemo_item.eid, es_json_bc['eid'])
            self.assertEqual('CommemorationItem', es_json_bc['cw_etype'])
            self.assertEqual(es_json_bc['content'], u'content')

            # update basecontent
            basecontent.cw_set(content=u'28 juin')
            cnx.commit()
            commemo_item = cnx.find('CommemorationItem',
                                    eid=commemo_item.eid).one()
            es_json_commemo = commemo_item.cw_adapt_to(
                'IFullTextIndexSerializable').serialize()
            self.assertEqual('28 juin', es_json_commemo['manif_prog'])
            basecontent = cnx.find('BaseContent',
                                   eid=basecontent.eid).one()
            es_json_bc = basecontent.cw_adapt_to(
                'IFullTextIndexSerializable').serialize()
            self.assertEqual('28 juin', es_json_bc['manif_prog'])

    @patch('elasticsearch.client.indices.IndicesClient.exists')
    @patch('elasticsearch.client.Elasticsearch.index')
    def test_is_a_publication(self, index, exists):
        """es_json['cw_etype'] of BaseContent which is a publication
           (in `publication` section) must be Publication
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                'Service', category=u'cat',
                name=u'Service', short_name=u's1')
            basecontent = cnx.create_entity(
                'BaseContent', title=u'program',
                content=u'31 juin',
                basecontent_service=service,
                reverse_children=cnx.create_entity(
                    'Section', title=u'Publication',
                    name=u'publication'))
            cnx.commit()
            es_json = basecontent.cw_adapt_to(
                'IFullTextIndexSerializable').serialize()
            self.assertEqual('Publication', es_json['cw_etype'])

    @patch('elasticsearch.client.indices.IndicesClient.exists')
    @patch('elasticsearch.client.Elasticsearch.index')
    def test_is_not_a_publication(self, index, exists):
        """es_json['cw_type'] of BaseContent which is not a publication
           (not in `publication` section) must be BaseContent
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                'Service', category=u'cat',
                name=u'Service', short_name=u's1')
            basecontent = cnx.create_entity(
                'BaseContent', title=u'program',
                content=u'31 juin',
                basecontent_service=service,
                reverse_children=cnx.create_entity(
                    'Section', title=u'Publication',
                    name=u'toto'))
            cnx.commit()
            es_json = basecontent.cw_adapt_to(
                'IFullTextIndexSerializable').serialize()
            self.assertEqual('BaseContent', es_json['cw_etype'])

    @patch('elasticsearch.client.indices.IndicesClient.exists')
    @patch('elasticsearch.client.Elasticsearch.index')
    def test_basecontent_without_manif_prog(self, index, exists):
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                'Service', category=u'cat',
                name=u'Service', short_name=u's1')
            basecontent = cnx.create_entity(
                'BaseContent', title=u'program',
                content=u'31 juin',
                basecontent_service=service)
            cnx.commit()
            es_json = basecontent.cw_adapt_to(
                'IFullTextIndexSerializable').serialize()
            self.assertEqual('edito', es_json['escategory'])
            self.assertEqual('31 juin', es_json['content'])
            self.assertEqual('program', es_json['title'])
            self.assertEqual(es_json['publisher'], [u's1'])

    @patch('elasticsearch.client.indices.IndicesClient.exists')
    @patch('elasticsearch.client.Elasticsearch.index')
    def test_basecontent_services(self, index, exists):
        with self.admin_access.cnx() as cnx:
            s1 = cnx.create_entity(
                'Service', category=u'cat',
                name=u'Service', short_name=u's1')
            s2 = cnx.create_entity(
                'Service', category=u'cat',
                name=u'Service', short_name=u's2')
            basecontent = cnx.create_entity(
                'BaseContent', title=u'program',
                content=u'31 juin',
                basecontent_service=[s1, s2])
            cnx.commit()
            es_json = basecontent.cw_adapt_to(
                'IFullTextIndexSerializable').serialize()
            self.assertEqual(es_json['publisher'], [u's1', u's2'])

    @patch('elasticsearch.client.indices.IndicesClient.exists')
    @patch('elasticsearch.client.Elasticsearch.index')
    def test_virtualexhibit(self, index, exists):
        with self.admin_access.cnx() as cnx:
            s1 = cnx.create_entity(
                'Service', category=u'cat',
                name=u'Service', short_name=u's1')
            s2 = cnx.create_entity(
                'Service', category=u'cat',
                name=u'Service', short_name=u's2')
            extref = cnx.create_entity('ExternRef',
                                       reftype=u'Virtual_exhibit',
                                       title=u'externref-title',
                                       url=u'http://toto',
                                       start_year=1982,
                                       exref_service=[s1, s2])
            es_json = extref.cw_adapt_to(
                'IFullTextIndexSerializable').serialize()
            self.assertEqual(es_json['reftype'], u'virtual_exhibit')
            self.assertEqual(es_json['cw_etype'], u'Virtual_exhibit')
            self.assertEqual(es_json['start_year'], 1982)
            self.assertEqual(es_json['escategory'], u'edito')
            self.assertEqual(es_json['publisher'], [u's1', u's2'])

    @patch('elasticsearch.client.indices.IndicesClient.exists')
    @patch('elasticsearch.client.Elasticsearch.index')
    def test_manif_prog_html_is_stripped(self, index, exists):
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            basecontent = ce('BaseContent', title=u'program',
                             content=u'Bonjour <em>Bourvil</em>')
            # link the basecontent to a CommemorationItem
            commemo_item = ce('CommemorationItem', title=u'Commemoration',
                              alphatitle=u'commemoration',
                              content=u'content',
                              commemoration_year=1500,
                              manif_prog=basecontent,
                              collection_top=ce('CommemoCollection',
                                                title=u'Moyen Age',
                                                year=1500))
            cnx.commit()
            es_json_commemo = commemo_item.cw_adapt_to(
                'IFullTextIndexSerializable').serialize()
            self.assertEqual(es_json_commemo['manif_prog'], 'Bonjour Bourvil')

    @patch('elasticsearch.client.indices.IndicesClient.exists')
    @patch('elasticsearch.client.Elasticsearch.index')
    def test_html_content_section(self, index, exists):
        with self.admin_access.cnx() as cnx:
            section = cnx.create_entity(
                'Section', title=u'section',
                content=u'<p><strong>content</strong></p>')
            cnx.commit()
            es_json = section.cw_adapt_to(
                'IFullTextIndexSerializable').serialize()
            self.assertEqual('content', es_json['content'])

    @patch('elasticsearch.client.indices.IndicesClient.exists')
    @patch('elasticsearch.client.Elasticsearch.index')
    def test_map_esdoc(self, index, exists):
        with self.admin_access.cnx() as cnx:
            s1 = cnx.create_entity('Section', title=u's1', name=u's1')
            s1_1 = cnx.create_entity('Section', title=u's1_1', name=u's1_1',
                                     reverse_children=s1)
            map1 = cnx.create_entity('Map', title=u'map1', map_file=Binary(''),
                                     reverse_children=s1_1)
            esdoc = map1.cw_adapt_to('IFullTextIndexSerializable').serialize()
            self.assertDictContainsSubset({
                'title': u'map1',
                'cw_etype': u'Map',
                'escategory': u'edito',
                'ancestors': [s1.eid, s1_1.eid],
            }, esdoc)
            self.assertNotIn('map_file', esdoc,
                             'map file content should not be indexed by ES')

    @patch('elasticsearch.client.indices.IndicesClient.exists')
    @patch('elasticsearch.client.Elasticsearch.index')
    def test_commemo_esdoc(self, index, exists):
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            commemo_item = ce('CommemorationItem', title=u'Commemoration',
                              alphatitle=u'commemoration',
                              subtitle=u'commemo-subtitle',
                              content=u'content',
                              commemoration_year=1500,
                              collection_top=ce('CommemoCollection',
                                                title=u'Moyen Age',
                                                year=1500))
            esdoc = commemo_item.cw_adapt_to('IFullTextIndexSerializable').serialize()
            self.assertDictContainsSubset({
                'title': u'Commemoration',
                'cw_etype': 'CommemorationItem',
                'escategory': u'commemorations',
                'subtitle': 'commemo-subtitle',
            }, esdoc)


class ISuggestIndexSerializableTC(EsSerializableMixIn, PostgresTextMixin,
                                  testlib.CubicWebTC):

    def create_findingaid(self, cnx, eadid):
        return cnx.create_entity(
            'FindingAid', name=eadid,
            stable_id=u'stable_id{}'.format(eadid),
            eadid=eadid,
            publisher=u'publisher',
            did=cnx.create_entity(
                'Did', unitid=u'unitid{}'.format(eadid),
                unittitle=u'title{}'.format(eadid)),
            fa_header=cnx.create_entity('FAHeader')
        )

    @patch('elasticsearch.client.indices.IndicesClient.exists')
    @patch('elasticsearch.client.Elasticsearch.index')
    def test_location_authority(self, index, exists):
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            loc1 = ce('LocationAuthority', label=u'location 1')
            fa1 = self.create_findingaid(cnx, u'eadid1')
            ce('Geogname',
               label=u'index location 1',
               index=fa1, authority=loc1)
            fa2 = self.create_findingaid(cnx, u'eadid2')
            ce('Geogname',
               label=u'index location 2',
               index=fa2, authority=loc1)
            cnx.commit()
            esdoc = loc1.cw_adapt_to('ISuggestIndexSerializable').serialize()
            expected = {
                'count': 2, 'cw_etype':
                u'LocationAuthority',
                'additional': '',
                'text': u'location 1',
                'urlpath': 'location/{}'.format(loc1.eid),
                'eid': loc1.eid, 'type': 'geogname'}
            self.assertDictContainsSubset(expected, esdoc)


if __name__ == '__main__':
    unittest.main()