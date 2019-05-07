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
import datetime as dt
import base64

from cubicweb import Binary
from cubicweb.pyramid.test import PyramidCWTest

from cubicweb_francearchives.pviews.edit import load_json_value


class BasicTests(unittest.TestCase):

    def test_load_json_value(self):
        for args, expected in [(('2014/10/13', 'Date'), dt.date(2014, 10, 13)),
                               (('0830/10/3', 'Date'), dt.date(830, 10, 3)),
                               (('0830-10-3', 'Date'), dt.date(830, 10, 3)),
                               (('830/10/13', 'Date'), dt.date(830, 10, 13)),
                               (('0830-10-3 10:22:04', 'Datetime'),
                                dt.datetime(830, 10, 3, 10, 22, 4))]:
            result = load_json_value(*args)
            self.assertEqual(result, expected)


class EditRoutesMixin(object):
    settings = {
        'cubicweb.bwcompat': 'no',
        'cubicweb.session.secret': 'stuff',
        'cubicweb.auth.authtkt.session.secret': 'stuff',
        'cubicweb.auth.authtkt.persistent.secret': 'stuff',
        'francearchives.autoinclude': 'no',
    }

    def includeme(self, config):
        config.include('cubicweb_francearchives.pviews.edit')


class NewsTests(EditRoutesMixin, PyramidCWTest):

    def test_newscontent_creation(self):
        content = u'<h1 style="border: 1px solid red; padding-bottom: 1em">Hello</h1>'
        self.webapp.put_json('/_update/NewsContent/123456', {
            'title': u'news-1',
            'content': content,
            'content_format': u'text/html',
            'start_date': u'2016-01-01',
        })
        with self.admin_access.cnx() as cnx:
            rset = cnx.find('NewsContent', title=u'news-1')
            self.assertEqual(len(rset), 1)
            news = rset.one()
            self.assertEqual(news.uuid, u'123456')
            self.assertEqual(news.content, content)
            self.assertEqual(news.content_format, u'text/html')
            self.assertEqual(news.content_format, u'text/html')
            self.assertEqual(news.start_date, dt.date(2016, 1, 1))

    def test_newscontent_update(self):
        with self.admin_access.cnx() as cnx:
            news = cnx.create_entity('NewsContent', title=u'news-1',
                                     start_date=dt.date(2016, 1, 1))
            uuid = news.uuid
            cnx.commit()
        content = u'<h1 style="border: 1px solid red; padding-bottom: 1em">Hello</h1>'
        self.webapp.put_json('/_update/NewsContent/{}'.format(uuid), {
            'title': u'news-1-2',
            'content': content,
            'content_format': u'text/html',
        })
        with self.admin_access.cnx() as cnx:
            rset = cnx.find('NewsContent', title=u'news-1')
            self.assertEqual(len(rset), 0)
            rset = cnx.find('NewsContent', uuid=uuid)
            self.assertEqual(len(rset), 1)
            news = rset.one()
            self.assertEqual(news.title, u'news-1-2')
            self.assertEqual(news.content, content)
            self.assertEqual(news.content_format, u'text/html')
            self.assertEqual(news.content_format, u'text/html')
            self.assertEqual(news.start_date, dt.date(2016, 1, 1))

    def test_newscontent_creation_metadata(self):
        self.webapp.put_json('/_update/NewsContent/123456', {
            'title': u'news-1',
            'content': u'<h1>Hello</h1>',
            'content_format': u'text/html',
            'start_date': u'2016-01-01',
            'metadata': [{
                'cw_etype': u'Metadata',
                'title': u'meta-news1',
                'type': u'news',
                'uuid': u'123456-metadata',
            }],
        })
        with self.admin_access.cnx() as cnx:
            rset = cnx.find('NewsContent', title=u'news-1')
            self.assertEqual(len(rset), 1)
            news = rset.one()
            self.assertEqual(news.content, u'<h1>Hello</h1>')
            self.assertTrue(news.metadata)
            self.assertEqual(news.metadata[0].title, u'meta-news1')
            self.assertEqual(news.metadata[0].type, u'news')

    def test_newscontent_update_metadata(self):
        with self.admin_access.cnx() as cnx:
            metadata = cnx.create_entity('Metadata', title=u'meta-news1')
            metadata_uuid = metadata.uuid
            news = cnx.create_entity('NewsContent', title=u'news-1',
                                     start_date=dt.date(2016, 1, 1),
                                     metadata=metadata)
            uuid = news.uuid
            cnx.commit()
        self.webapp.put_json('/_update/NewsContent/{}'.format(uuid), {
            'metadata': [{
                'cw_etype': u'Metadata',
                'title': u'meta-news2',
                'uuid': metadata_uuid,
            }],
        })
        with self.admin_access.cnx() as cnx:
            rset = cnx.find('NewsContent', title=u'news-1')
            self.assertEqual(len(rset), 1)
            news = rset.one()
            self.assertEqual(news.metadata[0].title, u'meta-news2')

    def test_newscontent_creation_uuid_conflict(self):
        self.webapp.put_json('/_update/NewsContent/123456', {
            'title': u'news-1',
            'content': u'<h1>Hello</h1>',
            'content_format': u'text/html',
            'start_date': u'2016-01-01',
            'uuid': '654321',
        }, status=409)

    def test_newscontent_creation_with_image(self):
        self.webapp.put_json('/_update/NewsContent/123456', {
            'title': u'news-1',
            'content': u'<h1>Hello</h1>',
            'content_format': u'text/html',
            'start_date': u'2016-01-01',
            'metadata': [{
                'cw_etype': u'Metadata',
                'title': u'meta-news1',
                'type': u'news',
                'uuid': u'123456-metadata',
            }],
            'news_image': [{
                'cw_etype': u'Image',
                'caption': u'image-caption',
                'uuid': u'123456-image',
                'image_file': [{
                    'cw_etype': u'File',
                    'uuid': u'123456-image-file',
                    'data': base64.b64encode('some-image-data'),
                    'data_name': u'image-name.png',
                    'data_format': u'image/png',
                }],
            }],
        })
        with self.admin_access.cnx() as cnx:
            rset = cnx.find('NewsContent', title=u'news-1')
            self.assertEqual(len(rset), 1)
            news = rset.one()
            self.assertEqual(news.metadata[0].title, u'meta-news1')
            self.assertEqual(len(news.news_image), 1)
            image = news.news_image[0]
            self.assertEqual(image.caption, u'image-caption')
            self.assertEqual(len(image.image_file), 1)
            fobj = image.image_file[0]
            self.assertEqual(fobj.data_name, u'image-name.png')
            self.assertEqual(fobj.data_format, u'image/png')
            self.assertEqual(fobj.data.getvalue(), u'some-image-data')

    def test_newscontent_update_image(self):
        self.webapp.put_json('/_update/NewsContent/123456', {
            'title': u'news-1',
            'content': u'<h1>Hello</h1>',
            'content_format': u'text/html',
            'start_date': u'2016-01-01',
            'metadata': [{
                'cw_etype': u'Metadata',
                'title': u'meta-news1',
                'type': u'news',
                'uuid': u'123456-metadata',
            }],
            'news_image': [{
                'cw_etype': u'Image',
                'caption': u'image-caption',
                'uuid': u'123456-image',
                'image_file': [{
                    'cw_etype': u'File',
                    'uuid': u'123456-image-file',
                    'data': base64.b64encode('some-image-data'),
                    'data_name': u'image-name.png',
                    'data_format': u'image/png',
                }],
            }],
        })
        self.webapp.put_json('/_update/NewsContent/123456', {
            'uuid': '123456',
            'news_image': [{
                'cw_etype': u'Image',
                'uuid': u'123456-image',
                'image_file': [{
                    'cw_etype': u'File',
                    'uuid': u'123456-image-file',
                    'data': base64.b64encode('some-new-image-data'),
                }],
            }],
        })
        with self.admin_access.cnx() as cnx:
            news = cnx.find('NewsContent', title=u'news-1').one()
            fobj = news.news_image[0].image_file[0]
            self.assertEqual(fobj.data_name, u'image-name.png')
            self.assertEqual(fobj.data_format, u'image/png')
            self.assertEqual(fobj.data.getvalue(), u'some-new-image-data')

    def test_newscontent_new_image(self):
        """ensure new images are detected and added"""
        with self.admin_access.cnx() as cnx:
            news = cnx.create_entity('NewsContent', title=u'news-1',
                                     start_date=dt.date(2016, 1, 1))
            uuid = news.uuid
            cnx.commit()
        self.webapp.put_json('/_update/NewsContent/{}'.format(uuid), {
            'news_image': [{
                'cw_etype': u'Image',
                'caption': u'image-caption',
                'uuid': u'123456-image',
                'image_file': [{
                    'cw_etype': u'File',
                    'uuid': u'123456-image-file',
                    'data': base64.b64encode('some-image-data'),
                    'data_name': u'image-name.png',
                    'data_format': u'image/png',
                }],
            }],
        })
        with self.admin_access.cnx() as cnx:
            news = cnx.find('NewsContent', uuid=uuid).one()
            self.assertEqual(len(news.news_image), 1)
            image = news.news_image[0]
            self.assertEqual(image.uuid, u'123456-image')
            self.assertEqual(len(image.image_file), 1)
            self.assertEqual(image.image_file[0].data.getvalue(), 'some-image-data')
            self.assertEqual(image.image_file[0].uuid, u'123456-image-file')

    def test_circular_update_concept(self):
        """ensure related concept is serialized with ``uuid_attr`` attr"""
        with self.admin_access.cnx() as cnx:
            scheme = cnx.create_entity('ConceptScheme', title=u'some classification')
            concept1 = cnx.create_entity('Concept', in_scheme=scheme, cwuri=u'uri1')
            cnx.create_entity('Label', label=u'hip', language_code=u'fr',
                              kind=u'preferred', label_of=concept1)
            concept2 = cnx.create_entity('Concept', in_scheme=scheme, cwuri=u'uri2')
            cnx.create_entity('Label', label=u'hip', language_code=u'fr',
                              kind=u'preferred', label_of=concept2)
            circular = cnx.create_entity('Circular', circ_id=u'circ1', status=u'revoked',
                                         title=u'circ1',
                                         historical_context=concept1)
            uuid = circular.uuid
            cnx.commit()
        self.webapp.put_json('/_update/Circular/{}'.format(uuid), {
            'circ_id': u'circ1',
            'status': u'revoked',
            'title': u'circ2',
            'historical_context': [{
                'cw_etype': 'Concept',
                'cwuri': 'uri2',
            }]
        })
        with self.admin_access.cnx() as cnx:
            c = cnx.find('Circular', circ_id=u'circ1').one()
            self.assertEqual(c.title, 'circ2')
            self.assertEqual(len(c.historical_context), 1)
            self.assertEqual(c.historical_context[0].cwuri, 'uri2')
            rset = cnx.find('Concept', cwuri=u'uri1')
            self.assertEqual(len(rset), 1)
            rset = cnx.find('Concept', cwuri=u'uri2')
            self.assertEqual(len(rset), 1)

    def test_circular_relto_concept(self):
        """ensure related concept is serialized with ``uuid_attr`` attr"""
        with self.admin_access.cnx() as cnx:
            scheme = cnx.create_entity('ConceptScheme', title=u'some classification')
            concept = cnx.create_entity('Concept', in_scheme=scheme, cwuri=u'uri')
            cnx.create_entity('Label', label=u'hip', language_code=u'fr',
                              kind=u'preferred', label_of=concept)
            circular = cnx.create_entity(
                'Circular', circ_id=u'circ1', status=u'revoked',
                title=u'circ1'
                # XXX ajout business_field initial
            )
            uuid = circular.uuid
            cnx.commit()
        self.webapp.put_json('/_update/Circular/{}'.format(uuid), {
            'circ_id': u'circ1',
            'status': u'revoked',
            'title': u'circ2',
            'business_field': [{
                'cw_etype': 'Concept',
                'cwuri': 'uri',
            }]
        })
        with self.admin_access.cnx() as cnx:
            c = cnx.find('Circular', circ_id=u'circ1').one()
            self.assertEqual(c.title, 'circ2')
            self.assertEqual(len(c.business_field), 1)
            self.assertEqual(c.business_field[0].cwuri, 'uri')
            rset = cnx.find('Concept', cwuri=u'uri')
            self.assertEqual(len(rset), 1)

    def test_newscontent_change_image(self):
        """ensure old images are deleted and replaced"""
        self.webapp.put_json('/_update/NewsContent/123456', {
            'title': u'news-1',
            'content': u'<h1>Hello</h1>',
            'content_format': u'text/html',
            'start_date': u'2016-01-01',
            'metadata': [{
                'cw_etype': u'Metadata',
                'title': u'meta-news1',
                'type': u'news',
                'uuid': u'123456-metadata',
            }],
            'news_image': [{
                'cw_etype': u'Image',
                'caption': u'image-caption',
                'uuid': u'123456-image',
                'image_file': [{
                    'cw_etype': u'File',
                    'uuid': u'123456-image-file',
                    'data': base64.b64encode('some-image-data'),
                    'data_name': u'image-name.png',
                    'data_format': u'image/png',
                }],
            }],
        })
        self.webapp.put_json('/_update/NewsContent/123456', {
            'news_image': [{
                'cw_etype': u'Image',
                'caption': u'image-caption2',
                'uuid': u'123456-image2',
                'image_file': [{
                    'cw_etype': u'File',
                    'uuid': u'123456-image-file2',
                    'data': base64.b64encode('some-image-data2'),
                    'data_name': u'image-name2.jpg',
                    'data_format': u'image/jpg',
                }],
            }],
        })
        with self.admin_access.cnx() as cnx:
            news = cnx.find('NewsContent', uuid=u'123456').one()
            self.assertEqual(len(news.news_image), 1)
            # make sure the new image was added and linked to the news content
            image = news.news_image[0]
            self.assertEqual(image.uuid, u'123456-image2')
            self.assertEqual(len(image.image_file), 1)
            self.assertEqual(image.image_file[0].data.getvalue(), 'some-image-data2')
            self.assertEqual(image.image_file[0].uuid, u'123456-image-file2')
            # make sure the old image does not exist
            self.assertEqual(len(cnx.find('Image', uuid=u'123456-image')), 0)
            self.assertEqual(len(cnx.find('File', uuid=u'123456-image-file')), 0)

    def test_content_not_update_if_not_needed(self):
        self.webapp.put_json('/_update/NewsContent/123456', {
            'title': u'news-1',
            'content': u'<h1>Hello</h1>',
            'content_format': u'text/html',
            'start_date': u'2016-01-01',
            'modification_date': u'2015-01-01 00:00:00',
        })
        with self.admin_access.cnx() as cnx:
            news = cnx.find('NewsContent', uuid=u'123456').one()
            self.assertEqual(news.modification_date.year, 2015)
        self.webapp.put_json('/_update/NewsContent/123456', {
            'title': u'news-1',
            'content': u'<h1>Hello</h1>',
        })
        with self.admin_access.cnx() as cnx:
            news = cnx.find('NewsContent', uuid=u'123456').one()
            self.assertEqual(news.modification_date.year, 2015)
        self.webapp.put_json('/_update/NewsContent/123456', {
            'title': u'news-2',
        })
        with self.admin_access.cnx() as cnx:
            news = cnx.find('NewsContent', uuid=u'123456').one()
            self.assertEqual(news.modification_date.year, dt.datetime.now().year)

    def test_concept_multipleref(self):
        """ensure one concet can be used in multiple relations"""
        with self.admin_access.cnx() as cnx:
            scheme = cnx.create_entity('ConceptScheme', title=u'some classification')
            concept = cnx.create_entity('Concept', in_scheme=scheme, cwuri=u'uri')
            cnx.create_entity('Label', label=u'hip', language_code=u'fr',
                              kind=u'preferred', label_of=concept)
            circular = cnx.create_entity('Circular', circ_id=u'circ1', status=u'revoked',
                                         title=u'circ1')
            uuid = circular.uuid
            cnx.commit()
        self.webapp.put_json('/_update/Circular/{}'.format(uuid), {
            'circ_id': u'circ1',
            'status': u'revoked',
            'title': u'circ2',
            'historical_context': [{
                'cw_etype': 'Concept',
                'cwuri': 'uri',
            }],
            'business_field': [{
                'cw_etype': 'Concept',
                'cwuri': 'uri',
            }]
        })
        with self.admin_access.cnx() as cnx:
            c = cnx.find('Circular', circ_id=u'circ1').one()
            self.assertEqual(c.title, 'circ2')
            self.assertEqual(len(c.business_field), 1)
            self.assertEqual(c.business_field[0].cwuri, 'uri')
            self.assertEqual(len(c.historical_context), 1)
            self.assertEqual(c.historical_context[0].cwuri, 'uri')
            rset = cnx.find('Concept', cwuri=u'uri')
            self.assertEqual(len(rset), 1)

    def test_dont_delete_target_if_not_composite(self):
        self.webapp.put_json('/_update/Circular/123456', {
            'circ_id': u'circ1',
            'status': u'revoked',
            'title': u'circ1',
            'additional_link': [{
                'cw_etype': u'Link',
                'uuid': 'link1',
                'url': 'url1',
                'title': 'link1',
            }],
        })
        with self.admin_access.cnx() as cnx:
            circular = cnx.find('Circular', uuid=u'123456').one()
            self.assertEqual(circular.circ_id, u'circ1')
            self.assertEqual(len(circular.additional_link), 1)
            self.assertEqual(circular.additional_link[0].uuid, 'link1')
        self.webapp.put_json('/_update/Circular/123456', {
            'circ_id': u'circ1',
            'status': u'revoked',
            'title': u'circ1',
            'additional_link': [{
                'cw_etype': u'Link',
                'uuid': 'link2',
                'url': 'url2',
                'title': 'link2',
            }],
        })
        with self.admin_access.cnx() as cnx:
            circular = cnx.find('Circular', uuid=u'123456').one()
            self.assertEqual(circular.circ_id, u'circ1')
            self.assertEqual(len(circular.additional_link), 1)
            self.assertEqual(circular.additional_link[0].uuid, 'link2')
            # additional_link is not composite, link1 should not have been deleted
            self.assertEqual(len(cnx.find('Link', uuid=u'link1')), 1)

    def test_move_basecontent(self):
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            ce('Section', title=u'sect-1', name=u'sect-1',
               children=ce('BaseContent', title=u'the-object', uuid=u'654321'))
            ce('Section', title=u'sect-2', uuid=u'123456', name=u'sect-2')
            cnx.commit()
        self.webapp.put_json('/_update/Section/123456', {
            'cw_etype': u'Section',
            'title': u'sect-2',
            'name': u'sect-2',
            'children': [{
                'cw_etype': u'BaseContent',
                'uuid': '654321',
                'title': u'the-object',
            }],
        })
        with self.admin_access.cnx() as cnx:
            article = cnx.find('BaseContent', uuid=u'654321').one()
            self.assertEqual(article.reverse_children[0].uuid, u'123456')


class MoveTests(EditRoutesMixin, PyramidCWTest):

    def test_move_entity(self):
        with self.admin_access.cnx() as cnx:
            article = cnx.create_entity('BaseContent', title=u'the-object')
            article_uuid = article.uuid
            cnx.create_entity('Section',
                              title=u'sect-1', name=u'sect-1',
                              children=article)
            sect2_uuid = cnx.create_entity('Section', title=u'sect-2',
                                           name=u'sect-2').uuid
            cnx.commit()
        self.webapp.post_json('/_update/move/BaseContent/{}'.format(article_uuid), {
            'to-section': sect2_uuid,
        })
        with self.admin_access.cnx() as cnx:
            article = cnx.find('BaseContent').one()
            self.assertEqual(article.reverse_children[0].name, u'sect-2')

    def test_move_entity_same_section(self):
        """make sure moving an entity ot its own section is a noop"""
        with self.admin_access.cnx() as cnx:
            article = cnx.create_entity('BaseContent', title=u'the-object')
            article_uuid = article.uuid
            sect1_uuid = cnx.create_entity('Section',
                                           title=u'sect-1', name=u'sect-1',
                                           children=article).uuid
            cnx.commit()
        self.webapp.post_json('/_update/move/BaseContent/{}'.format(article_uuid), {
            'to-section': sect1_uuid,
        })
        with self.admin_access.cnx() as cnx:
            article = cnx.find('BaseContent').one()
            self.assertEqual(article.reverse_children[0].name, u'sect-1')


class DeleteTests(EditRoutesMixin, PyramidCWTest):

    def test_delete_newscontent(self):
        with self.admin_access.cnx() as cnx:
            fobj = cnx.create_entity('File',
                                     data=Binary('some-image-data'),
                                     data_name=u'image-name.png',
                                     data_format=u'image/png')
            image = cnx.create_entity('Image',
                                      caption=u'image-caption',
                                      image_file=fobj)
            news = cnx.create_entity('NewsContent',
                                     title=u'news', start_date=u'2016-01-01',
                                     news_image=image)
            news_uuid = news.uuid
            cnx.commit()
        self.webapp.delete('/_update/NewsContent/{}'.format(news_uuid))
        with self.admin_access.cnx() as cnx:
            self.assertEqual(len(cnx.find('NewsContent')), 0)
            self.assertEqual(len(cnx.find('Image')), 0)
            self.assertEqual(len(cnx.find('File')), 0)


if __name__ == '__main__':
    unittest.main()
