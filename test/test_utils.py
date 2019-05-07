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

from mock import Mock, MagicMock
import string

from cubicweb.devtools.testlib import CubicWebTC
from cubicweb.uilib import remove_html_tags

from cubicweb_francearchives.utils import find_card
from cubicweb_francearchives.entities.faproperties import (process_html,
                                                           fix_links as fa_fix_links)
from cubicweb_francearchives.views.forms import EMAIL_REGEX
from cubicweb_francearchives.dataimport import normalize_entry
from cubicweb_francearchives.views.search import PniaElasticSearchView
from cubicweb_francearchives.utils import id_for_anchor
from cubicweb_francearchives.xmlutils import enhance_accessibility
from cubicweb_francearchives.utils import clean_up, is_absolute_url


class UtilsTest(CubicWebTC):

    def test_fa_fix_links_1(self):
        html = u'<div class="ead-p"> <a href="www.archives.valdoise.fr">Archives <b>départementales</b> du Val</a></div>'
        expected = u'<div class="ead-p"> <a href="www.archives.valdoise.fr" rel="nofollow noopener noreferrer" target="_blank" title="Archives départementales du Val - New window">Archives <b>départementales</b> du Val</a></div>'
        with self.admin_access.cnx() as cnx:
            self.assertEqual(fa_fix_links(html, cnx), expected)

    def test_fa_fix_links_2(self):
        html = u'''<div class="ead-p"><a href="www.archives.valdoise.fr" title="site">Archives départementales du Val-d'Oise</a></div>'''
        expected = u'''<div class="ead-p"><a href="www.archives.valdoise.fr" title="site - New window" rel="nofollow noopener noreferrer" target="_blank">Archives départementales du Val-d'Oise</a></div>'''
        with self.admin_access.cnx() as cnx:
            self.assertEqual(fa_fix_links(html, cnx), expected)

    def test_fa_fix_links_3(self):
        html = u'<div class="ead-section ead-otherfindaid"><div class="ead-wrapper"><div class="ead-p">Inventaire, CADN, 1991.<br>\n<a href="medias/Intruments%20de%20recherche%20bureautiques/CADN/POI/Otase_B_1955-1971_26POI.pdf" rel="nofollow noopener noreferrer" target="_blank">Voir l\'instrument de recherche</a>&#160;</div></div></div>'
        expected = (u'<div class="ead-section ead-otherfindaid"><div class="ead-wrapper">'
                    u'<div class="ead-p">Inventaire, CADN, 1991.<br>\n</div></div></div>')
        with self.admin_access.cnx() as cnx:
            self.assertEqual(fa_fix_links(html, cnx), expected)

    def test_insert_biblio_labels(self):
        html = u"""<div class="ead-section ead-bibliography"><div class="ead-label">bibliography_label</div><div class="ead-wrapper"><div>
<div class="ead-p">text-bibliography</div>
</div></div></div>
<div class="ead-section ead-bioghist"><div class="ead-wrapper">
<div class="ead-p">text-bioghist</div>
</div></div>"""

        expected = """<div class="ead-section ead-bibliography"><div class="ead-label">bibliography_label</div><div class="ead-wrapper"><div>
<div class="ead-p">text-bibliography</div>
</div></div></div>
<div class="ead-section ead-bioghist"><div class="ead-label">bioghist_label</div><div class="ead-wrapper">
<div class="ead-p">text-bioghist</div>
</div></div>"""

        labels = ['bibliography', 'bibref', 'bioghist']
        with self.admin_access.cnx() as cnx:
            got = process_html(cnx, html, labels=labels)
            self.assertEqual(got, expected)

    def test_skip_empty_biblio_labels(self):
        html = '''<div class="ead-section ead-bibliography"><div class="ead-wrapper"></div></div><div class="ead-section ead-arrangement"><div class="ead-wrapper"><div class="ead-p">Classement chronologique</div></div></div>'''
        labels = ['bibliography', 'bibref', 'bioghist']
        with self.admin_access.cnx() as cnx:
            got = process_html(cnx, html, labels=labels)
            self.assertEqual(got, html)

    def test_insert_description_labels(self):
        html = '''<div class="ead-section ead-accruals"><div class="ead-wrapper"><div class="ead-p">Fonds ouvert susceptible d'accroissement</div></div></div>
<div class="ead-section ead-appraisal"><div class="ead-wrapper"><div class="ead-p">Aucun</div></div></div>
<div class="ead-section ead-arrangement"><div class="ead-wrapper"><div class="ead-p">Classement chronologique</div></div></div>'''

        expected =  '''<div class="ead-section ead-accruals"><div class="ead-label">accruals_label</div><div class="ead-wrapper"><div class="ead-p">Fonds ouvert susceptible d'accroissement</div></div></div>
<div class="ead-section ead-appraisal"><div class="ead-label">appraisal_label</div><div class="ead-wrapper"><div class="ead-p">Aucun</div></div></div>
<div class="ead-section ead-arrangement"><div class="ead-label">arrangement_label</div><div class="ead-wrapper"><div class="ead-p">Classement chronologique</div></div></div>'''

        labels = ['accruals', 'appraisal', 'arrangement']
        with self.admin_access.cnx() as cnx:
            got = process_html(cnx, html, labels=labels)
            self.assertEqual(got, expected)

    def test_additional_resources(self):
        html = u'<div class="ead-section ead-otherfindaid"><div class="ead-wrapper"><div class="ead-p"><a href="../file/dd5464631894040fed175ea8db7bd843d3fc2f48/FRMAEE_MN_179CPCOM_Maroc.pdf" rel="nofollow noopener noreferrer" target="_blank">Voir l\'instrument de\n    recherche</a>&#160;</div></div></div>\n<div class="ead-section ead-otherfindaid"><div class="ead-wrapper"><div class="ead-p"><a href="../file/dd5464631894040fed175ea8db7bd843d3fc2f48/FRMAEE_MN_179CPCOM_Maroc.pdf" rel="nofollow noopener noreferrer" target="_blank">Voir l\'instrument de\n    recherche</a>&#160;</div></div></div>\n<div class="ead-section ead-relatedmaterial"><div class="ead-wrapper"><div class="ead-p"><a href="../file/06419493742584d8873722d6b1b3732cfc7d8532/FRMAEE_MN_179CPCOM_Maroc.pdf" rel="nofollow noopener noreferrer" target="_blank">Voir l\'instrument de\n    recherche</a>&#160;</div></div></div>\n<div class="ead-section ead-separatedmaterial"><div class="ead-wrapper"><div class="ead-p"><a href="../file/dd5464631894040fed175ea8db7bd843d3fc2f48/FRMAEE_MN_179CPCOM_Maroc.pdf" rel="nofollow noopener noreferrer" target="_blank">Voir l\'instrument de\n    recherche</a>&#160;</div></div></div>'
        expected = u'<div class="ead-section ead-otherfindaid"><div class="ead-wrapper"><div class="ead-p"><a href="../file/dd5464631894040fed175ea8db7bd843d3fc2f48/FRMAEE_MN_179CPCOM_Maroc.pdf">Voir l\'instrument de\n    recherche</a>\xa0</div></div></div>\n<div class="ead-section ead-otherfindaid"><div class="ead-wrapper"><div class="ead-p"><a href="../file/dd5464631894040fed175ea8db7bd843d3fc2f48/FRMAEE_MN_179CPCOM_Maroc.pdf">Voir l\'instrument de\n    recherche</a>\xa0</div></div></div>\n<div class="ead-section ead-relatedmaterial"><div class="ead-wrapper"><div class="ead-p"><a href="../file/06419493742584d8873722d6b1b3732cfc7d8532/FRMAEE_MN_179CPCOM_Maroc.pdf">Voir l\'instrument de\n    recherche</a>\xa0</div></div></div>\n<div class="ead-section ead-separatedmaterial"><div class="ead-wrapper"><div class="ead-p"><a href="../file/dd5464631894040fed175ea8db7bd843d3fc2f48/FRMAEE_MN_179CPCOM_Maroc.pdf">Voir l\'instrument de\n    recherche</a>\xa0</div></div></div>'
        labels=['custodhist']
        with self.admin_access.cnx() as cnx:
            got = process_html(cnx, html, labels=labels)
            self.assertEqual(got, expected)

    def test_find_card_nocard(self):
        with self.admin_access.cnx() as cnx:
            self.assertIsNone(find_card(cnx, 'no-such-wikiid'))

    def test_find_card_nolang(self):
        with self.admin_access.cnx() as cnx:
            c1 = cnx.create_entity('Card', title=u'c1', wikiid=u'c1',
                                   content=u'foo')
            self.assertEqual(find_card(cnx, 'c1').eid, c1.eid)
            cnx.set_language('fr')
            self.assertEqual(find_card(cnx, 'c1').eid, c1.eid)

    def test_find_card_fr(self):
        with self.admin_access.cnx() as cnx:
            c1 = cnx.create_entity('Card', title=u'c1', wikiid=u'c1',
                                   content=u'foo')
            c1fr = cnx.create_entity('Card', title=u'c1', wikiid=u'c1-fr',
                                     content=u'foo')
            cnx.set_language('fr')
            self.assertEqual(find_card(cnx, 'c1').eid, c1fr.eid)

    def test_find_card_en_match(self):
        with self.admin_access.cnx() as cnx:
            c1 = cnx.create_entity('Card', title=u'c1', wikiid=u'c1',
                                   content=u'foo')
            c1en = cnx.create_entity('Card', title=u'c1', wikiid=u'c1-en',
                                     content=u'foo')
            c1fr = cnx.create_entity('Card', title=u'c1', wikiid=u'c1-fr',
                                     content=u'foo')
            cnx.set_language('en')
            self.assertEqual(find_card(cnx, 'c1').eid, c1en.eid)

    def test_find_card_en_fallback(self):
        with self.admin_access.cnx() as cnx:
            c1 = cnx.create_entity('Card', title=u'c1', wikiid=u'c1',
                                   content=u'foo')
            c1fr = cnx.create_entity('Card', title=u'c1', wikiid=u'c1-fr',
                                     content=u'foo')
            cnx.set_language('en')
            self.assertEqual(find_card(cnx, 'c1').eid, c1fr.eid)

    def test_find_card_en_fallback_when_nocontent(self):
        with self.admin_access.cnx() as cnx:
            c1fr = cnx.create_entity('Card', title=u'c1', wikiid=u'c1-fr',
                                     content=u'foo')
            # create an english card but with no content. Behaviour should
            # be the same as if there was no card
            c1en = cnx.create_entity('Card', title=u'c1', wikiid=u'c1-en')
            cnx.set_language('en')
            self.assertEqual(find_card(cnx, 'c1').eid, c1fr.eid)

    def test_email_checker(self):
        email = 'test@toto.fr'
        self.assertTrue(EMAIL_REGEX.match(email))
        email = 'testtoto.fr'
        self.assertFalse(EMAIL_REGEX.match(email))
        email = 'test@totofr'
        self.assertFalse(EMAIL_REGEX.match(email))
        email = '@test@toto.fr'
        self.assertFalse(EMAIL_REGEX.match(email))

    def test_normalize_entry(self):
        norm = normalize_entry
        self.assertEqual(norm('Charles de Gaulle'), 'charles de gaulle')
        self.assertEqual(norm('Charles   de Gaulle'), 'charles de gaulle')
        self.assertEqual(norm('Charles, Gaulle (de)'), 'charles de gaulle')
        self.assertEqual(norm('Gaulle de, Charles'), 'charles de gaulle')
        self.assertEqual(norm('Charles (de)   Gaulle'), 'charles de gaulle')
        self.assertEqual(norm('Charles de Gaulle (1890-1970)'), 'charles de gaulle')
        self.assertEqual(norm('Charles de Gaulle (1890 - 1970)'), 'charles de gaulle')
        self.assertEqual(norm('Charles de Gaulle (1890 - 1970)'), 'charles de gaulle')
        self.assertEqual(norm('Liszt, Franz (1811-1886)'), 'franz liszt')
        self.assertEqual(norm('Liszt (Franz)'), 'franz liszt')
        self.assertEqual(norm(u'debré, jean-louis (1944-....)'), 'debre jeanlouis')
        self.assertEqual(norm(u'DEBRE, Jean-Louis'), 'debre jeanlouis')
        self.assertEqual(norm(u'Debré, Jean-Louis'), 'debre jeanlouis')

    def test_pagination(self):
        # params: number_of_items (items_per_page, max_pages, max_pagination_links)
        results_per_page = 10

        pesv = PniaElasticSearchView()
        pesv._cw = Mock()
        pesv._cw.form = Mock()

        # No need to paginate
        pesv._cw.form.copy = MagicMock(return_value={'page': 1})
        self.assertEqual(len(pesv.pagination(results_per_page)), 0)

        # [1] 2 > (only 1 item on the second page)
        pesv._cw.form.copy = MagicMock(return_value={'page': 1})
        self.assertEqual(len(pesv.pagination(results_per_page + 1)), 3)

        # [1] 2 >
        pesv._cw.form.copy = MagicMock(return_value={'page': 1})
        self.assertEqual(len(pesv.pagination(results_per_page * 2)), 3)

        # [1] 2 3 >
        pesv._cw.form.copy = MagicMock(return_value={'page': 1})
        self.assertEqual(len(pesv.pagination(results_per_page * 3)), 4)

        # < 1 [2] 3 4 5 >
        pesv._cw.form.copy = MagicMock(return_value={'page': 2})
        self.assertEqual(len(pesv.pagination(results_per_page * 5)), 7)

        # < 1 2 3 4 5 6 [7]
        pesv._cw.form.copy = MagicMock(return_value={'page': 7})
        self.assertEqual(len(pesv.pagination(results_per_page * 7)), 8)

        # [1] 2 3 4 5 … 30 >
        pesv._cw.form.copy = MagicMock(return_value={'page': 1})
        self.assertEqual(len(pesv.pagination(results_per_page * 30)), 8)

        # < 1 [2] 3 4 5 … 30 >
        pesv._cw.form.copy = MagicMock(return_value={'page': 2})
        self.assertEqual(len(pesv.pagination(results_per_page * 30)), 9)

        # < 1 … 26 27 28 29 [30]
        pesv._cw.form.copy = MagicMock(return_value={'page': 30})
        self.assertEqual(len(pesv.pagination(results_per_page * 30)), 8)

        # < 1 … 26 27 28 [29] 30 >
        pesv._cw.form.copy = MagicMock(return_value={'page': 29})
        self.assertEqual(len(pesv.pagination(results_per_page * 30)), 9)

        # < 1 … 13 14 [15] 16 … 30 >
        pesv._cw.form.copy = MagicMock(return_value={'page': 15})
        self.assertEqual(len(pesv.pagination(results_per_page * 30)), 10)

        # < 1 … 13 14 [15] 16 17 … 30 >
        pesv._cw.form.copy = MagicMock(return_value={'page': 15})
        self.assertEqual(
            len(pesv.pagination(results_per_page * 30, max_pagination_links=7)),
            11
        )


    def test_get_pagination_range(self):
        # params: current_page, number_of_pages, window
        pesv = PniaElasticSearchView()

        # left hand side
        self.assertListEqual(pesv.get_pagination_range(1, 10, 3), [1, 2, 3])
        self.assertListEqual(pesv.get_pagination_range(2, 10, 3), [1, 2, 3])
        self.assertListEqual(pesv.get_pagination_range(3, 10, 3), [2, 3, 4])

        # middle
        self.assertListEqual(pesv.get_pagination_range(5, 10, 3), [4, 5, 6])

        # right hand side
        self.assertListEqual(pesv.get_pagination_range(9, 10, 3), [8, 9, 10])
        self.assertListEqual(pesv.get_pagination_range(10, 10, 3), [8, 9, 10])

        # even window
        self.assertListEqual(pesv.get_pagination_range(5, 10, 4), [3, 4, 5, 6])

        # Abberant values
        self.assertListEqual(pesv.get_pagination_range(11, 10, 4), [7, 8, 9, 10])
        self.assertListEqual(pesv.get_pagination_range(3, 5, 10), [1, 2, 3, 4, 5])
        self.assertListEqual(pesv.get_pagination_range(3, 5, 1), [3])

    def test_clean_up_punctuation(self):
        """Test filename clean-up.

        Trying: filename contains punctuation
        Expecting: punctuation replaced with "_"
        """
        filename = "foo" + string.punctuation + "bar"
        cleaned_up = "foo" + len(string.punctuation) * "_" + "bar"
        self.assertEqual(cleaned_up, clean_up(filename))

    def test_clean_up_whitespace(self):
        """Test filename clean-up.

        Trying: filename contains whitespaces
        Expecting: whitespaces replaced with "_"
        """
        filename = "foo" + string.whitespace + "bar"
        cleaned_up = "foo" + len(string.whitespace) * "_" + "bar"
        self.assertEqual(cleaned_up, clean_up(filename))

    def test_clean_up_common_french(self):
        """Test filename clean-up.

        Trying: filename contains any of "ÀàÇçÉéÈè"
        Expecting: replaced with "AaEe"
        """
        filename = u"ÀàÇçÉéÈè"
        cleaned_up = u"AaCcEeEe"
        self.assertEqual(cleaned_up, clean_up(filename))

    def test_absolute_url(self):
        """Test absolute URL check.

        Trying: https://foo.com/bar
        Expecting: is True
        """
        self.assertTrue(is_absolute_url("https://foo.com/bar"))

    def test_relative_url(self):
        """Test absolute URL check.

        Trying: /foo/bar
        Expecting: is False
        """
        self.assertFalse(is_absolute_url("/foo/bar"))

    def test_www(self):
        """Test absolute URL check.

        Trying: www.foo.com/bar
        Expecting: is True
        """
        self.assertTrue(is_absolute_url("www.foo.com/bar"))


class XMlUtilsTest(CubicWebTC):

    def test_link_remove_empty_title(self):
        html = u'''<div><a href="www.archives.valdoise.fr" title="">Archives départementales du Val-d'Oise</a></div>'''  # noqa
        target = 'rel="nofollow noopener noreferrer" target="_blank"'
        expected = u'''<div><a href="www.archives.valdoise.fr" {}>Archives départementales du Val-d'Oise</a></div>'''.format(target)  # noqa
        with self.admin_access.cnx() as cnx:
            self.assertEqual(enhance_accessibility(html, cnx), expected)

    def test_link_invalid_html(self):
        html = u'''href="www.archives.valdoise.fr" title="{0}"> Archives départementales du Val-d'Oise</a></div>'''  # noqa
        with self.admin_access.cnx() as cnx:
            self.assertEqual(enhance_accessibility(html, cnx), html)

    def test_link_remove_identical_link_title(self):
        title = u"Archives départementales du Val-d'Oise"
        label = u"Archives départementales du <i>Val-d'Oise</i>"
        html = u'<div><a href="www.archives.valdoise.fr" title="{0}">{1}</a></div>'.format(
            title, label)
        target = 'rel="nofollow noopener noreferrer" target="_blank"'
        expected = u'<div><a href="www.archives.valdoise.fr" {}>{}</a></div>'.format(
            target, label)
        with self.admin_access.cnx() as cnx:
            self.assertEqual(enhance_accessibility(html, cnx), expected)

    def test_link_add_blank_target(self):
        html = u'<div><a href="www.google">google</a></div>'
        expected = u'<div><a href="www.google" rel="nofollow noopener noreferrer" target="_blank">google</a></div>'  # noqa
        with self.admin_access.cnx() as cnx:
            self.assertEqual(enhance_accessibility(html, cnx), expected)

    def test_link_do_not_add_blank_target(self):
        with self.admin_access.cnx() as cnx:
            html = u'<div><a href="{}google.fr">google</a></div>'.format(cnx.base_url())
            self.assertEqual(enhance_accessibility(html, cnx), html)

    def test_link_add_target_1(self):
        html = u'<a href="www.archives.valdoise.fr" title="toto">toto</a>'
        with self.admin_access.cnx() as cnx:
            expected = '<a href="www.archives.valdoise.fr" rel="nofollow noopener noreferrer" target="_blank">toto</a>'
            self.assertEqual(enhance_accessibility(html, cnx), expected)

    def test_link_add_target_2(self):
        html = u'<a href="//www.archives.valdoise.fr" title="toto">toto</a>'
        with self.admin_access.cnx() as cnx:
            expected = '<a href="//www.archives.valdoise.fr" rel="nofollow noopener noreferrer" target="_blank">toto</a>'
            self.assertEqual(enhance_accessibility(html, cnx), expected)

    def test_link_do_not_add_target_1(self):
        html = u'<a href="./article" title="titi">toto</a>'
        with self.admin_access.cnx() as cnx:
            self.assertEqual(enhance_accessibility(html, cnx), html)

    def test_link_do_not_add_target_2(self):
        html = u'<a href="/article" title="titi">toto</a>'
        with self.admin_access.cnx() as cnx:
            self.assertEqual(enhance_accessibility(html, cnx), html)

    def test_link_keep_link_title(self):
        title = u"Archives départementales du Val-d'Oise - Voir plus"
        label = u"Archives départementales du Val-d'Oise"
        html = u'<div><a href="www.archives.valdoise.fr" title="{0}">{1}</a></div>'.format(
            title, label)
        target = 'rel="nofollow noopener noreferrer" target="_blank"'
        expected = u'<div><a href="www.archives.valdoise.fr" title="{0}" {1}>{2}</a></div>'.format(
            title, target, label)
        with self.admin_access.cnx() as cnx:
            self.assertEqual(enhance_accessibility(html, cnx), expected)

    def test_remove_target(self):
        html = u'<a href="../location/18363459" target="_blank" rel="noopener">Saint-Laurent-Blangy</a>'
        expected = u'<a href="../location/18363459">Saint-Laurent-Blangy</a>'
        with self.admin_access.cnx() as cnx:
            self.assertEqual(enhance_accessibility(html, cnx), expected)

    def test_images_add_empty_alt(self):
        """images must have alt attribute"""
        html = u'<div><img src="http://advaldoise.fr"/></div>'
        expected = u'<div><img src="http://advaldoise.fr" alt=""></div>'
        with self.admin_access.cnx() as cnx:
            self.assertEqual(enhance_accessibility(html, cnx), expected)

    def test_images_add_link_title_as_alt(self):
        """image's alt inside a link must be equal to the link title"""
        label = u"Archives départementales du <i>Val-d'Oise</i>"
        html = (u'<div><img src="http://google.fr">'
                u'<a href="www.archives.valdoise.fr">'
                u'<img src="http://advaldoise.fr" '
                u'alt="toto" />{}</a></div>').format(
                label)
        target = 'rel="nofollow noopener noreferrer" target="_blank"'
        expected = (u'<div><img src="http://google.fr" alt="">'
                    u'<a href="www.archives.valdoise.fr" {target} class="image-link">'
                    u'<img src="http://advaldoise.fr" alt="{alt}">'
                    u'{label}</a></div>').format(
                        target=target, label=label, alt=remove_html_tags(label))
        with self.admin_access.cnx() as cnx:
            self.assertEqual(enhance_accessibility(html, cnx), expected)

    def test_images_remove_alt_content(self):
        """images alt must be relevent"""
        html = (u'<img src="../file/01c12288z2dsd/illustration_1.jpg" alt="illustration_1.jpg" '
                u'width="523" height="371" >')
        expected = (u'<img src="../file/01c12288z2dsd/illustration_1.jpg" alt="" '
                    u'width="523" height="371">')
        with self.admin_access.cnx() as cnx:
            self.assertEqual(enhance_accessibility(html, cnx), expected)

    def test_images_alt_and_title(self):
        """images alt and title must be identical is title is present"""
        html = (u'<img src="../file/01c12288z2dsd/illustration_1.jpg" alt="alt" '
                u'title="title" width="523" height="371" />')
        expected = (u'<img src="../file/01c12288z2dsd/illustration_1.jpg" alt="alt" '
                    u'title="alt" width="523" height="371">')
        with self.admin_access.cnx() as cnx:
            self.assertEqual(enhance_accessibility(html, cnx), expected)

    def test_not_html_node(self):
        with self.admin_access.cnx() as cnx:
            html = u'\xa0<p>tooo</p>'
            self.assertEqual(enhance_accessibility(html, cnx), html)
            html = u'test<p>\xa0</p>'
            self.assertEqual(enhance_accessibility(html, cnx), html)

    def test_process_not_body_node(self):
        with self.admin_access.cnx() as cnx:
            html = u'<body>\xa0<p>tooo</p></body>'
            self.assertEqual(enhance_accessibility(html, cnx, eid=1111), html)


    def test_image_link_class(self):
        """add a specific css class on image-links"""
        html = (u'<a href="www.archives.valdoise.fr" rel="nofollow noopener noreferrer" '
                u'target="_blank" class="toto">'
                u'<img src="../file/01c12288z2dsd/illustration_1.jpg" alt="alt" /></a>')
        expected = (u'<a href="www.archives.valdoise.fr" rel="nofollow noopener noreferrer" '
                    u'target="_blank" class="toto image-link">'
                    u'<img src="../file/01c12288z2dsd/illustration_1.jpg" alt=""></a>')
        with self.admin_access.cnx() as cnx:
            self.assertEqual(enhance_accessibility(html, cnx), expected)

    def test_id_for_anchor(self):
        title = u'Commune de Pierre-Bénite - Archives : communales'
        expected = u'commune-de-pierrebenite--archives--communales'
        self.assertEqual(id_for_anchor(title), expected)


if __name__ == '__main__':
    unittest.main()
