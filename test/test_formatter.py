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

# importing devtools ensures CW's adjust_sys_path is called
# before importing cube
from cubicweb import devtools  # noqa

from cubicweb_francearchives.dataimport import eadreader


def xmlparse(text, parser=etree.XMLParser(remove_blank_text=True)):
    return etree.fromstring(text, parser=parser)


class FormatterMixin(object):
    def assertNodeEqual(self, node1, node2):
        actual_output = etree.tostring(node1)
        expected_output = etree.tostring(node2)
        self.assertEqual(expected_output, actual_output)


class FormatterTests(FormatterMixin, unittest.TestCase):
    def assertTransformEqual(self, expected_output, input_text):
        output = eadreader.html_formatter(xmlparse(input_text))
        self.assertNodeEqual(xmlparse(expected_output), output)

    def test_html_formatting(self):
        ead_source = """<list>
<item>item1</item>
<item>item2</item>
<item>item3</item>
</list>"""
        expected_output = """<div class="ead-wrapper">
<ul class="ead-list-unmarked">
<li>item1</li>
<li>item2</li>
<li>item3</li>
</ul>
</div>"""
        self.assertTransformEqual(expected_output, ead_source)

    def test_html_formatting_with_head(self):
        ead_source = """<list>
<head>Hello</head>
<item>item1</item>
<item>item2</item>
<item>item3</item>
</list>"""
        expected_output = """<div class="ead-wrapper">
<span class="ead-title">Hello</span>
<ul class="ead-list-unmarked">
<li>item1</li>
<li>item2</li>
<li>item3</li>
</ul>
</div>"""
        self.assertTransformEqual(expected_output, ead_source)

    def test_html_formatting_abbr(self):
        ead_source = '<p>Hello <abbr expan="cubicweb.org">cwo</abbr> !</p>'
        expected_output = (
            '<div class="ead-wrapper"><div class="ead-p">Hello '
            '<abbr title="cubicweb.org">cwo</abbr> !</div></div>'
        )
        self.assertTransformEqual(expected_output, ead_source)

    def test_html_formatting_expan(self):
        ead_source = '<p>Hello <expan abbr="cwo">cubicweb.org</expan> !</p>'
        expected_output = (
            '<div class="ead-wrapper"><div class="ead-p">Hello '
            '<span title="cwo">cubicweb.org</span> !</div></div>'
        )
        self.assertTransformEqual(expected_output, ead_source)

    def test_html_formatting_lb(self):
        ead_source = "<p>Hello <lb/> world !</p>"
        expected_output = (
            '<div class="ead-wrapper"><div class="ead-p">Hello ' "<br /> world !</div></div>"
        )
        self.assertTransformEqual(expected_output, ead_source)

    def test_html_formatting_table(self):
        ead_source = """
<table>
  <tgroup cols="4">
    <colspec colnum="1" align="center" colwidth="4cm" colsep="1" colname="anciennecote1"/>
    <colspec colnum="2" align="center" colwidth="4cm" colsep="1" colname="coteactuelle1"/>
    <colspec colnum="3" align="center" colwidth="4cm" colsep="1" colname="anciennecote2"/>
    <colspec colnum="4" align="center" colwidth="4cm" colname="coteactuelle2"/>
    <thead>
      <row valign="middle">
        <entry colname="anciennecote1">Ancienne cote</entry>
        <entry colname="coteactuelle1">Cote actuelle</entry>
        <entry colname="anciennecote2">Ancienne cote</entry>
        <entry colname="coteactuelle2">Cote actuelle</entry>
      </row>
    </thead>
    <tbody>
      <row>
        <entry colname="anciennecote1">1</entry>
        <entry colname="coteactuelle1">Deficit</entry>
        <entry colname="anciennecote2">21B</entry>
        <entry colname="coteactuelle2">11</entry>
      </row>
      <row>
        <entry colname="anciennecote1">2</entry>
        <entry colname="coteactuelle1">Deficit</entry>
        <entry colname="anciennecote2">22</entry>
        <entry colname="coteactuelle2">12</entry>
      </row>
    </tbody>
  </tgroup>
</table>"""
        expected_output = """
<div class="ead-wrapper">
    <table>
        <colgroup>
            <col align="center" />
            <col align="center" />
            <col align="center" />
            <col align="center" />
        </colgroup>
        <thead>
            <tr valign="middle">
                <th align="center" valign="middle">Ancienne cote</th>
                <th align="center" valign="middle">Cote actuelle</th>
                <th align="center" valign="middle">Ancienne cote</th>
                <th align="center" valign="middle">Cote actuelle</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td align="center">1</td>
                <td align="center">Deficit</td>
                <td align="center">21B</td>
                <td align="center">11</td>
            </tr>
            <tr>
                <td align="center">2</td>
                <td align="center">Deficit</td>
                <td align="center">22</td>
                <td align="center">12</td>
            </tr>
        </tbody>
    </table>
</div>"""
        self.assertTransformEqual(expected_output, ead_source)


class XMLReformatTests(FormatterMixin, unittest.TestCase):
    def assertUnnest(self, input_text, expected_output):
        node = xmlparse(input_text)
        eadreader.unnest(node)
        self.assertNodeEqual(xmlparse(expected_output), node)

    def test_unnest_noop(self):
        ead_source = """
<accessrestrict>
  <p>Il n'y a pas de restriction juridique à la consultation de ces
documents, qui se fait selon les modalités matérielles en vigueur au
CHAN.</p>
</accessrestrict>
"""
        expected_output = """
<accessrestrict>
  <p>Il n'y a pas de restriction juridique à la consultation de ces
documents, qui se fait selon les modalités matérielles en vigueur au
CHAN.</p>
</accessrestrict>
        """
        self.assertUnnest(ead_source, expected_output)

    def test_unnest(self):
        ead_source = """
<accessrestrict>
  <head>Modalités d'accès</head>
  <accessrestrict>
    <head>Statut juridique</head>
    <legalstatus>
      Archives publiques
    </legalstatus>
  </accessrestrict>
  <accessrestrict>
    <head>Communicabilité</head>
    <p>Librement consultable pour les actes de plus de 75 ans, sur dérogation pour les actes de moins de 75, publication restreinte aux actes de plus de 100 ans.</p>
  </accessrestrict>
</accessrestrict>
"""  # noqa
        expected_output = """
<accessrestrict>
  <head>Modalités d'accès</head>
  <p class="ead-accessrestrict">
    <head>Statut juridique</head>
    <legalstatus>
      Archives publiques
    </legalstatus>
  </p>
  <p class="ead-accessrestrict">
    <head>Communicabilité</head>
    <p>Librement consultable pour les actes de plus de 75 ans, sur dérogation pour les actes de moins de 75, publication restreinte aux actes de plus de 100 ans.</p>
  </p>
</accessrestrict>
"""  # noqa
        self.assertUnnest(ead_source, expected_output)

    def test_unnest_accruals(self):
        ead_source = """
<accruals>
  <head>Modalités d'accès</head>
  <accruals>
    <head>Statut juridique</head>
    <legalstatus>
      Archives publiques
    </legalstatus>
  </accruals>
  <accruals>
    <head>Communicabilité</head>
    <p>Librement consultable pour les actes de plus de 75 ans, sur dérogation pour les actes de moins de 75, publication restreinte aux actes de plus de 100 ans.</p>
  </accruals>
</accruals>
"""  # noqa
        expected_output = """
<accruals>
  <head>Modalités d'accès</head>
  <p class="ead-accruals">
    <head>Statut juridique</head>
    <legalstatus>
      Archives publiques
    </legalstatus>
  </p>
  <p class="ead-accruals">
    <head>Communicabilité</head>
    <p>Librement consultable pour les actes de plus de 75 ans, sur dérogation pour les actes de moins de 75, publication restreinte aux actes de plus de 100 ans.</p>
  </p>
</accruals>
"""  # noqa
        self.assertUnnest(ead_source, expected_output)


if __name__ == "__main__":
    unittest.main()
