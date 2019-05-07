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
from os import path as osp
import os
import glob

import unittest
from lxml import etree

from oaipmh.metadata import MetadataRegistry, oai_dc_reader
from oaipmh.client import Client

from cubicweb.devtools.testlib import CubicWebTC
from cubicweb_francearchives.testutils import PostgresTextMixin

from cubicweb_francearchives.dataimport import oai, oai_dc, usha1
from cubicweb_francearchives.dataimport.scripts.generate_ape_ead import (
    generate_ape_ead_other_sources_from_eids,)

from pgfixtures import setup_module, teardown_module  # noqa


class OaiDcImportTC(PostgresTextMixin, CubicWebTC):

    @classmethod
    def init_config(cls, config):
        """Initialize configuration."""
        super(OaiDcImportTC, cls).init_config(config)
        config.set_option("ead-services-dir", "/tmp")

    def setUp(self):
        super(OaiDcImportTC, self).setUp()
        self.oai_dc_dir = self.datapath('oai_dc')

    def tearDown(self):
        """Tear down test cases."""
        super(OaiDcImportTC, self).tearDown()
        directories = [
            self.path.format(
                ead_services_dir=self.config["ead-services-dir"], code=code
            ) for code in ("FRAD034", "FRAD055")
        ]
        for directory in directories:
            if osp.exists(directory):
                for filename in glob.glob(osp.join(directory, "*")):
                    os.remove(filename)
                os.removedirs(directory)

    def filepath(self, filepath):
        return osp.join(self.oai_dc_dir, filepath)

    @property
    def path(self):
        return "{ead_services_dir}/{code}/oaipmh/dc"

    def test_write(self):
        """Test writing OAI-PMH records to backup file.

        Trying: importing records
        Expecting: backup file
        """
        with self.admin_access.cnx() as cnx:
            url = "file://{}?verb=ListRecords&metadataPrefix=oai_dc".format(
                self.filepath("oai_dc_sample.xml")
            )
            service_infos = {"code": "FRAD034"}
            oai.import_oai(cnx, url, service_infos)
            path = self.path.format(
                ead_services_dir=self.config["ead-services-dir"],
                **service_infos
            )
            self.assertTrue(osp.exists(path))

    def test_reimport_findingaid_support(self):
        """Test re-import of OAI-PMH records from backup file.

        Trying: re-import based on backup file created during import
        Expecting: the same data
        """
        service_infos = {"code": "FRAD034"}
        url_str = "file://{}?verb=ListRecords&metadataPrefix=oai_dc"
        with self.admin_access.cnx() as cnx:
            # import
            url = url_str.format(
                self.filepath("oai_dc_sample.xml")
            )
            oai.import_oai(cnx, url, service_infos)
            fi_rql = (
                "Any X, E, FSPATH(D) WHERE X findingaid_support F, F data D,"
                " X eadid E")
            fi_eid, fi_eadid, fs_path = [
                (eid, eadid, fpath.getvalue())
                for eid, eadid, fpath in cnx.execute(fi_rql)][0]
            # improt the findingaid_support file
            url = url_str.format(fs_path)
            oai.import_oai(cnx, url, service_infos)
            self.assertEqual(cnx.find('FindingAid').rowcount, 1)
            nfi_eid, nfi_eadid, nfs_path = [
                (eid, eadid, fpath.getvalue())
                for eid, eadid, fpath in cnx.execute(fi_rql)][0]
            self.assertNotEqual(fi_eid, nfi_eid)
            self.assertEqual(fi_eadid, nfi_eadid)
            self.assertEqual(fs_path, nfs_path)

    def test_eadid_legacy_compliance(self):
        """Test Findinding and FAComponent ead are always based on <eadid>
        value, but not on the file name
        """
        service_infos = {"code": "FRAD034"}
        url_str = "file://{}?verb=ListRecords&metadataPrefix=oai_dc"
        with self.admin_access.cnx() as cnx:
            # import
            url = url_str.format(
                self.filepath("oai_dc_sample.xml")
            )
            oai.import_oai(cnx, url, service_infos)
            fi = cnx.find('FindingAid').one()
            self.assertEqual(fi.stable_id, usha1(fi.eadid))
            fs_path = cnx.execute(
                'Any FSPATH(D) WHERE X findingaid_support F, '
                'F data D')[0][0].getvalue()
            # import the findingaid_support file
            url = url_str.format(fs_path)
            oai.import_oai(cnx, url, service_infos)
            fi = cnx.find('FindingAid').one()
            self.assertEqual(fi.stable_id, usha1(fi.eadid))

    def test_metadata(self):
        path = 'file://{path}'.format(
            path=osp.join(self.filepath('oai_dc_sample.xml')))
        registry = MetadataRegistry()
        registry.registerReader('oai_dc', oai_dc_reader)
        client = Client(path, registry, force_http_get=False)
        records = client.listRecords(metadataPrefix='oai_dc')
        header, metadata, about = records.next()
        header = oai_dc.build_header(header, client.getNamespaces())
        metadata = oai_dc.build_metadata(metadata)
        self.assertEqual(header, {
            'eadid': 'FRAD055_REC',
            'identifier': '86869/a011349628476eWWr7u',
            'name': 'FRAD055'})
        self.assertEqual(metadata, {
            'contributor': [u'Jean Valjean', u'Victor Hugo'],
            'coverage': [u'France'],
            'creator': [u'Archives départementales de la Meuse'],
            'date1': u'1865',
            'date2': u'1981',
            'description': [u'description'],
            'format': [u'8.0'],
            'identifier': [u'https://recherche-archives.doubs.fr/ark:/25993/a011369750208WU2TRM'],
            'language': [u'eng'],
            'publisher': [u'Archives départementales du Doubs'],
            'relation': [u'vignette 1', u'vignette 2'],
            'rights': [u'Les documents peuvent être reproduits sous réserve de leur bon état de conservation. La reproduction et la réutilisation des documents sont soumises aux dispositions du règlement général de réutilisation des informations publiques des Archives départementales du Doubs. '],  # noqa
            'source': [u'62J-105'],
            'subject': [u'Architecture', u'Livre'],
            'title': [u'62J Ordre et syndicat des architectes'],
            'type': [u'fonds', u'fake type']}
        )

    def test_import_meuse_extentities(self):
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                'Service', code=u'FRAD055', name=u'Service',
                category=u'test')
            cnx.commit()
            path = 'file://{path}?verb=ListRecords&metadataPrefix=oai_dc'.format(
                path=self.filepath('oai_dc_meuse_sample.xml'))
            service_infos = {'name': service.name,
                             'eid': service.eid,
                             'code': service.code}
            with cnx.allow_all_hooks_but('es'):
                oai.import_oai(cnx, path, service_infos)
                fa_rset = cnx.execute('Any X WHERE X is FindingAid')
                self.assertEqual(len(fa_rset), 1)
                es_fa_rset = cnx.execute('Any ES WHERE X is FindingAid, ES entity X')
                self.assertEqual(len(es_fa_rset), 1)
                fac_rset = cnx.execute('Any X WHERE X is FAComponent')
                self.assertEqual(len(fac_rset), 300)
                es_fac_rset = cnx.execute('Any ES WHERE X is FAComponent, ES entity X')
                self.assertEqual(len(es_fac_rset), 300)

    def test_import_extentities(self):
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                'Service', code=u'FRAD034', name=u'Service',
                category=u'test')
            cnx.commit()
            path = 'file://{path}?verb=ListRecords&metadataPrefix=oai_dc'.format(
                path=self.filepath('oai_dc_sample.xml'))
            service_infos = {'name': service.name,
                             'eid': service.eid,
                             'code': service.code}
            with cnx.allow_all_hooks_but('es'):
                oai.import_oai(cnx, path, service_infos)
                fa_rset = cnx.execute('Any X WHERE X is FindingAid')
                self.assertEqual(len(fa_rset), 1)
                fa = fa_rset.one()
                self.assertEqual(fa.eadid,
                                 u'FRAD055_REC')
                self.assertEqual(fa.name, u'FRAD055')
                self.assertEqual(fa.publisher, u'Service')
                self.assertEqual(fa.service[0].eid, service.eid)
                self.assertEqual(fa.scopecontent, None)
                self.assertFalse(fa.fatype, None)
                self.assertEqual(fa.did[0].unitid, None)
                self.assertEqual(fa.did[0].unittitle, u'FRAD055')
                self.assertEqual(fa.did[0].startyear, None)
                self.assertEqual(fa.did[0].stopyear, None)
                self.assertEqual(fa.did[0].unitdate, None)
                self.assertEqual(fa.did[0].origination, None)
                self.assertEqual(fa.did[0].lang_code, None)
                self.assertEqual(fa.fa_header[0].titleproper, u'FRAD055')
                facs_rset = cnx.execute('Any F WHERE F is FAComponent')
                facs = list(facs_rset.entities())
                facs.sort(key=lambda fac: fac.did[0].unitid)
                fac1, fac2 = facs
                fac1_did = fac1.did[0]
                self.assertEqual(fac1_did.unittitle, u'62J Ordre et syndicat des architectes')
                self.assertEqual(fac1_did.unitid, u'62J-105')
                self.assertEqual(fac1_did.origination, u'Archives départementales de la Meuse')
                self.assertEqual(fac1_did.unitdate, u'1865 - 1981')
                self.assertEqual(fac1_did.startyear, 1865)
                self.assertEqual(fac1_did.stopyear, 1981)
                self.assertEqual(fac1.did[0].lang_code, 'eng')
                self.assertEqual(fac1.did[0].lang_description, None)
                self.assertIn(u'<div class="ead-p">8.0</div>', fac1_did.physdesc)
                self.assertIn(u'<div class="ead-p">description</div>', fac1.scopecontent)
                self.assertIn(u'<div class="ead-p">Les documents peuvent', fac1.userestrict)
                self.assertEqual(len(fac1.digitized_versions), 3)
                self.assertCountEqual(
                    [dao.url for dao in fac1.digitized_versions if dao.url],
                    [u'https://recherche-archives.doubs.fr/ark:/25993/a011369750208WU2TRM'])
                self.assertCountEqual(
                    [dao.illustration_url for dao in fac1.digitized_versions
                     if dao.illustration_url],
                    [u'vignette 1', 'vignette 2'])
                index_entries = [(ie.authority[0].cw_etype, ie.authority[0].label)
                                 for ie in fac1.reverse_index]
                self.assertCountEqual(
                    index_entries,
                    [(u'SubjectAuthority', u'Architecture'),
                     (u'SubjectAuthority', u'Livre'),
                     (u'AgentAuthority', u'Jean Valjean'),
                     (u'AgentAuthority', u'Victor Hugo'),
                     (u'LocationAuthority', u'France')])
                fac2_did = fac2.did[0]
                self.assertEqual(fac2_did.unittitle, u'62J1 Ordre et syndicat des architectes')
                self.assertEqual(fac2_did.unitid, u'62J1-205')
                self.assertEqual(fac2_did.origination, u'Archives départementales de la Meuse')
                self.assertEqual(fac2_did.unitdate, u'1865')
                self.assertEqual(fac2_did.startyear, 1865)
                self.assertEqual(fac2_did.stopyear, None)
                self.assertEqual(fac2.did[0].lang_code, None)
                self.assertIn(u'<div class="ead-p">eng ; fra</div>', fac2.did[0].lang_description)
                self.assertIn(u'<div class="ead-p">12.19 ; text/html</div>', fac2_did.physdesc)
                self.assertIn(u'<div class="ead-p">description</div>', fac2.scopecontent)
                self.assertIn(u'<div class="ead-p">Les documents peuvent', fac2.userestrict)
                self.assertEqual(len(fac2.digitized_versions), 1)
                self.assertCountEqual(
                    [dao.url for dao in fac2.digitized_versions if dao.url],
                    [u'https://recherche-archives.doubs.fr/ark:/25993/a011369750208WU2TRT'])
                index_entries = [(ie.authority[0].cw_etype, ie.authority[0].label)
                                 for ie in fac2.reverse_index]
                self.assertCountEqual(
                    index_entries,
                    [(u'SubjectAuthority', u'France'),
                     (u'AgentAuthority', u'Jean Marais'),
                     (u'LocationAuthority', u'Paris')])
                # ape_ead_file must be created
                ape_ead_file = fa.ape_ead_file[0]
                content = ape_ead_file.data.read()
                tree = etree.fromstring(content)
                eadid = tree.xpath('//e:eadid',
                                   namespaces={'e': tree.nsmap[None]})[0]
                self.assertEqual(eadid.attrib['url'],
                                 'https://francearchives.fr/{}'.format(
                                     fa.rest_path()))

    def test_unique_indexes(self):
        """Test that no duplicate authorities are created during oai_dc import"""
        with self.admin_access.cnx() as cnx:
            cnx.create_entity('LocationAuthority',
                              label=u'Paris')
            cnx.create_entity('AgentAuthority',
                              label=u'Jean Valjean')
            cnx.create_entity('SubjectAuthority',
                              label=u'Architecture')
            cnx.create_entity('SubjectAuthority',
                              label=u'Livre')
            cnx.commit()
            service = cnx.create_entity(
                'Service', code=u'FRAD034', name=u'Service',
                category=u'test')
            cnx.commit()
            path = 'file://{path}?verb=ListRecords&metadataPrefix=oai_dc'.format(
                path=self.filepath('oai_dc_sample.xml'))
            service_infos = {'name': service.name,
                             'eid': service.eid,
                             'code': service.code}
            with cnx.allow_all_hooks_but('es'):
                oai.import_oai(cnx, path, service_infos)
                self.assertEqual(
                    ['Architecture', 'France', 'Livre'],
                    sorted([e.label for e in
                            cnx.find('SubjectAuthority').entities()]))
                self.assertEqual(
                    ['Jean Marais', 'Jean Valjean', 'Victor Hugo'],
                    sorted([e.label for e in
                            cnx.find('AgentAuthority').entities()]))
                self.assertEqual(
                    [u'France', u'Paris'],
                    sorted([e.label for e in
                            cnx.find('LocationAuthority').entities()]))

    def test_generate_ape_ead_utils(self):
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                'Service', code=u'FRAD034', name=u'Service',
                category=u'test')
            fadid = cnx.create_entity('Did', unitid=u'maindid',
                                      unittitle=u'maindid-title')
            fa = cnx.create_entity(
                'FindingAid',
                name=u'the-fa',
                stable_id=u'FRAD051_xxx',
                eadid=u'FRAD051_xxx',
                publisher=u'FRAD051',
                service=service,
                did=fadid,
                fa_header=cnx.create_entity('FAHeader')
            )
            cnx.commit()
            generate_ape_ead_other_sources_from_eids(cnx, [str(fa.eid)])
            fa = cnx.entity_from_eid(fa.eid)
            content = fa.ape_ead_file[0].data.read()
            tree = etree.fromstring(content)
            eadid = tree.xpath('//e:eadid',
                               namespaces={'e': tree.nsmap[None]})[0]
            self.assertEqual(eadid.attrib['url'],
                             'https://francearchives.fr/{}'.format(
                                 fa.rest_path()))

    def test_oai_dc_reimport(self):
        """Test OAI DC re-import
        Trying: reimport the same file
        Expecting: no error is raised and no extra FindingAids created
            """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                'Service', code=u'FRAD055', name=u'Service',
                category=u'test')
            cnx.commit()
            path = 'file://{path}?verb=ListRecords&metadataPrefix=oai_dc'.format(
                path=self.filepath('oai_dc_meuse_sample.xml'))
            service_infos = {'name': service.name,
                             'eid': service.eid,
                             'code': service.code}
            oai.import_oai(cnx, path, service_infos)
            fi = cnx.execute('Any X WHERE X is FindingAid').one()
            # reimport the same file
            oai.import_oai(cnx, path, service_infos)
            new_fi = cnx.execute('Any X WHERE X is FindingAid').one()
            self.assertNotEqual(fi.eid, new_fi.eid)
            self.assertEqual(new_fi.stable_id, new_fi.stable_id)
            fac_rset = cnx.execute('Any X WHERE X is FAComponent')
            self.assertEqual(len(fac_rset), 300)
            self.assertEqual(len(set(f.dc_title() for f in fac_rset.entities())),
                             100)

    def test_multiple_setSpec(self):
        """Test the case where several FindingAid are created from the same harvesting
        Trying: import a oai_dc file with 2 different <setSpec>
        Expecting: 2 FindingAid are created with one and two FAComponents
            """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                'Service', code=u'FRAD055', name=u'Service',
                category=u'test')
            cnx.commit()
            path = 'file://{path}?verb=ListRecords&metadataPrefix=oai_dc'.format(
                path=self.filepath('oai_dc_multiple_set.xml'))
            service_infos = {'name': service.name,
                             'eid': service.eid,
                             'code': service.code}
            oai.import_oai(cnx, path, service_infos)
            self.assertEqual(len(cnx.execute('Any X WHERE X is FindingAid')), 2)
            self.assertEqual(len(cnx.execute('Any X WHERE X is FAComponent')), 3)
            fi_ec = cnx.execute('Any X WHERE X is FindingAid, X eadid "FRAD055_EC"').one()
            self.assertEqual(len(fi_ec.reverse_finding_aid), 2)
            fi_rec = cnx.execute('Any X WHERE X is FindingAid, X eadid "FRAD055_REC"').one()
            self.assertEqual(len(fi_rec.reverse_finding_aid), 1)

    def test_multiple_findingaind_support(self):
        """Test each FindingAid created from the same harvesting has
        a separate findingaid_support file
        Trying: import a oai_dc file with 2 different <setSpec>
        Expecting: both FindingAid have different findingaid_support files
            """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                'Service', code=u'FRAD055', name=u'Service',
                category=u'test')
            cnx.commit()
            path = 'file://{path}?verb=ListRecords&metadataPrefix=oai_dc'.format(
                path=self.filepath('oai_dc_multiple_set.xml'))
            service_infos = {'name': service.name,
                             'eid': service.eid,
                             'code': service.code}
            oai.import_oai(cnx, path, service_infos)
            rset = cnx.execute(
                "DISTINCT Any E, FSPATH(D) WHERE X findingaid_support F, F data D,"
                " X eadid E"
            )
            self.assertEqual(rset.rowcount, 2)
            for eid, fpath in rset:
                fpath = fpath.getvalue()
                self.assertEqual(fpath, u'{}/FRAD055/oaipmh/dc/{}.xml'.format(
                    self.config["ead-services-dir"], eid))
                self.assertTrue(osp.exists(fpath))


if __name__ == '__main__':
    unittest.main()
