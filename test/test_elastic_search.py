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
from __future__ import print_function

import os.path as osp

import sys

import datetime as dt
import unittest
from io import StringIO

from mock import patch

from cubicweb import Binary
from cubicweb.devtools.testlib import CubicWebTC

from cubicweb_francearchives import ccplugin
from cubicweb_francearchives.testutils import EsSerializableMixIn

from esfixtures import teardown_module  # noqa


class ElasticSearchTC(EsSerializableMixIn, CubicWebTC):

    def create_indexable_entries(self, cnx):
        ce = cnx.create_entity
        ce('PniaAgent', type=u'persname', label=u'Charles de Gaulles')
        ce('PniaAgent', type=u'persname', label=u'Charles Chaplin')
        cnx.commit()

    @patch('elasticsearch.client.Elasticsearch.index', unsafe=True)
    @patch('elasticsearch.client.Elasticsearch.bulk', unsafe=True)
    @patch('elasticsearch.client.indices.IndicesClient.exists', unsafe=True)
    @patch('elasticsearch.client.indices.IndicesClient.create', unsafe=True)
    def test_ccplugin(self, create, exists, bulk, index):
        self.skipTest('reimplement me')
        with self.admin_access.cnx() as cnx:
            cnx.disable_hook_categories('es')
            with cnx.allow_all_hooks_but('es'):
                self.create_indexable_entries(cnx)
        bulk.reset_mock()
        cmd = [self.appid, '--dry-run', 'yes']
        sys.stdout = out = StringIO()
        try:
            ccplugin.IndexESAutocomplete(None).main_run(cmd)
        finally:
            sys.stdout = sys.__stdout__
        self.assertEquals('', out.getvalue())
        create.assert_not_called()
        bulk.assert_not_called()

        cmd = [self.appid]
        sys.stdout = StringIO()
        try:
            ccplugin.IndexESAutocomplete(None).main_run(cmd)
        finally:
            sys.stdout = sys.__stdout__
        with self.admin_access.cnx() as cnx:
            self.assert_(cnx.execute('Any X WHERE X is PniaAgent'))
        bulk.assert_called()

    @patch('elasticsearch.client.indices.IndicesClient.create', unsafe=True)
    @patch('elasticsearch.client.indices.IndicesClient.exists', unsafe=True)
    @patch('elasticsearch.client.Elasticsearch.index', unsafe=True)
    def test_es_hooks_modify(self, index, exists, create):
        with self.admin_access.cnx() as cnx:
            entity = cnx.create_entity('BaseContent', title=u'the-title')
            cnx.commit()
            index.reset_mock()
            entity.cw_set(title=u'Different title')
            cnx.commit()
            index.assert_called()

    @patch('elasticsearch.client.indices.IndicesClient.create', unsafe=True)
    @patch('elasticsearch.client.indices.IndicesClient.exists', unsafe=True)
    @patch('elasticsearch.client.Elasticsearch.index', unsafe=True)
    def test_es_hooks_modify_ignored_etype(self, index, exists, create):
        with self.admin_access.cnx() as cnx:
            entity = cnx.create_entity('Category',
                                       name=u'De Gaulles, Charles')
            cnx.commit()
            index.reset_mock()
            entity.cw_set(name=u'Different title')
            cnx.commit()
            index.assert_not_called()

    @patch('elasticsearch.client.indices.IndicesClient.create')
    @patch('elasticsearch.client.indices.IndicesClient.exists')
    @patch('elasticsearch.client.Elasticsearch.index')
    def test_externref_index(self, index, exists, create):
        with self.admin_access.cnx() as cnx:
            extref = cnx.create_entity('ExternRef',
                                       reftype=u'Virtual_exhibit',
                                       title=u'externref-title',
                                       url=u'http://toto')
            cnx.commit()
            indexer = cnx.vreg['es'].select('indexer', cnx)
            indexer.get_connection()
            self.assertTrue(index.called)
            args, kwargs = index.call_args
            self.assertEqual(kwargs['doc_type'], '_doc')
            for arg_name, expected_value in (
                ('title', u'externref-title'),
                ('cw_etype', u'Virtual_exhibit'),
                ('reftype', u'virtual_exhibit'),
                    ('cwuri', extref.cwuri)):
                self.assertEqual(kwargs['body'][arg_name], expected_value)
            index.reset_mock()
            new_title = u'new title'
            extref.cw_set(title=new_title)
            cnx.commit()
            self.assertTrue(index.called)
            args, kwargs = index.call_args
            self.assertEqual(kwargs['doc_type'], '_doc')
            self.assertEqual(kwargs['body']['cw_etype'], 'Virtual_exhibit')
            self.assertEqual(kwargs['body']['title'], new_title)

    @patch('elasticsearch.client.indices.IndicesClient.create')
    @patch('elasticsearch.client.indices.IndicesClient.exists')
    @patch('elasticsearch.client.Elasticsearch.index')
    def test_index_commemo_manif_prog(self, index, exists, create):
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            collection = ce('CommemoCollection',
                            title=u'Moyen Age',
                            year=1500)
            basecontent = ce('BaseContent', title=u'program',
                             content=u'31 juin')
            cnx.commit()
            indexer = cnx.vreg['es'].select('indexer', cnx)
            indexer.get_connection()
            self.assertTrue(index.called)
            index.reset_mock()
            commemo_item = ce('CommemorationItem', title=u'Commemoration',
                              alphatitle=u'commemoration',
                              content=u'content<br />commemoration',
                              commemoration_year=1500,
                              manif_prog=basecontent,
                              collection_top=collection)
            cnx.commit()
            for args, kwargs in index.call_args_list:
                if kwargs['doc_type'] == '_doc':
                    break
            else:
                self.fail('index not called on CommemorationItem')
            self.assertEqual(kwargs['doc_type'], '_doc')
            self.assertEqual(kwargs['body']['cw_etype'], 'CommemorationItem')
            for arg_name, expected_value in (
                ('cw_etype', 'CommemorationItem'),
                ('title', commemo_item.title),
                ('manif_prog', basecontent.content),
                ('content', 'content commemoration'),
                ('year', None),
                ('commemoration_year', commemo_item.commemoration_year),
                    ('cwuri', commemo_item.cwuri)):
                self.assertEqual(kwargs['body'][arg_name], expected_value)
            index.reset_mock()
            new_content = u'28 juin<br>2018'
            basecontent.cw_set(content=new_content)
            cnx.commit()
            indexer = cnx.vreg['es'].select('indexer', cnx)
            indexer.get_connection()
            self.assertTrue(index.called)
            args, kwargs = index.call_args
            for arg_name, expected_value in (
                ('title', commemo_item.title),
                ('manif_prog', '28 juin 2018'),
                ('year', None),
                ('commemoration_year', commemo_item.commemoration_year),
                    ('cwuri', commemo_item.cwuri)):
                self.assertEqual(kwargs['body'][arg_name], expected_value)

    @patch('elasticsearch.client.indices.IndicesClient.create')
    @patch('elasticsearch.client.indices.IndicesClient.exists')
    @patch('elasticsearch.client.Elasticsearch.index')
    def test_index_single_base_content(self, index, exists, create):
        with self.admin_access.cnx() as cnx:
            basecontent = cnx.create_entity('BaseContent', title=u'program',
                                            content=u'31 juin')
            cnx.commit()
            indexer = cnx.vreg['es'].select('indexer', cnx)
            indexer.get_connection()
            self.assertTrue(index.called)
            args, kwargs = index.call_args
            self.assertEqual(kwargs['doc_type'], '_doc')
            self.assertEqual(kwargs['body']['cw_etype'], 'BaseContent')
            self.assertEqual(kwargs['body']['content'], u'31 juin')
            index.reset_mock()
            # modify basecontent
            basecontent.cw_set(content=u'28 juin')
            cnx.commit()
            indexer = cnx.vreg['es'].select('indexer', cnx)
            indexer.get_connection()
            self.assertTrue(index.called)
            args, kwargs = index.call_args
            self.assertEqual(kwargs['doc_type'], '_doc')
            self.assertEqual(kwargs['body']['cw_etype'], 'BaseContent')
            self.assertEqual(kwargs['body']['content'], u'28 juin')

    @patch('elasticsearch.client.indices.IndicesClient.create')
    @patch('elasticsearch.client.indices.IndicesClient.exists')
    @patch('elasticsearch.client.Elasticsearch.index')
    def test_index_circular_file(self, index, exists, create):
        with self.admin_access.cnx() as cnx:
            signing_date = dt.date(2001, 6, 6)
            with open(osp.join(self.datadir, 'pdf.pdf'), 'rb') as pdf:
                ce = cnx.create_entity
                circular = ce('Circular',
                              circ_id=u'circ01', title=u'Circular',
                              signing_date=signing_date,
                              status=u'in-effect')
                attachement = ce('File',
                                 data_name=u'pdf',
                                 data_format=u'application/pdf',
                                 data=Binary(pdf.read()),
                                 reverse_attachment=circular)
                cnx.commit()
            indexer = cnx.vreg['es'].select('indexer', cnx)
            indexer.get_connection()
            self.assertTrue(index.called)
            args, kwargs = index.call_args
            self.assertEqual(kwargs['doc_type'], '_doc')
            pdf_text = u'Test\nCirculaire chat\n\n\x0c'
            for arg_name, expected_value in (
                ('cw_etype', 'Circular'),
                ('title', u'Circular'),
                ('sort_date', signing_date),
                ('attachment', pdf_text),
                    ('cwuri', circular.cwuri)):
                self.assertEqual(kwargs['body'][arg_name], expected_value)
            # modify the pdf
            index.reset_mock()
            new_title = u'New title'
            circular.cw_set(title=new_title)
            cnx.commit()
            self.assertTrue(index.called)
            args, kwargs = index.call_args
            self.assertEqual(kwargs['body']['title'], new_title)
            index.reset_mock()
            # update pdf
            new_pdf_content = u'Circulaire sérieux\n\n\x0c'
            with open(osp.join(self.datadir, 'pdf1.pdf'), 'rb') as pdf:
                attachement.cw_set(data=Binary(pdf.read()))
                cnx.commit()
            self.assertTrue(index.called)
            args, kwargs = index.call_args
            for arg_name, expected_value in (
                ('title', new_title),
                ('sort_date', signing_date),
                ('attachment', new_pdf_content),
                    ('cwuri', circular.cwuri)):
                self.assertEqual(kwargs['body'][arg_name], expected_value)


if __name__ == '__main__':
    unittest.main()
