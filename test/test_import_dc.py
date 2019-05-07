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

from os import path as osp

from cubicweb.devtools import testlib

from cubicweb.dataimport.stores import RQLObjectStore

from cubicweb_francearchives.testutils import PostgresTextMixin
from cubicweb_francearchives.utils import pick
from cubicweb_francearchives.dataimport import (dc, CSVIntegrityError)

from pgfixtures import setup_module, teardown_module  # noqa


class CSVImportMixIn(object):

    def csv_filepath(self, filepath):
        return osp.join(self.datapath('csv', filepath))

    def _test_medatadata_csv(self, cnx, service):
        fa_rset = cnx.execute('Any FA WHERE FA is FindingAid')
        self.assertEqual(len(fa_rset), 1)
        fa = fa_rset.one()
        self.assertEqual(fa.name, u'FRAD092_9FI_cartes-postales.csv')
        self.assertEqual(fa.eadid, u'FRAD092_9FI_cartes-postales')
        self.assertEqual(fa.fatype, u'photographie')
        self.assertEqual(fa.did[0].unitid, None)
        self.assertEqual(fa.did[0].unittitle, u'Cartes postales anciennes')
        self.assertEqual(fa.did[0].unitdate, None)  # XXX ?
        self.assertEqual(fa.did[0].startyear, 1900)
        self.assertEqual(fa.did[0].stopyear, 1944)
        self.assertEqual(fa.did[0].origination, 'Archives des Hauts-de-Seine')
        self.assertEqual(fa.did[0].lang_description, u'italien')
        self.assertEqual(fa.did[0].extptr,
                         u'https://opendata.hauts-de-seine.fr/explore/dataset/cartes-postales/')
        self.assertEqual(fa.fa_header[0].titleproper, u'Cartes postales anciennes')
        self.assertIn('<div class="ead-p">5 cartons</div>', fa.did[0].physdesc)
        self.assertIn(
            u'<div class="ead-p">Cartes postales anciennes (1900-1944)</div>',
            fa.scopecontent)
        self.assertIn(
            u'<div class="ead-p">Collection photographie département Essonne.</div>',
            fa.additional_resources)
        self.assertIn(u'<div class="ead-p">Libre accès</div>', fa.accessrestrict)
        self.assertIn(u'<div class="ead-p">Libre de droit</div>', fa.userestrict)
        self.assertEqual(fa.publisher, u'AD 92')
        self.assertEqual(fa.service[0].eid, service.eid)
        self.assertEqual(fa.findingaid_support[0].data_name,
                         u'FRAD092_9FI_cartes-postales.csv')
        self.assertEqual(fa.findingaid_support[0].data_format, u'text/csv')
        facs_rset = cnx.execute('Any F WHERE F is FAComponent')
        self.assertEqual(len(facs_rset), 10)
        facs = sorted(facs_rset.entities(), key=lambda fac: fac.did[0].unitid)
        fac1 = facs[0]
        self.assertIn(u'<div class="ead-p">Est développée la notion',
                      fac1.scopecontent)
        self.assertIn(u'<div class="ead-p">Collection photographie, BNF',
                      fac1.additional_resources)
        self.assertIn(u'<div class="ead-p">Libre accès</div>', fac1.accessrestrict)
        self.assertIn(u'<div class="ead-p">Libre de droit</div>', fac1.userestrict)
        self.assertEqual(fac1.did[0].unitid, u'9FI/BAG_10')
        self.assertEqual(fac1.did[0].unittitle, u'Le Dépot des Tramways')
        self.assertEqual(fac1.did[0].unitdate, u'1900')
        self.assertEqual(fac1.did[0].startyear, 1900)
        self.assertEqual(fac1.did[0].stopyear, 1900)
        self.assertEqual(fac1.did[0].origination, u'Archives privées Mr X')
        self.assertEqual(fac1.did[0].lang_description, None)
        self.assertIn(u'<div class="ead-p">12x19 cm</div>',
                      fac1.did[0].physdesc)
        self.assertEqual(len(fac1.digitized_versions), 1)
        self.assertEqual(
            fac1.digitized_versions[0].url,
            u'https://opendata.hauts-de-seine.fr/explore/dataset/cartes-postales/table/?sort=id')  # noqa
        self.assertEqual(
            fac1.digitized_versions[0].illustration_url,
            u'https://opendata.hauts-de-seine.fr/api/datasets/1.0/cartes-postales/images/8ee3d34b124926666f78afa361566542')  # noqa
        index_entries = [(ie.authority[0].cw_etype, ie.authority[0].label)
                         for ie in fac1.reverse_index]
        self.assertCountEqual(
            index_entries,
            [(u'SubjectAuthority', u'Bâtiment public > Gare'),
             (u'AgentAuthority', u'Charles Baudelaire'),
             (u'LocationAuthority', u'Bagneux')])
        fac5 = facs[5]
        self.assertIn(u'<div class="ead-p">Duis aute irure dolor in',
                      fac5.scopecontent)
        self.assertEqual(fac5.additional_resources, None)
        self.assertIn(u'<div class="ead-p">Libre accès</div>', fac5.accessrestrict)
        self.assertIn(u'<div class="ead-p">Libre de droit</div>', fac5.userestrict)
        self.assertEqual(fac5.did[0].unitid, u'9FI/BAG_21')
        self.assertEqual(fac5.did[0].unittitle, u'La Sous-Station Electrique')
        self.assertEqual(fac5.did[0].unitdate, u'1900')
        self.assertEqual(fac5.did[0].startyear, 1900)
        self.assertEqual(fac5.did[0].stopyear, 1900)
        self.assertEqual(fac5.did[0].origination, u'Entreprise Pajol')
        self.assertEqual(fac5.did[0].lang_description, None)
        self.assertIn(u'<div class="ead-p">17x19 cm</div>',
                      fac5.did[0].physdesc)
        self.assertEqual(len(fac5.digitized_versions), 1)
        self.assertEqual(
            fac5.digitized_versions[0].url,
            u'https://opendata.hauts-de-seine.fr/explore/dataset/cartes-postales/table/?sort=id')  # noqa

        self.assertEqual(fac5.digitized_versions[0].illustration_url, None)
        index_entries = [(ie.authority[0].cw_etype, ie.authority[0].label)
                         for ie in fac5.reverse_index]
        self.assertCountEqual(
            index_entries,
            [(u'SubjectAuthority', u'Bâtiment public'),
             (u'AgentAuthority', u'Emma Bovary'),
             (u'AgentAuthority', u'Claudette Levy'),
             (u'AgentAuthority', u'Société Beguin-Say'),
             (u'LocationAuthority', u'Bagneux')])


class CSVDCImportTC(CSVImportMixIn, PostgresTextMixin,
                    testlib.CubicWebTC):
    readerconfig = {
        'noes': True,
        'esonly': False,
        'appid': 'data',
        'nodrop': False,
        'dc_no_cache': True,
        'index-name': 'dummy',
    }

    def test_import_findingaid_esonly(self):
        with self.admin_access.cnx() as cnx:
            fpath = self.csv_filepath('frmaee_findingaid.csv')
            config = self.readerconfig.copy()
            config['esonly'] = True
            store = RQLObjectStore(cnx)
            importer = dc.CSVReader(config, store)
            services_infos = {}
            es_docs = [e['_source'] for e in importer.import_filepath(services_infos, fpath)]
            self.assertEqual(len(es_docs), 4)
            fa_docs = [e for e in es_docs if e['cw_etype'] == 'FindingAid']
            self.assertEqual(len(fa_docs), 1)
            self.assertEqual(set(fa_docs[0].keys()), {
                'escategory',
                'publisher',
                'name',
                'cw_etype',
                'did',
                'year',
                'eid',
                'stable_id',
                'fa_stable_id',
                'fatype',
                'index_entries',
                'scopecontent',
                'eadid', })

    def test_import_one_facomponent_esonly(self):
        with self.admin_access.cnx() as cnx:
            fpath = self.csv_filepath('frmaee_findingaid.csv')
            config = self.readerconfig.copy()
            config['esonly'] = True
            store = RQLObjectStore(cnx)
            importer = dc.CSVReader(config, store)
            services_infos = {}
            es_docs = [e['_source'] for e in importer.import_filepath(services_infos, fpath)]
            es_docs = [e for e in es_docs if e['cw_etype'] == 'FAComponent']
            self.assertEqual(len(es_docs), 3)
            es_doc = [e for e in es_docs if e['did']['unitid'] == 'TRA13680001'][0]
            self.assertEqual(set(es_doc.keys()), {'escategory',
                                                  'publisher',
                                                  'name',
                                                  'eid',
                                                  'cw_etype',
                                                  'did',
                                                  'year',
                                                  'stable_id',
                                                  'fa_stable_id',
                                                  'index_entries',
                                                  'eadid',
                                                  'scopecontent',
                                                  'digitized', })
            es_index_entries = es_doc['index_entries']
            self.assertTrue(all('type' in i and 'label' in i for i in es_index_entries))
            self.assertEqual(len(es_index_entries), 4)
            es_doc = pick(es_doc, *(set(es_doc) - {'extid', 'stable_id'}))
            # ensure `index_entries` list is alway in same order
            es_doc['index_entries'] = sorted(es_doc['index_entries'], key=lambda k: k['normalized'])
            self.assertEqual(es_doc, {
                'cw_etype': u'FAComponent',
                'did': {
                    'unitid': u'TRA13680001',
                    'unittitle': u'Recueil de traités (1368-1408)',
                    'eid': None,
                },
                'digitized': True,
                'eadid': None,
                'eid': None,
                'escategory': u'archives',
                'fa_stable_id': u'd8e6d65766871576a026b2a75b3fc2fa349d6040',
                'index_entries': [{
                    'label': u'Clermont-Ferrand',
                    'normalized': u'clermontferrand',
                    'type': 'geogname',
                    'role': u'index',
                    'authority': None,
                    'authfilenumber': None,
                }, {
                    'label': u'corporname',
                    'normalized': u'corporname',
                    'type': 'corpname',
                    'role': u'index',
                    'authority': None,
                    'authfilenumber': None,
                }, {
                    'label': u'Henri VII',
                    'normalized': u'henri vii',
                    'type': 'persname',
                    'role': u'index',
                    'authority': None,
                    'authfilenumber': None,
                }, {
                    'label': u'subject',
                    'normalized': u'subject',
                    'type': 'subject',
                    'role': u'index',
                    'authority': None,
                    'authfilenumber': None,
                }],
                'name': u'frmaee_findingaid',
                'publisher': u'FRMAEE',
                'scopecontent': u'Validit\xe9 du trait\xe9 : historique.',
                'year': 1500
            })

    def test_import_filepath(self):
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but('es'):
                fpath = self.csv_filepath('frmaee_findingaid.csv')
                config = self.readerconfig.copy()
                dc.import_filepath(cnx, config, fpath)
                fa_rset = cnx.execute('Any FA WHERE FA is FindingAid')
                self.assertEqual(len(fa_rset), 1)
                fa = fa_rset.one()
                did = fa.did[0]
                self.assertEqual(fa.name, u'frmaee_findingaid')
                self.assertEqual(fa.eadid, u'frmaee_findingaid')
                self.assertEqual(fa.publisher, u'FRMAEE')
                self.assertFalse(fa.fatype)
                self.assertEqual(fa.scopecontent, None)
                self.assertEqual(fa.additional_resources, None)
                self.assertEqual(fa.accessrestrict, None)
                self.assertEqual(fa.userestrict, None)
                self.assertEqual(did.unitid, None)
                self.assertEqual(did.unittitle, u'frmaee_findingaid')
                self.assertEqual(did.unitdate, None)  # XXX ?
                self.assertEqual(did.startyear, None)
                self.assertEqual(did.stopyear, None)
                self.assertEqual(did.origination, u'frmaee')
                self.assertEqual(did.lang_description, None)
                self.assertEqual(fa.fa_header[0].titleproper, u'frmaee_findingaid')
                self.assertEqual(fa.findingaid_support[0].data_name, u'frmaee_findingaid.csv')
                self.assertEqual(fa.findingaid_support[0].data_format, u'text/csv')
                dids_rset = cnx.execute('Any D WHERE D is Did')
                self.assertEqual(len(dids_rset), 4)
                ies_rset = cnx.execute('Any X WHERE X is IN (AgentName, Geogname, Subject)')
                self.assertEqual(len(ies_rset), 8)
                dvs_rset = cnx.execute('Any D WHERE D is DigitizedVersion')
                self.assertEqual(len(dvs_rset), 3)
                facs_rset = cnx.execute('Any F WHERE F is FAComponent')
                self.assertEqual(len(facs_rset), 3)
                facs = list(facs_rset.entities())
                facs.sort(key=lambda fac: fac.did[0].unitid)
                fac1, fac2, fac3 = facs
                fac1_did = fac1.did[0]
                self.assertIn(u'Validité du traité : historique.', fac1.scopecontent)
                self.assertIn(u'Ressource complementaire 1', fac1.additional_resources)
                self.assertIn(u'<div class="ead-p">Libre accès</div>', fac1.accessrestrict)
                self.assertIn(u'<div class="ead-p">Libre de droit</div>', fac1.userestrict)
                self.assertEqual(fac1_did.unitid, u'TRA13680001')
                self.assertEqual(fac1_did.unittitle, u'Recueil de traités (1368-1408)')
                self.assertEqual(fac1_did.unitdate, u'1500-01-01')
                self.assertEqual(fac1_did.startyear, 1500)
                self.assertEqual(fac1_did.stopyear, 1500)
                self.assertEqual(fac1_did.origination, u'origine1')
                self.assertIn(u'<div class="ead-p">fra</div>', fac1_did.lang_description)
                self.assertIn(u'<div class="ead-p">Format 1</div>',
                              fac1_did.physdesc)
                self.assertEqual(len(fac1.digitized_versions), 1)
                self.assertEqual(
                    fac1.digitized_versions[0].url,
                    u'http://www.diplomatie.gouv.fr/traites/affichetraite.do?accord=TRA13680001')
                self.assertEqual(fac1.digitized_versions[0].illustration_url, u'img1')
                self.assertEqual(len(fac1.reverse_index), 4)
                index_entries = [(ie.authority[0].cw_etype, ie.authority[0].label)
                                 for ie in fac1.reverse_index]
                self.assertCountEqual(
                    index_entries,
                    [(u'SubjectAuthority', u'subject'),
                     (u'AgentAuthority', u'corporname'),
                     (u'AgentAuthority', u'Henri VII'),
                     (u'LocationAuthority', u'Clermont-Ferrand')])
                self.assertIn(u'Validité du traité : historique. Lieu de signature : Vincennes.',
                              fac2.scopecontent)
                self.assertIn(u'Ressource complementaire 2', fac2.additional_resources)
                self.assertIn(u'<div class="ead-p">Libre accès</div>', fac2.accessrestrict)
                self.assertIn(u'<div class="ead-p">Libre de droit</div>', fac2.userestrict)
                self.assertEqual(fac1.component_order, 0)
                fac2_did = fac2.did[0]
                self.assertEqual(fac2_did.unitid, u'TRA13690001')
                self.assertEqual(fac2_did.unittitle,
                                 u'Lettres patentes de Charles V, roi de France')
                self.assertEqual(fac2_did.unitdate, u'1671-07-11 - 1683-09-13')
                self.assertEqual(fac2_did.startyear, 1671)
                self.assertEqual(fac2_did.stopyear, 1683)
                self.assertIn(u'Format 2', fac2_did.physdesc)
                self.assertIn(u'<div class="ead-p">eng</div>', fac2_did.lang_description)
                self.assertIn(u'<div class="ead-p">Format 2</div>',
                              fac2_did.physdesc)
                self.assertEqual(fac2_did.origination, 'origine2')
                self.assertEqual(len(fac2.digitized_versions), 1)
                self.assertEqual(
                    fac2.digitized_versions[0].url,
                    u'http://www.diplomatie.gouv.fr/traites/affichetraite.do?accord=TRA13690001')
                self.assertEqual(fac2.digitized_versions[0].illustration_url, u'img2')
                self.assertEqual(len(fac2.reverse_index), 4)
                index_entries = [(a.cw_etype, a.label)
                                 for a in cnx.execute(
                    'Any A WHERE X eid %(e)s, I index X, I authority A',
                    {'e': fac2.eid}).entities()]
                fac3_did = fac3.did[0]
                self.assertEqual(fac2.component_order, 1)
                self.assertEqual(fac3_did.physdesc, None)
                self.assertEqual(fac3_did.lang_description, None)
                self.assertEqual(fac3.additional_resources, None)
                self.assertEqual(fac3_did.origination, None)
                self.assertEqual(fac3_did.unitid, u'TRA13690003')
                self.assertCountEqual(
                    index_entries,
                    [(u'SubjectAuthority', u'subject2'),
                     (u'AgentAuthority', u'corporname2'),
                     (u'AgentAuthority', u'Charles V'),
                     (u'LocationAuthority', u'Paris')])
                self.assertEqual(
                    fac3.digitized_versions[0].url,
                    u'http://www.diplomatie.gouv.fr/traites/affichetraite.do?accord=TRA15590001')
                self.assertEqual(fac3.digitized_versions[0].illustration_url, None)
                self.assertEqual(fac3.component_order, 2)

    def test_import_csv_without_metadatafile(self):
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity('Service', code=u'FRAD092',
                                        short_name=u'AD 92',
                                        level=u'level-D', category=u'foo')
            cnx.commit()
            with cnx.allow_all_hooks_but('es'):
                fpath = self.csv_filepath('FRAD092_9FI_cartes-postales.csv')
                config = self.readerconfig.copy()
                dc.import_filepath(cnx, config, fpath)
                self._test_medatadata_csv(cnx, service)

    def test_import_csv_with_metadatafile(self):
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity('Service', code=u'FRAD092',
                                        short_name=u'AD 92',
                                        level=u'level-D', category=u'foo')
            cnx.commit()
            with cnx.allow_all_hooks_but('es'):
                fpath = self.csv_filepath('FRAD092_9FI_cartes-postales.csv')
                meta_fpath = self.csv_filepath('metadata.csv')
                config = self.readerconfig.copy()
                config['dc_no_cache'] = False
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                self._test_medatadata_csv(cnx, service)

    def test_metadata_csv_failed(self):
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity('Service', code=u'FRAD092',
                                        short_name=u'AD 92',
                                        level=u'level-D', category=u'foo')
            cnx.commit()
            with cnx.allow_all_hooks_but('es'):
                fpath = self.csv_filepath('FRAD092_9FI_cartes-postales.csv')
                meta_fpath = self.csv_filepath('metadata.csv')
                config = self.readerconfig.copy()
                config['dc_no_cache'] = False
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                # reimport a similar but same file
                fpath = self.csv_filepath('FRAD092_9FI_cartes-postales-ko.csv')
                meta_fpath = self.csv_filepath('metadata.csv')
                try:
                    dc.import_filepath(cnx, config, fpath, meta_fpath)
                except CSVIntegrityError:
                    pass
                self._test_medatadata_csv(cnx, service)

    def test_metadata_csv_reimport(self):
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity('Service', code=u'FRAD092',
                                        short_name=u'AD 92',
                                        level=u'level-D', category=u'foo')
            cnx.commit()
            with cnx.allow_all_hooks_but('es'):
                # create a finding_aid
                fpath = self.csv_filepath('FRAD092_9FI_cartes-postales.csv')
                meta_fpath = self.csv_filepath('metadata.csv')
                config = self.readerconfig.copy()
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                self._test_medatadata_csv(cnx, service)
                fa = cnx.execute('Any FA WHERE FA is FindingAid').one()
                fa.cw_set(name=u'toto', publisher=u'titi', fatype=None)
                cnx.commit()
                self.assertEqual(fa.name, u'toto')
                # reimport the same file
                config.update({'dc_no_cache': False,
                               'reimport': True,
                               'force_delete': True})
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                self._test_medatadata_csv(cnx, service)

    def test_create_ape_ead_file(self):
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but('es'):
                fpath = self.csv_filepath('FRAD092_9FI_cartes-postales.csv')
                meta_fpath = self.csv_filepath('metadata.csv')
                config = self.readerconfig.copy()
                config['dc_no_cache'] = False
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                # reimport the same file
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                fa = cnx.execute('Any FA WHERE FA is FindingAid').one()
                ape_ead_file = fa.ape_ead_file[0]
                filepath = cnx.execute(
                    'Any FSPATH(D) WHERE X eid %(e)s, X data D', {'e': ape_ead_file.eid}
                )[0][0].getvalue()
                self.assertEqual(filepath,
                      u'/tmp/ape-ead/FRAD092/ape-FRAD092_9FI_cartes-postales.csv.xml')  # noqa
                content = ape_ead_file.data.read()
                tree = etree.fromstring(content)
                eadid = tree.xpath('//e:eadid',
                                   namespaces={'e': tree.nsmap[None]})[0]
                self.assertEqual(eadid.attrib['url'],
                                 'https://francearchives.fr/{}'.format(
                                     fa.rest_path()))


class CSVDCReImportTC(CSVImportMixIn,
                      PostgresTextMixin, testlib.CubicWebTC):
    readerconfig = {
        'noes': True,
        'esonly': False,
        'appid': 'data',
        'nodrop': True,
        'dc_no_cache': True,
        'reimport': True,
        'force_delete': True,
        'index-name': 'dummy',
    }

    def test_index_reimport(self):
        with self.admin_access.cnx() as cnx:
            cnx.create_entity('Service', code=u'FRAD092',
                              short_name=u'AD 92',
                              level=u'level-D', category=u'foo')
            cnx.commit()
            with cnx.allow_all_hooks_but('es'):
                fpath = self.csv_filepath('FRAD092_9FI_cartes-postales.csv')
                config = self.readerconfig.copy()
                dc.import_filepath(cnx, config, fpath)
                ferry = cnx.execute(
                    'Any X WHERE X is AgentAuthority, X label %(e)s',
                    {'e': u'Jules Ferry'}).one()
                self.assertEqual(len(ferry.reverse_authority[0].index), 1)
                # reimport the same file
                dc.import_filepath(cnx, config, fpath)
                # we shell have only one AgentAuthority for Jules Ferry
                new_ferry = cnx.execute(
                    'Any X WHERE X is AgentAuthority, X label %(e)s',
                    {'e': u'Jules Ferry'}).one()
                self.assertEqual(ferry.eid, new_ferry.eid)

    def test_reimport_csv_with_files(self):
        with self.admin_access.cnx() as cnx:
            cnx.create_entity('Service', code=u'FRAD092',
                              short_name=u'AD 92',
                              level=u'level-D', category=u'foo')
            cnx.commit()
            with cnx.allow_all_hooks_but('es'):
                fpaths = [self.csv_filepath('FRAD092_9FI_cartes-postales.csv'),
                          self.csv_filepath('FRAD092_affiches_culture.csv'),
                          self.csv_filepath('FRAD092_affiches_anciennes.csv'),
                          ]
                config = self.readerconfig.copy()
                config['dc_no_cache'] = False
                dc.import_filepaths(cnx, config, fpaths)
                fa1, fa2, f3 = cnx.find('FindingAid').entities()

    def test_reimport_csv_without_metadatafile(self):
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity('Service', code=u'FRAD092',
                                        short_name=u'AD 92',
                                        level=u'level-D', category=u'foo')
            cnx.commit()
            with cnx.allow_all_hooks_but('es'):
                fpath = self.csv_filepath('FRAD092_9FI_cartes-postales.csv')
                config = self.readerconfig.copy()
                dc.import_filepath(cnx, config, fpath)
                # reimport the same file
                dc.import_filepath(cnx, config, fpath)
                self._test_medatadata_csv(cnx, service)

    def test_reimport_csv_with_metadatafile(self):
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity('Service', code=u'FRAD092',
                                        short_name=u'AD 92',
                                        level=u'level-D', category=u'foo')
            cnx.commit()
            with cnx.allow_all_hooks_but('es'):
                fpath = self.csv_filepath('FRAD092_9FI_cartes-postales.csv')
                meta_fpath = self.csv_filepath('metadata.csv')
                config = self.readerconfig.copy()
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                # reimport the same file
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                self._test_medatadata_csv(cnx, service)


if __name__ == '__main__':
    unittest.main()
