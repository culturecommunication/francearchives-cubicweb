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
from io import StringIO

from lxml import etree

from mock import patch

from os import path as osp


from cubicweb import NoResultError

from cubicweb.devtools.testlib import BaseTestCase, CubicWebTC
from cubicweb.dataimport.stores import RQLObjectStore

from cubicweb_francearchives.testutils import PostgresTextMixin, EADImportMixin
from cubicweb_francearchives.utils import merge_dicts, pick
from cubicweb_francearchives.dataimport import ead, eadreader
from cubicweb_francearchives.dataimport.sqlutil import delete_from_filename

from pgfixtures import setup_module, teardown_module  # noqa


def find_component(cnx, unitid):
    rset = cnx.execute('Any X WHERE X is FAComponent, X did D, '
                       'D unitid %(unitid)s', {'unitid': unitid})
    if rset:
        return rset.one()
    return None


class EADTests(BaseTestCase):

    def test_preprocess_c(self):
        ead_path = self.datapath('FRAD084_IRL000006.xml')
        tree = etree.parse(ead_path)
        self.assertIsNotNone(tree.find('.//c[@id="de-2587"]'))
        clean_tree = eadreader.preprocess_ead(ead_path)
        self.assertIsNone(clean_tree.find('.//c[@id="de-2587"]'))

    def test_preprocess_nested_c(self):
        ead_path = self.datapath('FRAD084_IRL000006.xml')
        tree = etree.parse(ead_path)
        self.assertIsNotNone(tree.find('.//c[@id="tt2-114"]'))
        self.assertIsNotNone(tree.find('.//c[@id="de-2599"]'))
        clean_tree = eadreader.preprocess_ead(ead_path)
        self.assertIsNone(clean_tree.find('.//c[@id="tt2-114"]'))
        self.assertIsNone(clean_tree.find('.//c[@id="de-2599"]'))

    def test_preprocess_dap(self):
        ead_path = self.datapath('FRAD084_IRL000006.xml')
        tree = etree.parse(ead_path)
        self.assertIsNotNone(tree.find('.//dao[@id="dao-internal-test"]'))
        clean_tree = eadreader.preprocess_ead(ead_path)
        self.assertIsNone(clean_tree.find('.//dao[@id="dao-internal-test"]'))

    def test_parse_unitid(self):
        ead_path = self.datapath('FRAN_IR_0261167_excerpt.xml')
        tree = eadreader.preprocess_ead(ead_path)
        did = tree.find('.//dsc//did')
        infos = eadreader.did_infos(did)
        self.assertEqual(infos['unitid'], '20050526/1-20050526/26 - 20050526/1-20050526/6')

    def test_parse_empty_unitid(self):
        ead_path = self.datapath('ir_data/FRAD051_est_ead_affichage.xml')
        tree = eadreader.preprocess_ead(ead_path)
        did = tree.find('.//c[@id="a011497973827MCtiYb"]/did')
        infos = eadreader.did_infos(did)
        self.assertFalse(infos['unitid'])

    def test_html_in_titleproper(self):
        ead_path = self.datapath('FRAN_IR_0261167_excerpt.xml')
        tree = eadreader.preprocess_ead(ead_path)
        header_props = eadreader.eadheader_props(tree.find('eadheader'))
        self.assertEqual(header_props['titleproper'],
                         u"Environnement ; Direction de l'eau (1922-2001)")

    def test_parse_unitdate(self):
        ead_path = self.datapath('FRAN_IR_000224.xml')
        tree = eadreader.preprocess_ead(ead_path)
        reader = eadreader.EADXMLReader(tree)
        self.assertEqual(
            pick(reader.fa_properties['did'], 'unitdate', 'startyear', 'stopyear'),
            {
                'unitdate': u'XIXe-XXe siècles',
                'startyear': 1801,
                'stopyear': 2000,
            })

    def test_parse_date_range(self):
        drange = eadreader.parse_normalized_daterange
        self.assertEqual(drange(None), None)
        self.assertEqual(drange(' '), None)
        self.assertEqual(drange('foo'), None)
        self.assertEqual(drange('82'), {'start': 82, 'stop': 82})
        self.assertEqual(drange('823'), {'start': 823, 'stop': 823})
        self.assertEqual(drange('823 - 1022'), {'start': 823, 'stop': 1022})
        self.assertEqual(drange('  823 -1022  '), {'start': 823, 'stop': 1022})
        self.assertEqual(drange('823 - 102'), {'start': 823, 'stop': 823})
        self.assertEqual(drange('1234/01/02 - 1235/02/03'), {'start': 1234, 'stop': 1235})
        self.assertEqual(drange('1234/01/02-1235/02/03'), {'start': 1234, 'stop': 1235})
        self.assertEqual(drange('1234-01-02 / 1235-02-03'), {'start': 1234, 'stop': 1235})
        self.assertEqual(drange('1234-01-02/1235-02-03'), {'start': 1234, 'stop': 1235})
        self.assertEqual(drange('1801-01-01/2000-12-31'), {'start': 1801, 'stop': 2000})

    def test_ignore_invalid_components(self):
        ead_path = self.datapath('FRAD0XX_00001.xml')
        tree = eadreader.preprocess_ead(ead_path)
        reader = eadreader.EADXMLReader(tree)
        comp_ids = [cnode.get('id') for cnode, cprops in reader.walk()]
        self.assertEqual(comp_ids, ['tt1-1', 'tt2', 'tt2-1', 'tt2-1-3'])


class EADNodropImporterTC(EADImportMixin, PostgresTextMixin, CubicWebTC):
    readerconfig = merge_dicts({},
                               EADImportMixin.readerconfig,
                               {'nodrop': False})

    def test_facomponent_data_ok_with_nodrop(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, self.datapath('FRAN_IR_022409.xml'))
            fa = cnx.find('FindingAid').one()
            self.assertEqual(fa.description, None)
            self.assertEqual(fa.description, None)
            self.assertEqual(fa.bibliography, None)
            scopecontent = (
                u'''<div class="ead-section ead-scopecontent"><div class="ead-wrapper">
         <span class="ead-title">Sommaire</span>
         <div class="ead-p">Enqu&#xEA;te annuelle d&#x2019;entreprise, fichier informatique, 1990. Art 1 : Fichier informatique. Art 2 : Documentation associ&#xE9;e au fichier l&#x2019;acc&#xE8;s &#xE0; une description pr&#xE9;cise de ces documents est assure par l&#x2019;interrogation des fichiers constance</div>
      </div></div>''')  # noqa
            self.assertEqual(fa.scopecontent, scopecontent)


class EADImporterTC(EADImportMixin, PostgresTextMixin, CubicWebTC):

    def test_record_id(self):
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            ar = ce('AuthorityRecord',
                    name=u'Observatoire économique et statistique des transports',
                    record_id=u'FRAN_NP_006883',
                    agent_kind=ce('AgentKind', name=u'bla'))
            cnx.commit()
            self.import_filepath(cnx, self.datapath('FRAN_IR_022409.xml'))
            fa = cnx.find('FindingAid').one()
            rset = cnx.execute(
                'Any R, I, L WHERE FA eid %(fae)s, I index FA, I label L, I role R',
                {'fae': fa.eid}
            )
            self.assertCountEqual(
                [(role, label) for role, _, label in rset.rows], [
                    (u'index', u'transport routier'),
                    (u'index', u'transport maritime'),
                    (u'index', u'transport fluvial'),
                    (u'index', u'transport ferroviaire'),
                    (u'index', u'transport aérien'),
                    (u'index', u'transport'),
                    (u'index', u'entreprise'),
                    (u'originator', u'Observatoire économique et statistique des transports'),
                ])
            originator_eid = [row[1] for row in rset if row[0] == 'originator'][0]
            originator = cnx.entity_from_eid(originator_eid)
            self.assertEqual(originator.authority[0].same_as[0].eid, ar.eid)
            self.assertEqual(originator.label, ar.name)

    def test_facomponent_data(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, self.datapath('FRAN_IR_022409.xml'))
            fa = cnx.find('FindingAid').one()
            self.assertEqual(fa.description, None)
            self.assertEqual(fa.description, None)
            self.assertEqual(fa.bibliography, None)
            scopecontent = (
                u'''<div class="ead-section ead-scopecontent"><div class="ead-wrapper">
         <span class="ead-title">Sommaire</span>
         <div class="ead-p">Enqu&#xEA;te annuelle d&#x2019;entreprise, fichier informatique, 1990. Art 1 : Fichier informatique. Art 2 : Documentation associ&#xE9;e au fichier l&#x2019;acc&#xE8;s &#xE0; une description pr&#xE9;cise de ces documents est assure par l&#x2019;interrogation des fichiers constance</div>
      </div></div>''')  # noqa
            self.assertEqual(fa.scopecontent, scopecontent)

    def test_publicationstmt(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, self.datapath('FRAN_IR_022409.xml'))
            faheader = cnx.find('FAHeader').one()
            self.assertEqual(faheader.titleproper,
                             (u"""Transports ; Enquête annuelle d'entreprises """
                              u"""auprès des entreprises de transport en 1990"""))
            self.assertEqual(faheader.publicationstmt,
                             u'<div class="ead-section ead-publisher">'
                             u'<div class="ead-wrapper">Archives nationales</div></div>\n'
                             u'<div class="ead-section ead-date">'
                             u'<div class="ead-wrapper">1993</div></div>')

    def test_physdesc(self):
        fa_rql = 'Any X WHERE X is FAComponent, X did D, D unitid %(u)s'
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, self.datapath('frad001_0000200j.xml'))
            fa = cnx.execute(fa_rql, {'u': u'200 J 28'}).one()
            did = fa.did[0]
            expected = u'''<div class="ead-section ead-physdesc"><div class="ead-wrapper"><div class="ead-p"><b class="ead-autolabel">Description physique:</b>  &lt;lb&gt;&lt;/lb&gt; </div></div>
<div class="ead-label">Registre</div>
<div class="ead-section ead-physfacet"><div class="ead-wrapper"><div class="ead-p"><b class="ead-autolabel">Registre:</b> Oui</div></div></div></div>'''  # noqa
            self.assertEqual(did.physdesc, expected)

    def test_titlestmt(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, self.datapath('FRAD095_00442.xml'))
            faheader = cnx.find('FAHeader').one()
            expected = (u'''<div class="ead-wrapper"><div>    <h1>Etude notariale de Franconville (1518-1907)</h1>R&#xE9;pertoire num&#xE9;rique.<div>Patrick Clervoy, sous la direction de Patrick Lapalu et Marie-H&#xE9;l&#xE8;ne Peltier, directeur des Archives d&#xE9;partementales du Val-d'Oise</div></div></div>''')  # noqa
            self.assertEqual(faheader.titlestmt, expected)

    def test_embedded_facomponent_dao(self):
        fc_rql = 'Any X WHERE X is FAComponent, X did D, D unitid %(u)s'
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, self.datapath('FRAD095_00374.xml'))
            fc = cnx.execute(fc_rql, {'u': u'3Q7 753 - 893'}).one()
            did = fc.did[0]
            self.assertEqual(did.unittitle, u'Instruments de recherche.')
            self.assertEqual(did.origination,
                             (u'''<div class="ead-wrapper"><div class="ead-p"><b class="ead-autolabel">producteur:</b> Seine-et-Oise. Direction de l'Enregistrement</div></div>'''))  # noqa
            self.assertEqual(fc.scopecontent, None)
            self.assertEqual(len(fc.digitized_versions), 0)
            fc = cnx.execute(fc_rql, {'u': u'3Q7 753 - 773'}).one()
            did = fc.did[0]
            self.assertEqual(did.unittitle,
                             u'Décès, absences et successions : tables alphabétiques.')
            # make sure origination and scopecontent are html-wrapped
            self.assertEqual(did.origination,
                             u'<div class="ead-wrapper"><div class="ead-p">'
                             u'<b class="ead-autolabel">producteur:</b> '
                             u"Seine-et-Oise. Direction de l'Enregistrement</div></div>")
            self.assertTrue(fc.scopecontent.startswith(
                '<div class="ead-section ead-scopecontent">'
                '<div class="ead-wrapper"><div class="ead-p">'))

    def test_facomponent_dao_FRAD085_6(self):
        """specific rules for Vendée"""
        fc_rql = 'Any X WHERE X is FAComponent, X did D, D unitid %(u)s'
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, self.datapath('FRAD085_6Fi.xml'))
            fc = cnx.execute(fc_rql, {'u': u'6 Fi 1130'}).one()
            got = sorted([(d.url, d.illustration_url, d.role)
                          for d in fc.digitized_versions])
            url = (u'http://www.archinoe.net/cg85/visu_serie.php?serie=6Fi&dossier=2Num8/2Num8_126/2Num8_126_001&page=1&pagefin=1')   # noqa
            expected = [(url, u'Fr\\Ad85\\2Num8\\2Num8_126\\2Num8_126_001.jpg', u'thumbnail')]
            self.assertEqual(got, expected)

    def test_facomponent_dao_FRAD085_2C(self):
        """specific rules for Vendée"""
        fc_rql = 'Any X WHERE X is FAComponent, X did D, D unitid %(u)s'
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, self.datapath('FRAD085_2C.xml'))
            fc = cnx.execute(fc_rql, {'u': u'2 C 2'}).one()
            got = sorted([(d.url, d.illustration_url, d.role)
                          for d in fc.digitized_versions])
            url = (u'http://www.archinoe.net/cg85/visu_serie.php?serie=2C&dossier=2Num286/018/2C2&page=1&pagefin=52')   # noqa
            expected = [(url, None, u'répertoire')]
            self.assertEqual(got, expected)
            self.assertEqual(fc.digitized_urls, [url])

    def test_facomponent_dao_FRAD067(self):
        """specific rules for Bas-Rhin"""
        fc_rql = 'Any X WHERE X is FAComponent, X did D, D unitid %(u)s'
        with self.admin_access.cnx() as cnx:
            fpath = 'FRAD067_1_FRAD067_EDF1_archives_paroissiales.xml'
            self.import_filepath(cnx, self.datapath(fpath))
            fc = cnx.execute(fc_rql, {'u': u'2 G'}).one()
            url = 'http://archives.bas-rhin.fr/media/96780/2G0Tabledesparoissesdef.pdf'
            relatedmaterial = (u'<a href="{url}" rel="nofollow noopener noreferrer" '
                               'target="_blank">{url}</a>'.format(url=url))
            self.assertIn(relatedmaterial, fc.additional_resources)

    def test_facomponent_dao_FRAD062(self):
        """Pas de Calais"""
        fc_rql = 'Any X WHERE X is FAComponent, X did D, D unitid %(u)s'
        with self.admin_access.cnx() as cnx:
            fpath = 'FRAD062_ir_9fi_02_permaliens.xml'
            self.import_filepath(cnx, self.datapath(fpath))
            fc = cnx.execute(fc_rql, {'u': u'9 Fi 1'}).one()
            # role image
            url = 'http://archivesenligne.pasdecalais.fr/ark:/64297/5e7c97997adc45bcdafd11b170ae7b11' # noqa
            self.assertTrue(fc.illustration_url, url)
            fc = cnx.execute(fc_rql, {'u': u'9 Fi 2'}).one()
            # role thumbnail
            url = 'http://archivesenligne.pasdecalais.fr/ark:/64297/1a9927cc6cbbe29139031df77d2be48' # noqa
            self.assertTrue(fc.illustration_url, url)

    def test_index_entries_inheritance(self):
        fc_rql = 'Any X WHERE X is FAComponent, X did D, D unitid %(u)s'
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, self.datapath('FRAD095_00374.xml'))
            fc = cnx.execute(fc_rql, {'u': u'3Q7 753 - 893'}).one()
            subjects = [i.label for i in fc.subject_indexes().entities()]
            self.assertCountEqual(subjects, ['ENREGISTREMENT'])
            fc = cnx.execute(fc_rql, {'u': u'3Q7 753 - 773'}).one()
            subjects = [i.label for i in fc.subject_indexes().entities()]
            self.assertCountEqual(subjects, ['ENREGISTREMENT', 'SUCCESSION'])

    def test_geogname_index_entries(self):
        with self.admin_access.cnx() as cnx:
            fc_rql = 'Any X WHERE X is FAComponent, X did D, D unitid %(u)s'
            self.import_filepath(cnx, self.datapath('FRAN_IR_050263.xml'))
            fc = None
            for e in cnx.execute(fc_rql, {
                    'u': u'MC/ET/LXXXVI/1565-MC/ET/LXXXVI/2197 - MC/ET/LXXXVI/1984'}).entities():
                if e.did[0].unittitle.startswith(u'Inventaire après dissolution'):
                    fc = e
            index_entries = [(ie.authority[0].cw_etype, ie.authority[0].label)
                             for ie in fc.reverse_index]
            self.assertCountEqual(
                index_entries,
                [(u'AgentAuthority', u'Hugo, Victor'),
                 (u'SubjectAuthority', u'litt\xe9rature')])

    def test_empty_unitid(self):
        with self.admin_access.cnx() as cnx:
            fc_rql = 'Any X WHERE X is FAComponent, X did D, D unittitle %(u)s'
            fname = 'ir_data/FRAD051_est_ead_affichage.xml'
            self.import_filepath(cnx, self.datapath(fname))
            fc = cnx.execute(fc_rql, {'u': u'1458-1992'}).one()
            self.assertFalse(fc.did[0].unitid)

    def test_findingaid_bioghist(self):
        with self.admin_access.cnx() as cnx:
            fname = 'ir_data/FRAD051_est_ead_affichage.xml'
            self.import_filepath(cnx, self.datapath(fname))
            fa = cnx.execute('Any X WHERE X is FindingAid').one()
            expected = '<div class="ead-p">bioghist: A concise essay or chronology'
            self.assertIn(expected, fa.bioghist)

    def test_facomponent_physdesc(self):
        with self.admin_access.cnx() as cnx:
            fname = 'ir_data/FRAD051_est_ead_affichage.xml'
            self.import_filepath(cnx, self.datapath(fname))
            fc_rql = 'Any X WHERE X is FAComponent, X did D, D unittitle %(u)s'
            fc = cnx.execute(fc_rql, {'u': u'1458-1992'}).one()
            for label in ('label extent', 'dimensions_label'):
                self.assertIn(label, fc.did[0].physdesc)

    def test_facomponent_materialspec(self):
        with self.admin_access.cnx() as cnx:
            fname = 'ir_data/FRAD051_est_ead_affichage.xml'
            self.import_filepath(cnx, self.datapath(fname))
            fc_rql = 'Any X WHERE X is FAComponent, X did D, D unittitle %(u)s'
            fc = cnx.execute(fc_rql, {'u': u'1458-1992'}).one()
            for label in ('<b class="ead-label">Mathematical Data:</b>',
                          '<b class="ead-label">Scale:</b> 1:10000</div>',
                          '<b class="ead-label">Projection:</b>'):
                self.assertIn(label, fc.did[0].materialspec)

    def test_facomponent_notes(self):
        with self.admin_access.cnx() as cnx:
            fname = 'ir_data/FRAD051_est_ead_affichage.xml'
            self.import_filepath(cnx, self.datapath(fname))
            fc_rql = 'Any X WHERE X is FAComponent, X did D, D unittitle %(u)s'
            fc = cnx.execute(fc_rql, {'u': u'1458-1992'}).one()
            expected = '''<div class="ead-wrapper">
                    <ul class="ead-list-unmarked"><li>odd, item = Department of Economic Affairs: Industrial Policy Group:
                            Registered Files (1-IG and 2-IG Series) EW 26
                        </li><li>item = Department of Economic Affairs: Industrial Division and
                            Industrial Policy Division: Registered Files (IA Series) EW 27
                        </li></ul>
                </div>'''  # noqa
            self.assertEqual(expected, fc.notes)

    def test_findingaid_changes(self):
        with self.admin_access.cnx() as cnx:
            fname = 'ir_data/FRAD051_est_ead_affichage.xml'
            self.import_filepath(cnx, self.datapath(fname))
            fa = cnx.execute('Any X WHERE X is FindingAid').one()
            self.assertIn('May 5, 1997', fa.fa_header[0].changes)
            expected = u'This electronic finding aid was updated to'
            self.assertIn(expected, fa.fa_header[0].changes)

    def test_findingaid_notes(self):
        with self.admin_access.cnx() as cnx:
            fname = 'ir_data/FRAD051_est_ead_affichage.xml'
            self.import_filepath(cnx, self.datapath(fname))
            fa = cnx.execute('Any X WHERE X is FindingAid').one()
            expected = '''<div class="ead-wrapper">
            <ul class="ead-list-unmarked"><li>odd. item. Department of Economic Affairs: Industrial Policy Group: Registered
                    Files (1-IG and 2-IG Series) EW 26
                </li><li>Department of Economic Affairs: Industrial Division and Industrial Policy
                    Division: Registered Files (IA Series) EW
                        27
                </li></ul>
        </div>'''  # noqa
            self.assertEqual(expected, fa.notes)

    def test_facomponent_genreform(self):
        with self.admin_access.cnx() as cnx:
            fname = 'ir_data/FRAD051_est_ead_affichage.xml'
            self.import_filepath(cnx, self.datapath(fname))
            fc_rql = 'Any X WHERE X is FAComponent, X did D, D unittitle %(u)s'
            fc = cnx.execute(fc_rql, {'u': u'1458-1992'}).one()
            self.assertEqual(fc.genreform, 'genreform')

    def test_facomponent_function(self):
        with self.admin_access.cnx() as cnx:
            fname = 'ir_data/FRAD051_est_ead_affichage.xml'
            self.import_filepath(cnx, self.datapath(fname))
            fc_rql = 'Any X WHERE X is FAComponent, X did D, D unittitle %(u)s'
            fc = cnx.execute(fc_rql, {'u': u'1458-1992'}).one()
            self.assertEqual(fc.function, 'function')

    def test_facomponent_occupation(self):
        with self.admin_access.cnx() as cnx:
            fname = 'ir_data/FRAD051_est_ead_affichage.xml'
            self.import_filepath(cnx, self.datapath(fname))
            fc_rql = 'Any X WHERE X is FAComponent, X did D, D unittitle %(u)s'
            fc = cnx.execute(fc_rql, {'u': u'1458-1992'}).one()
            self.assertEqual(fc.occupation, 'occupation')

    def test_services_normalization(self):
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity('Service', category=u'?',
                                        name=u'Les Archives Nationales',
                                        short_name=u'Les AN',
                                        code=u'fran')
            cnx.commit()
            self.import_filepath(cnx, self.datapath('FRAN_IR_022409.xml'), {
                'name': u'Les AN',
                'eid': service.eid,
                'code': u'FRAN',
            })
            fa = cnx.find('FindingAid').one()
            self.assertEqual(fa.related_service.eid, service.eid)
            self.assertEqual(fa.publisher, 'Les AN')

    def test_subject_index_creation(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, self.datapath('FRAN_IR_0261167_excerpt.xml'))
            self.assertEqual(len(cnx.find('Subject')), 5)
            fa = cnx.find('FindingAid').one()
            subjects = [i.label for i in fa.subject_indexes().entities()]
            self.assertCountEqual(subjects, [
                u'poisson',
                u'pisciculture',
                u'aquaculture',
            ])
            comp = cnx.find('FAComponent').one()
            subjects = [i.label for i in comp.subject_indexes().entities()]
            self.assertCountEqual(subjects, [
                u'Poisson',
                u'petits poissons',
                # + inherited index entries
                u'pisciculture',
                u'aquaculture',
                u'poisson',
            ])

    def test_location_index_creation(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, self.datapath('FRAN_IR_0261167_excerpt.xml'))
            self.assertEqual(len(cnx.find('Geogname')), 2)
            fa = cnx.find('FindingAid').one()
            locations = [i.label for i in fa.geo_indexes().entities()]
            self.assertCountEqual(locations, [
                u"garonne (cours d'eau)",
            ])
            comp = cnx.find('FAComponent').one()
            locations = [i.label for i in comp.geo_indexes().entities()]
            self.assertCountEqual(locations, [
                u"garonne (cours d'eau)",
                u"Garonne (cours d'eau)",
            ])

    def test_findingaid_data(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, self.datapath('FRAD095_00259.XML'))
            fa = cnx.find('FindingAid').one()
            self.assertEqual(fa.eadid, u'FRAD095_00259')
            self.assertEqual(fa.description, None)
            self.assertEqual(fa.bibliography, None)
            self.assertEqual(fa.acquisition_info, None)
            self.assertEqual(fa.scopecontent, None)
            did = fa.did[0]
            self.assertEqual(did.materialspec, None)
            origination = (
                u'<div class="ead-wrapper"><div class="ead-p">'
                u'<b class="ead-autolabel">producteur:</b> '
                u'PRODUCTEURS MULTIPLES</div></div>')
            self.assertEqual(did.origination, origination)

    def test_findingaid_data_FRAD09_1r(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, self.datapath('FRAD090_1r_retoucheFA.xml'))
            fa = cnx.find('FindingAid').one()
            self.assertEqual(fa.eadid, u'archref')
            self.assertEqual(fa.did[0].unitid, u'unitid: 1 R 109-277')
            self.assertIn(u"archives administratives militaires (BCAAM)",
                          fa.acquisition_info)
            self.assertIn(u"loi du 15 juillet 2008",
                          fa.accessrestrict)
            self.assertIn(u"imprimante personnelle ou en salle de lecture",
                          fa.userestrict)
            self.assertIn('anonyme, 38 p. Alouette',
                          fa.additional_resources)  # otherfindaid
            self.assertIn('Territoire de Belfort avant 1870',
                          fa.additional_resources)  # separatedmaterial
            self.assertIn(u'Q pour les Biens nationaux',
                          fa.additional_resources)  # relatedmaterial

    def test_authority_in_es_docs(self):
        with self.admin_access.cnx() as cnx:
            es_docs = self.import_filepath(cnx, self.datapath('FRAN_IR_0261167_excerpt.xml'))
            aa = cnx.find('AgentAuthority', label=u"Direction de l'eau").one()
            self.assertEqual(len(es_docs), 2)
            fa_es_doc, comp_es_doc = es_docs
            self.assertEqual(
                aa.eid,
                [
                    i for i in fa_es_doc['_source']['index_entries']
                    if i['label'] == "Direction de l'eau"
                ][0]['authority']
            )

    def test_agent_index_creation(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, self.datapath('FRAN_IR_0261167_excerpt.xml'))
            self.assertEqual(len(cnx.find('AgentName')), 4)
            fa = cnx.find('FindingAid').one()
            agents = [i.label for i in fa.agent_indexes().entities()]
            self.assertCountEqual(agents, [
                u"Jean-Michel",
                u"Direction de l'eau",
            ])
            comp = cnx.find('FAComponent').one()
            agents = [i.label for i in comp.agent_indexes().entities()]
            self.assertCountEqual(agents, [
                u"Jean-Michel",
                u"jean-Michel",
                u"Jean-Paul",
            ])

    def test_singleton_bibliography_div(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, self.datapath('FRAD095_00442.xml'))
            fa = cnx.find('FindingAid').one()
            self.assertFalse(fa.bibliography)

    def test_singleton_arrangement_div(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, self.datapath('FRAD095_00442.xml'))
            fa = cnx.find('FindingAid').one()
            expected = (u'<div class="ead-section ead-arrangement">'
                        '<div class="ead-wrapper"><div class="ead-p">'
                        'Classement chronologique</div></div></div>')
            self.assertIn(expected, fa.description)

    def test_singleton_accruals_div(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, self.datapath('FRAD095_00442.xml'))
            fa = cnx.find('FindingAid').one()
            expected = (
                u"""<div class="ead-section ead-accruals">"""
                """<div class="ead-wrapper"><div class="ead-p">"""
                """Fonds ouvert susceptible d'accroissement</div></div></div>""")
            self.assertIn(expected, fa.description)

    def test_singleton_appraisal_div(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, self.datapath('FRAD095_00442.xml'))
            fa = cnx.find('FindingAid').one()
            expected = (
                u'<div class="ead-section ead-appraisal">'
                '<div class="ead-wrapper"><div class="ead-p">'
                'Aucun</div></div></div>')
            self.assertIn(expected, fa.description)

    def test_concept_alignment(self):
        with self.admin_access.cnx() as cnx:
            scheme = cnx.create_entity('ConceptScheme', title=u'thesaurus W')
            c1 = cnx.create_entity('Concept', in_scheme=scheme)
            cnx.create_entity('Label', label=u'hip', language_code=u'fr',
                              kind=u'preferred', label_of=c1)
            c2 = cnx.create_entity('Concept', in_scheme=scheme, broader_concept=c1)
            cnx.create_entity('Label', label=u'hop', language_code=u'fr',
                              kind=u'preferred', label_of=c2)
            cnx.create_entity('Label', label=u'poIssON', language_code=u'fr',
                              kind=u'alternative', label_of=c2)
            cnx.commit()
            self.import_filepath(cnx, self.datapath('FRAN_IR_0261167_excerpt.xml'))
            same_as_rset = cnx.execute('Any X WHERE X is SubjectAuthority, X same_as C')
            self.assertEqual(len(same_as_rset), 2)
            poisson = cnx.find('SubjectAuthority', label=u'Poisson').one()
            self.assertEqual(poisson.same_as[0].eid, c2.eid)

    def test_dao(self):
        url = u'https://www.siv.archives-nationales.culture.gouv.fr/mm/media/download/FRDAFAN85_OF9v173541_L-min.jpg' # noqa
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, self.datapath('FRAN_IR_051016_excerpt.xml'))
            fc = cnx.find('FAComponent', component_order=0).one()
            self.assertEqual(len(fc.digitized_versions), 2)
            self.assertEqual(fc.illustration_url, url)

    def test_daogrp(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, self.datapath('FRAD095_00374.xml'))
            comp = find_component(cnx, u'3Q7 1 - 752')
            self.assertEqual(len(comp.digitized_versions), 0)
            comp = find_component(cnx, u'3Q7 1 - 7')
            self.assertEqual(len(comp.digitized_versions), 0)
            comp = find_component(cnx, u'3Q7 753')
            dv_urls = [dv.illustration_url for dv in comp.digitized_versions]
            self.assertCountEqual(dv_urls, [
                '/FRAD095_00374/FRAD095_3Q7_753/FRAD095_3Q7_753_0001.jpg',
                '/FRAD095_00374/FRAD095_3Q7_753/FRAD095_3Q7_753_0091.jpg',
            ])
            comp = find_component(cnx, u'3Q7 754')
            dv_urls = [dv.illustration_url for dv in comp.digitized_versions]
            self.assertCountEqual(dv_urls, [
                '/FRAD095_00374/FRAD095_3Q7_754/FRAD095_3Q7_754_0001.jpg',
                '/FRAD095_00374/FRAD095_3Q7_754/FRAD095_3Q7_754_0111.jpg',
            ])
            comp = find_component(cnx, u'3Q7 755')
            dv_urls = [dv.illustration_url for dv in comp.digitized_versions]
            self.assertCountEqual(dv_urls, [
                '/FRAD095_00374/FRAD095_3Q7_755/FRAD095_3Q7_755_0001.jpg',
                '/FRAD095_00374/FRAD095_3Q7_755/FRAD095_3Q7_755_0048.jpg',
            ])

    def test_component_order(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, self.datapath('FRAN_IR_051016_excerpt.xml'))
            fac_unitids = sorted((comp.component_order, comp.did[0].unitid)
                                 for comp in cnx.find('FAComponent').entities())
            self.assertEqual(fac_unitids, [
                (0, u'19860711/412-19860711/415 - 19860711/412'),
                (1, u'19860711/412-19860711/411 - 19860711/409'),
            ])

    def test_pdf_metadata(self):
        with self.admin_access.cnx() as cnx:
            es_doc = self.import_filepath(cnx, self.datapath('FRSHD_PUB_00000345_0001.pdf'))[0]
            fa = cnx.find('FindingAid').one()
            rset = cnx.find('SubjectAuthority', label=u'Journal des marches et opérations (JMO)')
            self.assertEqual(len(rset), 1)
            index_entries = es_doc['_source']['index_entries']
            self.assertEqual(len(index_entries), 1)
            self.assertEqual(index_entries[0],
                             {'type': 'subject',
                              'normalized': u'des et jmo journal marches operations',
                              'label': u'Journal des marches et opérations (JMO)',
                              'role': u'index', 'authority': rset.one().eid,
                              'authfilenumber': None})
            self.assertEqual(fa.dc_title(),
                             u"[Archives de l'armée de Terre]. Inventaire des archives "
                             u"de commandement et journaux des marches et opérations des "
                             u"formations de l’armée de terre. Sous-série GR 7 U (1946-1964).")
            self.assertEqual(fa.did[0].startyear, 1946)
            self.assertEqual(fa.did[0].stopyear, 1964)
            self.assertEqual(fa.did[0].physdesc, None)
            self.assertEqual(fa.did[0].lang_description, None)
            self.assertIn(u'Service historique', fa.did[0].origination)

    def test_nonregr_unittile_not_null(self):
        """unittitle should not be null: use unitdata instead (cf. #58785477)"""
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx,
                                 self.datapath('ir_data/FRANOM_01250_excerpt.xml'))
            title = cnx.execute('Any DT WHERE D is Did, D unitid %(id)s, D unittitle DT',
                                {'id': u'FR ANOM 91 / 2 M 242 a'})[0][0]
            self.assertEqual(title, u'1845-1898')

    def test_extptr_when_ark_is_specified(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx,
                                 self.datapath('ir_data/FRANOM_01250_excerpt.xml'))
            extpr = cnx.execute('Any X WHERE D extptr X, D unitid %(id)s',
                                {'id': u'FR ANOM 91 / 2 M 242 a'})[0][0]
            self.assertEqual(extpr, u'ark:/61561/kd508auuzxb')

    def test_ape_ead_path(self):
        with self.admin_access.cnx() as cnx:
            filepath = self.datapath('ir_data/v1/FRAD095_00374.xml')
            self.import_filepath(cnx, filepath)
            fa = cnx.find('FindingAid').one()
            self.assertEqual(len(fa.ape_ead_file), 1)
            ape_filepath = cnx.execute(
                'Any FSPATH(D) WHERE X ape_ead_file F, F data D, X eid %(x)s',
                {'x': fa.eid})[0][0].getvalue()
            self.assertEqual(ape_filepath,
                             self.datapath('tmp/ape-ead/FRAD095/ape-FRAD095_00374.xml'))

    def test_index_authorities(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, self.datapath('FRAC95300_1DHP_rpnum_001.xml'))
            fa = cnx.find('FindingAid').one()
            for itype in ('persname', 'corpname', 'name', 'famname', 'geogname'):
                agents = list(fa.main_indexes(itype).entities())
                self.assertEqual(len(agents), 0)

    def test_import_findingaid_bioghist(self):
        with self.admin_access.cnx() as cnx:
            filepath = self.datapath('ir_data/FRMAEE/FRMAEE_0001MA030.xml')
            self.import_filepath(cnx, filepath)
            fa = cnx.find('FindingAid').one()
            expected = u'Rabat le 28 mai 1947'
            self.assertIn(expected, fa.bioghist)

    def test_import_findingaid_fa_support(self):
        with self.admin_access.cnx() as cnx:
            filepath = self.datapath('ir_data/FRMAEE/FRMAEE_0001MA030.xml')
            self.import_filepath(cnx, filepath)
            fa = cnx.find('FindingAid').one()
            fa_support_filepath = cnx.execute(
                'Any FSPATH(D) WHERE X findingaid_support F, F data D, X eid %(x)s',
                {'x': fa.eid})[0][0].getvalue()
            self.assertEqual(fa_support_filepath, filepath)

    def test_import_findingaid_referenced_files(self):
        with self.admin_access.cnx() as cnx:
            filepath = self.datapath('ir_data/FRMAEE/FRMAEE_0001MA030.xml')
            self.import_filepath(cnx, filepath)
            fa = cnx.find('FindingAid').one()
            sha1_maroc = u'c7e79ea17f70586cb16c723b06832a7d9154fa20'
            maroc = '{}/FRMAEE_MN_179CPCOM_Maroc.pdf'.format(sha1_maroc)
            sha1_61 = u'05651f43e045d343c3d220950b7b060978e3c322'
            f61 = '{}/9BIP_1914-1961.pdf'.format(sha1_61)
            f1, f2, f3, f4 = fa.fa_referenced_files
            self.assertCountEqual([f.data_sha1hex for f in fa.fa_referenced_files],
                                  [sha1_maroc] * 3 + [sha1_61])
            for fsha1 in [maroc, f61]:
                expected = '<a href="../file/{}"'.format(fsha1)
                self.assertIn(expected, fa.additional_resources)
            fac = cnx.find('FAComponent').one()
            sha1_91 = u'e5d25c18f08e3e4a0d15d360dc2b7bfad86832d9'
            f91 = '{}/FRMAEE_1BIP_1919-1994.pdf'.format(sha1_91)
            self.assertCountEqual([f.data_sha1hex for f in fac.fa_referenced_files],
                                  [sha1_91, sha1_maroc, sha1_61])
            for fsha1 in [f91]:
                expected = '<a href="../file/{}"'.format(f91)
                self.assertIn(expected, fac.additional_resources)
            self.assertEqual(cnx.find('File').rowcount, 9)

    def test_import_relfiles(self):
        with self.admin_access.cnx() as cnx:
            self.assertFalse(cnx.execute('Any X WHERE X is File'))
            filepath = self.datapath('ir_data/FRMAEE/FRMAEE_0001MA030.xml')
            self.import_filepath(cnx, filepath)
            filepath = self.datapath('ir_data/FRMAEE/RELFILES/FRMAEE_1BIP_1919-1994.pdf')
            self.import_filepath(cnx, filepath)
            self.assertEqual(len(cnx.find('FindingAid')), 1)
            self.assertEqual(len(cnx.find('FAComponent')), 1)

    def test_import_relfiles_symlink(self):
        with self.admin_access.cnx() as cnx:
            filepath = self.datapath('ir_data/FRMAEE/FRMAEE_0001MA030.xml')
            self.import_filepath(cnx, filepath)
            rset = cnx.execute(
                'Any S, FSPATH(D) LIMIT 1 WHERE F data_sha1hex S, '
                'X fa_referenced_files F, F data D')
            data_sha1hex = rset[0][0]
            pdfpath = rset[0][1].getvalue()
            self.assertTrue(pdfpath.endswith(
                '179CPCOM_Maroc.pdf'))
            destpath = osp.join(self.config['appfiles-dir'],
                                '{}_{}'.format(data_sha1hex,
                                               osp.basename(pdfpath)))
            self.assertNotEqual(destpath, pdfpath)
            self.assertTrue(osp.isfile(destpath))
            self.assertTrue(osp.islink(destpath))

    def test_import_pdffiles(self):
        with self.admin_access.cnx() as cnx:
            self.assertFalse(cnx.execute('Any X WHERE X is File'))
            filepath = self.datapath('ir_data/FRMAEE/FRMAEE_0001MA030.xml')
            self.import_filepath(cnx, filepath)
            filepath = self.datapath('ir_data/FRMAEE/PDF/FRMAEE_1BIP_1919-1994.pdf')
            self.import_filepath(cnx, filepath)
            self.assertEqual(len(cnx.find('FindingAid')), 2)
            self.assertEqual(len(cnx.find('FAComponent')), 1)

    def test_import_pdffiles_symlink(self):
        """test than the symlink to the appfiles-dir is set for the pdf file

        """
        with self.admin_access.cnx() as cnx:
            filepath = self.datapath('ir_data/FRMAEE/PDF/FRMAEE_1BIP_1919-1994.pdf')
            self.import_filepath(cnx, filepath)
            pdffile = cnx.execute(
                'Any F WHERE X findingaid_support F').one()
            destpath = osp.join(self.config['appfiles-dir'],
                                '{}_{}'.format(pdffile.data_sha1hex,
                                               osp.basename(filepath)))
            self.assertNotEqual(destpath, filepath)
            self.assertTrue(osp.isfile(destpath))
            self.assertTrue(osp.islink(destpath))

    def test_imported_authority_in_es_docs(self):
        """Test that index_entires are correcty set in esdoc for imported PDFs"""
        with self.admin_access.cnx() as cnx:
            cnx.create_entity('Service', code=u'FRANMT', category=u'foo')
            cnx.create_entity(
                'LocationAuthority', label=u'Dunkerque (Nord, France)'
            )
            cnx.commit()
            filepath = self.datapath('ir_data/FRANMT/PDF/FRANMT_3_AQ_INV.pdf')
            es_docs = self.import_filepath(cnx, filepath, {'code': 'FRANMT'})
            self.assertEqual(1, len(cnx.find('FindingAid')))
            for es_doc in es_docs:
                self.assertIn('index_entries', es_doc['_source'].keys())
                for index_entry in es_doc['_source']['index_entries']:
                    self.assertIn('authority', index_entry)
                    self.assertIn('role', index_entry)


class EADreImportTC(EADImportMixin, PostgresTextMixin, CubicWebTC):
    readerconfig = merge_dicts({},
                               EADImporterTC.readerconfig,
                               {'reimport': True,
                                'nodrop': False,
                                'force_delete': True})

    def test_index_reimport(self):
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity('Service', category=u'?',
                                        name=u'Les Archives Nationales',
                                        short_name=u'Les AN',
                                        code=u'fran')
            cnx.commit()
            kwargs = {
                'name': u'Les AN',
                'eid': service.eid,
                'code': u'FRAN',
            }
            fpath = 'FRAN_IR_050263.xml'
            self.import_filepath(cnx, self.datapath(fpath), kwargs)
            hugo = cnx.execute(
                'Any X WHERE X is AgentAuthority, X label %(l)s',
                {'l': u'Hugo, Victor'}).one()
            self.assertEqual(len(hugo.reverse_authority[0].index), 1)
            # reimport the same file
            self.import_filepath(cnx, self.datapath(fpath), kwargs)
            # we shell have only one AgentAuthority for Hugo, Victor
            new_hugo = cnx.execute(
                'Any X WHERE X is AgentAuthority, X label %(l)s',
                {'l': u'Hugo, Victor'}).one()
            self.assertEqual(hugo.eid, new_hugo.eid)

    def test_files_after_reimport(self):
        """reimport a version of FRMAEE_0001MA030.xml without
           `fa_references_files` and check that old files are deleted"""
        with self.admin_access.cnx() as cnx:
            self.assertFalse(cnx.find('File').rowcount)
            filepath = self.datapath('ir_data/FRMAEE/FRMAEE_0001MA030.xml')
            self.import_filepath(cnx, filepath)
            fa = cnx.find('FindingAid').one()
            self.assertEqual(
                [f.data_name for f in fa.fa_referenced_files],
                [u'9BIP_1914-1961.pdf'] + [u'FRMAEE_MN_179CPCOM_Maroc.pdf'] * 3)
            fac = cnx.find('FAComponent').one()
            self.assertCountEqual(
                [f.data_name for f in fac.fa_referenced_files],
                [u'FRMAEE_1BIP_1919-1994.pdf', u'9BIP_1914-1961.pdf',
                 u'FRMAEE_MN_179CPCOM_Maroc.pdf'])
            deleted_files = dict((f[0], f[1].getvalue()) for f in cnx.execute(
                'Any F, FSPATH(D) WHERE X fa_referenced_files F,  F data D'))
            # ead.xml, ape.xml + 4 fa pdf + 3 fac pdf
            self.assertEqual(cnx.find('File').rowcount, 9)
            # reimport a new version
            filepath = self.datapath('ir_data/FRMAEE_v2/FRMAEE_0001MA030.xml')
            self.import_filepath(cnx, filepath)
            fa = cnx.find('FindingAid').one()
            self.assertFalse(fa.fa_referenced_files)
            fac = cnx.find('FAComponent').one()
            self.assertEqual(
                [f.data_name for f in fac.fa_referenced_files],
                [u'FRMAEE_1BIP_1919-1994.pdf', u'FRMAEE_MN_179CPCOM_Maroc.pdf'])
            # ead.xml, ape.xml + 0 fa pdf + 2 fac pdf
            self.assertEqual(cnx.find('File').rowcount, 4)
            for eid, path in deleted_files.items():
                self.assertTrue(osp.exists(path))
                # but not in db
                with self.assertRaises(NoResultError):
                    cnx.find('File', eid=eid).one()

    def test_reimport_findingaid_referenced_files(self):
        with self.admin_access.cnx() as cnx:
            self.assertFalse(cnx.execute('Any X WHERE X is File'))
            filepath = self.datapath('ir_data/FRMAEE/FRMAEE_0001MA030.xml')
            self.import_filepath(cnx, filepath)
            fa = cnx.find('FindingAid').one()
            fa_support = fa.findingaid_support[0]
            fa_ead = fa.ape_ead_file[0]
            f1, f2, f3, f4 = fa.fa_referenced_files
            fac = cnx.find('FAComponent').one()
            self.assertEqual(len(fac.fa_referenced_files), 3)
            # reimport the same file
            self.import_filepath(cnx, filepath)
            new_fa = cnx.find('FindingAid').one()
            self.assertEqual(len(new_fa.fa_referenced_files), 4)
            self.assertEqual(
                cnx.execute('Any COUNT(X) WHERE X is File')[0][0], 9)
            self.assertNotEqual(fa.eid, new_fa.eid)
            # enshure old files are deleted:
            for eid in (fa_support.eid, fa_ead.eid,
                        f1.eid, f2.eid, f3.eid, f4.eid):
                with self.assertRaises(NoResultError):
                    cnx.find('File', eid=eid).one()

    def test_failed_reimport(self):
        """tests that a previously imported FindingAid is not deleted after a failed
reimport"""
        with self.admin_access.cnx() as cnx:
            filepath = self.datapath('ir_data/FRMAEE_OK/FRMAEE_0001MA001.xml')
            self.import_filepath(cnx, filepath)
            fa = cnx.find('FindingAid').one()
            filepath = self.datapath('ir_data/FRMAEE_KO/FRMAEE_0001MA001.xml')
            # ensure the second file has errors
            with self.assertRaises(Exception):
                etree.parse(filepath)
            # import the erroneous file
            self.import_filepath(cnx, filepath)
            # the previously imported FindingAid is still there
            self.assertEqual(fa.eid, cnx.find('FindingAid').one().eid)


class EADFullMigrationTC(EADImportMixin, PostgresTextMixin, CubicWebTC):
    """tests for full data reimport"""
    readerconfig = merge_dicts({},
                               EADImporterTC.readerconfig,
                               {'autodedupe_authorities': 'global/normalize',
                                'esonly': 0,
                                'force_delete': False,
                                'index-name': 'cms',
                                'nodrop': 0, 'noes': True})

    def test_authorities(self):
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity('Service', category=u'?',
                                        name=u'Les Archives Nationales',
                                        short_name=u'Les AN',
                                        code=u'fran')
            cnx.commit()
            kwargs = {
                'name': u'Les AN',
                'eid': service.eid,
                'code': u'FRAN',
            }
            fpath = 'FRAN_IR_050263.xml'
            self.import_filepath(cnx, self.datapath(fpath), kwargs)
            authority_eids = cnx.execute(
                'Any X WHERE X is IN (AgentAuthority, '
                'SubjectAuthority, LocationAuthority)').rows
            index_rql = 'Any X WHERE X index Y'
            self.assertEqual(30, cnx.execute(index_rql).rowcount)
            delete_from_filename(cnx, fpath, interactive=False,
                                 esonly=False)

            cnx.commit()
            self.assertEqual(0, cnx.execute(index_rql).rowcount)
            self.import_filepath(cnx, self.datapath(fpath), kwargs)
            self.assertEqual(30, cnx.execute(index_rql).rowcount)
            # we shell still have the same authorities
            new_authority_eids = cnx.execute(
                'Any X WHERE X is IN (AgentAuthority, '
                'SubjectAuthority, LocationAuthority)').rows
            self.assertCountEqual(new_authority_eids, authority_eids)


class ESOnlyTests(PostgresTextMixin, CubicWebTC):

    @property
    def readerconfig(self):
        return {
            'esonly': True,
            'index-name': 'dummy',
            'appid': 'data',
            'appfiles-dir': self.datapath(),
        }

    def setup_database(self):
        # add FindingAId / FAcomponent matching stable ids of
        # FRAN_IR_0261167_excerpt.xml
        with self.admin_access.cnx() as cnx:
            did1 = cnx.create_entity('Did', unitid=u'did1', unittitle=u'title1')
            fa = cnx.create_entity('FindingAid', name=u'fa', eadid=u'fa',
                                   stable_id=u'c4b17d67cb5e8e884590ab98a864c81d48239053',
                                   publisher=u'FRAN',
                                   fa_header=cnx.create_entity('FAHeader'),
                                   did=did1)
            did2 = cnx.create_entity('Did', unitid=u'did2', unittitle=u'title2')
            comp = cnx.create_entity('FAComponent',
                                     stable_id=u'c97f63529b4450e34b8c548d0e97b063bfa8e4bd',
                                     did=did2,
                                     finding_aid=fa)
            cnx.commit()
            self.fa_eid = fa.eid
            self.comp_eid = comp.eid

    def import_filepath(self, cnx, filepath):
        store = RQLObjectStore(cnx)
        r = ead.Reader(self.readerconfig, store)
        return r.import_filepath(filepath, ead.load_services_map(cnx))

    def test_esonly_indexation(self):
        with self.admin_access.cnx() as cnx:
            es_docs = self.import_filepath(cnx,
                                           self.datapath('FRAN_IR_0261167_excerpt.xml'))
            self.assertEqual(len(es_docs), 2)
            fa_es_doc, comp_es_doc = es_docs
            self.assertEqual(fa_es_doc['_id'],
                             'c4b17d67cb5e8e884590ab98a864c81d48239053')
            self.assertEqual(fa_es_doc['_source']['eid'], self.fa_eid)
            self.assertEqual(comp_es_doc['_id'],
                             'c97f63529b4450e34b8c548d0e97b063bfa8e4bd')
            self.assertEqual(comp_es_doc['_source']['eid'], self.comp_eid)

    def test_html_strip(self):
        with self.admin_access.cnx() as cnx:
            es_docs = self.import_filepath(cnx,
                                           self.datapath('FRAN_IR_0261167_excerpt.xml'))
            self.assertEqual(len(es_docs), 2)
            fa_es_doc, comp_es_doc = es_docs
            self.assertEqual(comp_es_doc['_id'],
                             'c97f63529b4450e34b8c548d0e97b063bfa8e4bd')
            self.assertEqual(comp_es_doc['_source']['description'], 'Coucou tout le monde')

    def test_authority_in_es_index_docs(self):
        with self.admin_access.cnx() as cnx:
            es_docs = self.import_filepath(cnx, self.datapath('FRAN_IR_0261167_excerpt.xml'))
            self.assertEqual(len(es_docs), 2)
            fa_es_doc, comp_es_doc = es_docs
            self.assertIsNone(
                [
                    i for i in fa_es_doc['_source']['index_entries']
                    if i['label'] == "Direction de l'eau"
                ][0]['authority']
            )

    def test_originators_in_facomp_docs(self):
        with self.admin_access.cnx() as cnx:
            es_docs = self.import_filepath(cnx,
                                           self.datapath('FRAN_IR_0261167_excerpt.xml'))
            self.assertEqual(len(es_docs), 2)
            fa_es_doc, comp_es_doc = es_docs
            self.assertEqual(fa_es_doc['_source']['originators'],
                             ["Direction de l'eau"])
            self.assertEqual(comp_es_doc['_source']['originators'],
                             ["Direction de l'eau"])


class ReimportESonlyTests(EADImportMixin, PostgresTextMixin, CubicWebTC):
    readerconfig = merge_dicts({}, EADImportMixin.readerconfig, {'esonly': True})

    def test_authority_in_es_index_docs(self):
        with self.admin_access.cnx() as cnx:
            self.readerconfig = dict(self.readerconfig, esonly=False)
            es_docs = self.import_filepath(cnx, self.datapath('FRAN_IR_0261167_excerpt.xml'))
            self.readerconfig = dict(self.readerconfig, esonly=True)
            firstaa = cnx.find('AgentAuthority', label=u"Direction de l'eau").one()
        with self.admin_access.cnx() as cnx:
            es_docs = self.import_filepath(cnx, self.datapath('FRAN_IR_0261167_excerpt.xml'))
            secondaa = cnx.find('AgentAuthority', label=u"Direction de l'eau").one()
            # eid should not have changed since we import in `nodrop` mode
            self.assertEqual(firstaa.eid, secondaa.eid)
            self.assertEqual(len(es_docs), 2)
            fa_es_doc, comp_es_doc = es_docs
            # esdoc should have a key `authority' which value is AgentAuthority eid
            self.assertEqual(
                secondaa.eid,
                [
                    i for i in fa_es_doc['_source']['index_entries']
                    if i['label'] == "Direction de l'eau"
                ][0]['authority']
            )


class ReimportTests(EADImportMixin, PostgresTextMixin, CubicWebTC):
    readerconfig = merge_dicts({},
                               EADImportMixin.readerconfig,
                               {'nodrop': False})

    def test_reimport_ead(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, self.datapath('ir_data/v1/FRAD095_00374.xml'))
            c1, c11, c12 = cnx.execute('Any C ORDERBY I '
                                       'WHERE C is FAComponent, C did D, D unitid I').entities()
            self.assertEqual(len(c1.digitized_versions), 0)
            self.assertCountEqual([dv.illustration_url for dv in c11.digitized_versions],
                                  ['foo.jpg', 'bar.jpg'])
            self.assertCountEqual([dv.illustration_url for dv in c12.digitized_versions],
                                  ['bim.jpg', 'bam.jpg'])
            cnx.commit()
            delete_from_filename(cnx, 'FRAD095_00374.xml',
                                 interactive=False, esonly=False)
            self.import_filepath(cnx, self.datapath('ir_data/v2/FRAD095_00374.xml'))
            c1new, c11new, c12new, c21new = cnx.execute(
                'Any C ORDERBY I '
                'WHERE C is FAComponent, C did D, D unitid I').entities()
            self.assertCountEqual([dv.illustration_url for dv in c11new.digitized_versions],
                                  ['foo.jpg'])
            self.assertCountEqual([dv.illustration_url for dv in c12new.digitized_versions],
                                  ['bim.jpg', 'bam.jpg', 'boom.jpg'])
            self.assertCountEqual([dv.url for dv in c21new.digitized_versions],
                                  ['hello'])

    @patch('cubicweb_francearchives.dataimport.ead.Reader.ignore_filepath')
    def test_config_reimport_esonly(self, ignore_mock):
        """in esonly mode ``ignore_filepath`` method should never be called"""
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, self.datapath('FRAN_IR_022409.xml'),
                                 reimport=True, esonly=True)
            self.import_filepath(cnx, self.datapath('FRAN_IR_022409.xml'),
                                 reimport=True, esonly=True)
            self.assertFalse(ignore_mock.called)

    def test_config_reimport(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, self.datapath('FRAN_IR_022409.xml'))
            self.import_filepath(cnx, self.datapath('FRAN_IR_022409.xml'),
                                 reimport=True)
            rset = cnx.find('FindingAid')
            self.assertEqual(len(rset), 1)


class DeleteTests(EADImportMixin, PostgresTextMixin, CubicWebTC):

    def test_delete_ead_alone(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, self.datapath('ir_data/v1/FRAD095_00374.xml'))
            c1, c11, c12 = cnx.execute('Any C ORDERBY I '
                                       'WHERE C is FAComponent, C did D, D unitid I').entities()
            self.assertEqual(len(c1.digitized_versions), 0)
            self.assertCountEqual([dv.illustration_url for dv in c11.digitized_versions],
                                  ['foo.jpg', 'bar.jpg'])
            self.assertCountEqual([dv.illustration_url for dv in c12.digitized_versions],
                                  ['bim.jpg', 'bam.jpg'])
            cnx.commit()
            cnx.commit()
            self.assertGreater(len(cnx.find('Geogname')), 0)
            self.assertGreater(len(cnx.find('Subject')), 0)
            self.assertGreater(len(cnx.find('LocationAuthority')), 0)
            self.assertGreater(len(cnx.find('SubjectAuthority')), 0)
            delete_from_filename(cnx, 'FRAD095_00374.xml',
                                 interactive=False, esonly=False)
            self.assertEqual(len(cnx.find('FindingAid')), 0)
            self.assertEqual(len(cnx.find('FAComponent')), 0)
            self.assertEqual(len(cnx.find('Geogname')), 0)
            self.assertEqual(len(cnx.find('Subject')), 0)
            self.assertEqual(len(cnx.find('DigitizedVersion')), 0)
            self.assertGreater(len(cnx.find('LocationAuthority')), 0)
            self.assertGreater(len(cnx.find('SubjectAuthority')), 0)

    def test_delete_one_ead(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx,
                                 self.datapath('FRAN_IR_051016_excerpt.xml'))
            initial_fas = [fa.eid for fa in cnx.find('FindingAid').entities()]
            initial_facs = [fac.eid for fac in cnx.find('FAComponent').entities()]
            initial_dvs = [dv.eid for dv in cnx.find('DigitizedVersion').entities()]
            self.import_filepath(cnx, self.datapath('ir_data/v1/FRAD095_00374.xml'))
            self.assertEqual(len(cnx.find('FindingAid')), 2)
            self.assertEqual(len(cnx.find('FAComponent')), len(initial_facs) + 3)
            cnx.commit()
            delete_from_filename(cnx, 'FRAD095_00374.xml',
                                 interactive=False, esonly=False)
            final_fas = [fa.eid for fa in cnx.find('FindingAid').entities()]
            final_facs = [fac.eid for fac in cnx.find('FAComponent').entities()]
            final_dvs = [dv.eid for dv in cnx.find('DigitizedVersion').entities()]
            self.assertCountEqual(initial_fas, final_fas)
            self.assertCountEqual(initial_facs, final_facs)
            self.assertCountEqual(initial_dvs, final_dvs)


class PushEntitiesTests(PostgresTextMixin, CubicWebTC):

    def test_push_entities(self):
        with self.admin_access.cnx() as cnx:
            initial_nb_cards = len(cnx.find('Card'))
            cursor = cnx.cnxset.cu
            cursor.execute('CREATE TABLE foo(id varchar(16), title varchar(16))')
            cursor.copy_from(StringIO(u'c1\tt1\nc2\tt2\n'), 'foo')
            cursor.execute(
                "SELECT push_entities('Card', "
                "                     'cw_wikiid, cw_title', "
                "                     'SELECT id, title FROM foo')")
            cnx.commit()
            nb_cards = len(cnx.find('Card'))
            self.assertEqual(nb_cards, initial_nb_cards + 2)
            cnx.execute('Any C,W,T WHERE C is Card, C wikiid W, C title T')
            c1 = cnx.find('Card', wikiid=u'c1').one()
            self.assertEqual(c1.title, 't1')
            c2 = cnx.find('Card', wikiid=u'c2').one()
            self.assertEqual(c2.title, 't2')


class EADXMLReaderTests(BaseTestCase):

    def test_fa_properties(self):
        tree = eadreader.preprocess_ead(self.datapath('FRAN_IR_0261167_excerpt.xml'))
        reader = eadreader.EADXMLReader(tree)
        fa_properties = reader.fa_properties
        self.assertIn(u'Art 1-6 : poissons migrateurs',
                      fa_properties['scopecontent'])
        self.assertIn(u'dossiers par departement : syntheses',
                      fa_properties['scopecontent'])
        # remove properties that are explicitly tested elsewhere and
        # make test results harder to read
        for untested in ('origination', 'index_entries',
                         'scopecontent_format', 'scopecontent',
                         'notes', 'notes_format',
                         'genreform', 'function', 'occupation'):
            fa_properties.pop(untested)
        fa_properties['did'].pop('origination')
        self.assertEqual(reader.fa_properties, {
            'accessrestrict': None,
            'accessrestrict_format': u'text/html',
            'acquisition_info': None,
            'acquisition_info_format': u'text/html',
            'additional_resources': None,
            'additional_resources_format': u'text/html',
            'bibliography': None,
            'bibliography_format': u'text/html',
            'bioghist': None,
            'bioghist_format': u'text/html',
            'description': None,
            'description_format': u'text/html',
            'did': {
                'physloc': '<div class="ead-wrapper">Pierrefitte</div>',
                'startyear': 1922,
                'stopyear': 2001,
                'unitdate': '1922-2001',
                'unitid': u'20050526/1-20050526/26',
                'unittitle': u"Environnement ; Direction de l'eau",
            },
            'fatype': 'inventory',
            'userestrict': None,
            'userestrict_format': u'text/html',
            'referenced_files': [],
            'website_url': 'https://www.siv.archives-nationales.culture.gouv.fr/siv/IR/FRAN_IR_026167'  # noqa
        })

    def test_index_entries(self):
        tree = eadreader.preprocess_ead(self.datapath('FRAN_IR_0261167_excerpt.xml'))
        reader = eadreader.EADXMLReader(tree)
        index_entries = reader.fa_properties['index_entries']
        self.assertCountEqual(index_entries, [
            {
                'authfilenumber': None,
                'label': 'Jean-Michel',
                'normalized': u'jeanmichel',
                'role': u'index',
                'type': 'persname',
            }, {
                'authfilenumber': None,
                'label': "garonne (cours d'eau)",
                'normalized': u'cours deau garonne',
                'role': u'index',
                'type': 'geogname',
            }, {
                'authfilenumber': None,
                'label': 'poisson',
                'normalized': u'poisson',
                'role': u'index',
                'type': 'subject',
            }, {
                'authfilenumber': None,
                'label': 'pisciculture',
                'normalized': u'pisciculture',
                'role': u'index',
                'type': 'subject',
            }, {
                'authfilenumber': None,
                'label': 'aquaculture',
                'normalized': u'aquaculture',
                'role': u'index',
                'type': 'subject',
            }]
        )
        _, comp_properties = next(reader.walk())
        self.assertCountEqual(comp_properties['index_entries'], [
            {
                'authfilenumber': None,
                'label': 'Jean-Michel',
                'normalized': u'jeanmichel',
                'role': u'index',
                'type': 'persname',
            }, {
                'authfilenumber': None,
                'label': 'jean-Michel',
                'normalized': u'jeanmichel',
                'role': u'index',
                'type': 'persname',
            }, {
                'authfilenumber': None,
                'label': "garonne (cours d'eau)",
                'normalized': u'cours deau garonne',
                'role': u'index',
                'type': 'geogname',
            }, {
                'authfilenumber': None,
                'label': "Garonne (cours d'eau)",
                'normalized': u'cours deau garonne',
                'role': u'index',
                'type': 'geogname',
            }, {
                'authfilenumber': None,
                'label': 'Poisson',
                'normalized': u'poisson',
                'role': u'index',
                'type': 'subject',
            }, {
                'authfilenumber': None,
                'label': 'poisson',
                'normalized': u'poisson',
                'role': u'index',
                'type': 'subject',
            }, {
                'authfilenumber': None,
                'label': 'pisciculture',
                'normalized': u'pisciculture',
                'role': u'index',
                'type': 'subject',
            }, {
                'authfilenumber': None,
                'label': 'aquaculture',
                'normalized': u'aquaculture',
                'role': u'index',
                'type': 'subject',
            }, {
                'authfilenumber': None,
                'label': 'Jean-Paul',
                'normalized': u'jeanpaul',
                'role': u'index',
                'type': 'persname',
            }, {
                'authfilenumber': None,
                'label': 'petits poissons',
                'normalized': u'petits poissons',
                'role': u'index',
                'type': 'subject',
            }]
        )

    def test_fa_origination(self):
        tree = eadreader.preprocess_ead(self.datapath('FRAN_IR_0261167_excerpt.xml'))
        reader = eadreader.EADXMLReader(tree)
        self.assertEqual(reader.fa_properties['origination'], [{
            'authfilenumber': 'FRAN_NP_006122',
            'label': "Direction de l'eau",
            'normalized': u'de direction leau',
            'role': u'originator',
            'type': 'corpname',
        }])


if __name__ == '__main__':
    unittest.main()
