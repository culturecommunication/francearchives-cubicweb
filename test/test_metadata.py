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

from cubicweb.devtools.testlib import CubicWebTC


class MetaTests(CubicWebTC):

    def test_newscontent_default_metadata(self):
        """tests IMeta when no Metadata entity is created"""
        with self.admin_access.cnx() as cnx:
            newscontent = cnx.create_entity('NewsContent',
                                            title=u'the-news',
                                            content=u'the-content',
                                            start_date=dt.date(2011, 1, 1))
            meta = newscontent.cw_adapt_to('IMeta')
            self.assertEqual(meta.meta_data(), [
                ('title', 'the-news'),
                (u'twitter:card', u'summary'),
                (u'twitter:site', u'@FranceArchives'),
            ])

    def test_newscontent_with_metadata(self):
        """tests IMeta when a Metadata entity is created"""
        with self.admin_access.cnx() as cnx:
            metadata = cnx.create_entity('Metadata',
                                         title=u'meta-title',
                                         description=u'meta-descr',
                                         keywords=u'kw1 kw2',
                                         subject=u'the-subject',
                                         creator=u'john')
            newscontent = cnx.create_entity('NewsContent',
                                            title=u'the-news',
                                            content=u'the-content',
                                            start_date=dt.date(2011, 1, 1),
                                            metadata=metadata)
            meta = newscontent.cw_adapt_to('IMeta')
            self.assertEqual(meta.meta_data(), [
                ('title', 'meta-title'),
                ('description', 'meta-descr'),
                ('keywords', 'kw1 kw2'),
                ('author', 'john'),
                ('subject', 'the-subject'),
                (u'twitter:card', u'summary'),
                (u'twitter:site', u'@FranceArchives'),
            ])

    def test_newscontent_mix_with_metadata(self):
        """tests IMeta when a Metadata entity is created"""
        with self.admin_access.cnx() as cnx:
            metadata = cnx.create_entity('Metadata',
                                         description=u'meta-descr',
                                         keywords=u'kw1 kw2')
            newscontent = cnx.create_entity('NewsContent',
                                            title=u'the-news',
                                            content=u'the-content',
                                            start_date=dt.date(2011, 1, 1),
                                            metadata=metadata)
            meta = newscontent.cw_adapt_to('IMeta')
            self.assertEqual(meta.meta_data(), [
                ('title', 'the-news'),
                ('description', 'meta-descr'),
                ('keywords', 'kw1 kw2'),
                (u'twitter:card', u'summary'),
                (u'twitter:site', u'@FranceArchives'),
            ])


class OpenGraphTests(CubicWebTC):

    def test_news_opengraph(self):
        with self.admin_access.cnx() as cnx:
            metadata = cnx.create_entity('Metadata',
                                         title=u'meta-title',
                                         description=u'meta-descr',
                                         keywords=u'kw1 kw2',
                                         subject=u'the-subject',
                                         creator=u'john')
            newscontent = cnx.create_entity('NewsContent',
                                            title=u'the-news',
                                            content=u'the-content',
                                            start_date=dt.date(2011, 1, 1),
                                            metadata=metadata)
            ogdata = newscontent.cw_adapt_to('IOpenGraph')
            self.assertEqual(ogdata.og_data(), [
                (u'locale', u'fr_FR'),
                (u'site_name', u'FranceArchives'),
                (u'url', newscontent.absolute_url()),
                (u'title', u'meta-title'),
                (u'description', u'meta-descr'),
                (u'type', 'article'),
            ])

    def test_card_locale_opengraph(self):
        """test card locale handling"""
        with self.admin_access.cnx() as cnx:
            card = cnx.create_entity('Card',
                                     wikiid=u'card-de',
                                     title=u'the-card',
                                     content=u'some-content')
            ogdata = card.cw_adapt_to('IOpenGraph')
            self.assertEqual(ogdata.og_data(), [
                (u'locale', u'de_DE'),
                (u'site_name', u'FranceArchives'),
                (u'url', card.absolute_url()),
                (u'title', u'the-card'),
                (u'type', 'article'),
            ])
            card.cw_set(wikiid=u'some-card')
            ogdata = card.cw_adapt_to('IOpenGraph')
            self.assertEqual(ogdata.og_data(), [
                (u'locale', u'fr_FR'),  # ← lang default to fr
                (u'site_name', u'FranceArchives'),
                (u'url', card.absolute_url()),
                (u'title', u'the-card'),
                (u'type', 'article'),
            ])


if __name__ == '__main__':
    unittest.main()
