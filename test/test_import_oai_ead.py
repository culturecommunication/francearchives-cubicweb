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
import glob
import unittest
import os
import os.path

from datetime import datetime

from cubicweb_francearchives.testutils import EADImportMixin, PostgresTextMixin
from cubicweb_francearchives.dataimport import oai

from lxml import etree
from mock import patch
from cubicweb.devtools.testlib import CubicWebTC
from cubicweb_francearchives.dataimport import sqlutil, usha1

from pgfixtures import setup_module, teardown_module  # noqa


class OaiEadImportTC(EADImportMixin, PostgresTextMixin, CubicWebTC):

    @classmethod
    def init_config(cls, config):
        super(OaiEadImportTC, cls).init_config(config)
        config.set_option('consultation-base-url',
                          'https://francearchives.fr',
                          )
        config.set_option("ead-services-dir", "/tmp")

    def create_repo(self, cnx, service_code, url):
        service = cnx.create_entity(
            'Service',
            name=u'AD {}'.format(service_code),
            category=u'X',
            short_name=u'AD {}'.format(service_code),
            code=service_code)
        repo = cnx.create_entity(
            'OAIRepository',
            name=u'some-repo',
            service=service,
            url=url)
        return repo

    @property
    def path(self):
        return "{ead_services_dir}/{code}/oaipmh/ead".format(
            ead_services_dir=self.config["ead-services-dir"],
            **self.service_infos
        )

    @property
    def service_infos(self):
        return {"code": "FRAD051"}

    def tearDown(self):
        """Tear down test cases."""
        super(OaiEadImportTC, self).tearDown()
        if os.path.exists(self.path):
            for filename in glob.glob(os.path.join(self.path, "*")):
                os.remove(filename)
            os.removedirs(self.path)

    def test_dump(self):
        """Test OAI EAD standard importing.

        Trying: valid OAI-PMH
        Expecting: corresponding XML files
        """
        with self.admin_access.cnx() as cnx:
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(
                self.datapath("oai_ead/oai_ead_sample.xml")
            )
            oai.import_oai(cnx, url, self.service_infos)
            rql = "Any E WHERE X is FindingAid, X eadid E"
            result_set = [result[0] for result in cnx.execute(rql)]
        for eadid in result_set:
            prefix = self.service_infos["code"] + "_"
            if eadid.startswith(prefix):
                filename = eadid + ".xml"
            else:
                filename = prefix + ".xml"
            file_path = os.path.join(self.path, filename)
            self.assertTrue(os.path.exists(file_path))

    def test_import_no_header(self):
        """Test OAI EAD standard importing.

        Trying: no header tag
        Expecting: no database entries
        """
        with self.admin_access.cnx() as cnx:
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(
                self.datapath("oai_ead/no_header.xml")
            )
            service_infos = {"code": "FRAD051"}
            oai.import_oai(cnx, url, service_infos)
            self.assertFalse(cnx.find("FindingAid"))

    def test_import_no_metadata(self):
        """Test OAI EAD standard importing.

        Trying: no metadata tag
        Expecting: 2 out of 3 database entries
        """
        with self.admin_access.cnx() as cnx:
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(
                self.datapath("oai_ead/no_metadata.xml")
            )
            service_infos = {"code": "FRAD051"}
            oai.import_oai(cnx, url, service_infos)
            with open(self.datapath("oai_ead/no_metadata.xml")) as fp:
                element_tree = etree.parse(fp)
            eadids = [
                eadid.text for eadid in element_tree.findall(".//{*}eadid")
            ]
            rql = "Any E WHERE X is FindingAid, X eadid E"
            result_set = [result[0] for result in cnx.execute(rql)]
            self.assertItemsEqual(eadids, result_set)

    def test_import_no_eadid(self):
        """Test OAI EAD standard importing.

        Trying: no eadid tag
        Expecting: 2 out of 3 database entries
        """
        with self.admin_access.cnx() as cnx:
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(
                self.datapath("oai_ead/no_eadid.xml")
            )
            service_infos = {"code": "FRAD051"}
            oai.import_oai(cnx, url, service_infos)
            with open(self.datapath("oai_ead/no_metadata.xml")) as fp:
                element_tree = etree.parse(fp)
            eadids = [
                eadid.text for eadid in element_tree.findall(".//{*}eadid")
            ]
            rql = "Any E WHERE X is FindingAid, X eadid E"
            result_set = [result[0] for result in cnx.execute(rql)]
            self.assertItemsEqual(eadids, result_set)

    def test_empty_header(self):
        """Test OAI EAD standard importing.

        Trying: empty header
        Expecting: no database entries
        """
        with self.admin_access.cnx() as cnx:
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(
                self.datapath("oai_ead/empty_header.xml")
            )
            service_infos = {"code": "FRAD051"}
            oai.import_oai(cnx, url, service_infos)
            self.assertFalse(cnx.find("FindingAid"))

    def test_empty_metadata(self):
        """Test OAI EAD standard importing.

        Trying: empty metadata
        Expecting: no database entries
        """
        with self.admin_access.cnx() as cnx:
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(
                self.datapath("oai_ead/empty_metadata.xml")
            )
            service_infos = {"code": "FRAD051"}
            oai.import_oai(cnx, url, service_infos)
            self.assertFalse(cnx.find("FindingAid"))

    def test_empty_eadid(self):
        """Test OAI EAD standard importing.

        Trying: emtpy EAD ID
        Expecting: 2 out of 3 database entries
        """
        with self.admin_access.cnx() as cnx:
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(
                self.datapath("oai_ead/empty_eadid.xml")
            )
            service_infos = {"code": "FRAD051"}
            oai.import_oai(cnx, url, service_infos)
            with open(self.datapath("oai_ead/no_metadata.xml")) as fp:
                element_tree = etree.parse(fp)
            eadids = [
                eadid.text for eadid in element_tree.findall(".//{*}eadid")
            ]
            rql = "Any E WHERE X is FindingAid, X eadid E"
            result_set = [result[0] for result in cnx.execute(rql)]
            self.assertItemsEqual(eadids, result_set)

    def test_repeated_eadid(self):
        """Test OAI EAD standard importing.

        Trying: repeated EAD ID
        Expecting: for each EAD ID is only one entry in the database
        """
        with self.admin_access.cnx() as cnx:
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(
                self.datapath("oai_ead/repeated_eadid.xml")
            )
            service_infos = {"code": "FRAD051"}
            oai.import_oai(cnx, url, service_infos)
            with open(self.datapath("oai_ead/repeated_eadid.xml")) as fp:
                element_tree = etree.parse(fp)
            eadids = [
                eadid.text for eadid in element_tree.findall(".//{*}eadid")
            ]
            # assert that for each EAD ID is only one entry in the database
            rql = "Any E WHERE X is FindingAid, X eadid E"
            result_set = [result[0] for result in cnx.execute(rql)]
            self.assertItemsEqual(list(set(eadids)), result_set)

    def test_findingaid_support(self):
        """Test OAI EAD standard importing.

        Trying: OAI EAD standard import
        Expecting: findingaid_support attributes correspond to XML file paths
        """
        service_code = {"code": "FRAD051"}
        with self.admin_access.cnx() as cnx:
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(
                self.datapath("oai_ead/oai_ead_sample.xml")
            )
            oai.import_oai(cnx, url, service_code)
            filenames = glob.glob(os.path.join(self.path, "*.xml"))
            rql = "Any FSPATH(D) WHERE X findingaid_support F, F data D"
            result_set = [result[0].read() for result in cnx.execute(rql)]
            self.assertItemsEqual(filenames, result_set)

    def test_reimport_findingaid_support(self):
        """Test EAD re-import based on XML files.

        Trying: re-import based on XML files created during OAI EAD import
        Expecting: the same data
        """
        service_code = {"code": "FRAD051"}
        with self.admin_access.cnx() as cnx:
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(
                self.datapath("oai_ead/oai_ead_sample.xml")
            )
            oai.import_oai(cnx, url, service_code)
            rql = (
                "Any E, FSPATH(D) WHERE X findingaid_support F, F data D,"
                " X eadid E"
            )
            result_set = [
                (result[0], result[1].read()) for result in cnx.execute(rql)
            ]
            # eadids = [result[0] for result in result_set]
            filenames = [result[1] for result in result_set]
            for filename in filenames:
                sqlutil.delete_from_filename(
                    cnx, filename,
                    interactive=False, esonly=False
                )
            cnx.commit()
            rql = "Any X WHERE X is FindingAid"
            assert not cnx.execute(rql), "at least one FindingAid in database"
            rql = "Any E WHERE X is FindingAid, X eadid E"
            for filename in filenames:
                self.import_filepath(cnx, filename)
            # reimport from harvesting is temporarily suspended
            self.assertEqual(len(cnx.execute(rql)), 0)
            # self.assertItemsEqual(
            #     eadids,
            #     [result[0] for result in cnx.execute(rql)]
            # )

    def test_eadid_legacy_compliance(self):
        """Test Findinding and FAComponent ead of harvested files are always based on
        <eadid> value, but not on the file name
        """
        service_code = {"code": "FRAD051"}
        with self.admin_access.cnx() as cnx:
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(
                self.datapath("oai_ead/oai_ead_sample.xml")
            )
            oai.import_oai(cnx, url, service_code)
            rql = (
                "Any E, FSPATH(D) WHERE X findingaid_support F, F data D,"
                " X eadid E"
            )
            for fi in cnx.find('FindingAid').entities():
                self.assertEqual(fi.stable_id, usha1(fi.eadid))
            fs_paths = [f[0].getvalue() for f in cnx.execute(
                'Any FSPATH(D) WHERE X findingaid_support F, '
                'F data D')]
            # import the findingaid_support file
            for fs_path in fs_paths:
                sqlutil.delete_from_filename(
                    cnx, fs_path,
                    interactive=False, esonly=False
                )
            cnx.commit()
            for fs_path in fs_paths:
                self.import_filepath(cnx, fs_path)
                # reimport from harvesting is temporarily suspended
                self.assertEqual(len(cnx.execute(rql)), 0)

    def test_oai_ead_reimport(self):
        """Test OAI EAD re-import

        Trying: reimport the same file
        Expecting: no error is raised and no extra FindingAids creataed
        """
        service_code = {"code": "FRAD051"}
        with self.admin_access.cnx() as cnx:
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(
                self.datapath("oai_ead/oai_ead_sample.xml")
            )
            oai.import_oai(cnx, url, service_code)
            expected_fi_count = cnx.execute('Any X WHERE X is FindingAid').rowcount
            self.assertEqual(expected_fi_count, 2)
            # reimport the same file
            oai.import_oai(cnx, url, service_code)
            new_fi_count = cnx.execute('Any X WHERE X is FindingAid').rowcount
            self.assertEqual(expected_fi_count, new_fi_count)

    def test_import_extentities(self):
        with self.admin_access.cnx() as cnx:
            path = 'file://{path}?verb=ListRecords&metadataPrefix=ead'.format(
                path=self.datapath('oai_ead/oai_ead_sample.xml'))
            oai.import_oai(cnx, path, {"code": "FRAD051"})
            fas = cnx.find('FindingAid')
            self.assertEqual(2, len(fas))
            fa = cnx.find('FindingAid', eadid=u'FRAD051_000000028_203M').one()
            self.assertEqual(4, len(fa.reverse_finding_aid))
            comp_rset = cnx.execute('Any X WHERE X is FAComponent, X did D, D unittitle %(id)s',
                                    {'id': u'Administration générale'})
            self.assertEqual(1, len(comp_rset))
            comp = comp_rset.one()
            self.assertEqual(comp.digitized_versions[0].illustration_url,
                             'http://portail.cg51.mnesys.fr/ark:/86869/a011401093704slpxLP/1/1.thumbnail')  # noqa

    def test_import_new_findingaids_only(self):
        with self.admin_access.cnx() as cnx:
            repo = self.create_repo(
                cnx,
                u'FRAD051',
                url=u'file://{path}?verb=ListRecords&metadataPrefix=ead'.format(
                    path=self.datapath('oai_ead/oai_ead_sample.xml')
                )
            )
            cnx.commit()
            oai.import_delta(cnx, repo.eid)
            self.assertEqual(
                {fa.eadid for fa in cnx.find('FindingAid').entities()},
                {'FRAD051_000000028_203M', 'FRAD051_204M'}
            )
            fa = cnx.find('FindingAid', eadid=u'FRAD051_204M').one()
            self.assertCountEqual(
                {u'GUERRE 1939-1945'},
                {subject.label for subject in fa.subject_indexes().entities()}
            )
            self.assertIn(u'BAUDIN', fa.bibliography)
            self.assertEqual(
                fa.dc_title(),
                u'204 M - Organisation économique pendant la guerre 1939-1945')
            # now reimport a slightly different file to simulate changes
            # and check updates
            repo.cw_set(url=repo.url.replace('oai_ead/oai_ead_sample.xml',
                                             'oai_ead/oai_ead_sample_updated.xml'))
            oai.import_delta(cnx, repo.eid)
            # we should have :
            # FRAD051_000000028_203M untouched
            # FRAD051_204M updated (title changed, bibliography removed and
            #                       indexation changed)
            # FRAD051_205M created
            self.assertEqual(
                {fa.eadid for fa in cnx.find('FindingAid').entities()},
                {'FRAD051_000000028_203M', 'FRAD051_204M', 'FRAD051_205M'}
            )
            fa = cnx.find('FindingAid', eadid=u'FRAD051_204M').one()
            self.assertEqual(
                fa.dc_title(),
                u'MAJ - 204 M - Organisation économique pendant la guerre 1939-1945')
            self.assertEqual(fa.bibliography, None)
            self.assertCountEqual(
                {subject.label for subject in fa.subject_indexes().entities()},
                {u'GUERRE 1939-1945', u'La guerre de 39'}
            )

    def test_create_ape_ead_file(self):
        """test specific francearchive ape_ead transformations"""
        with self.admin_access.cnx() as cnx:
            repo = self.create_repo(
                cnx,
                u'FRAD051',
                url=u'file://{path}?verb=ListRecords&metadataPrefix=ead'.format(
                    path=self.datapath('oai_ead/oai_ead_sample.xml')
                )
            )
            cnx.commit()
            oai.import_delta(cnx, repo.eid)
            fa = cnx.find('FindingAid', eadid=u'FRAD051_204M').one()
            ape_ead_filepath = fa.ape_ead_file[0]
            content = ape_ead_filepath.data.read()
            tree = etree.fromstring(content)
            eadid = tree.xpath('//e:eadid',
                               namespaces={'e': tree.nsmap[None]})[0]
            self.assertEqual(eadid.attrib['url'],
                             'https://francearchives.fr/{}'.format(
                                 fa.rest_path()))
            extptrs = tree.xpath('//e:extptr',
                                 namespaces={'e': tree.nsmap[None]})
            self.assertEqual(len(extptrs), 5)
            for xlink in extptrs:
                self.assertTrue(xlink.attrib['{{{e}}}href'.format(
                    e=tree.nsmap['xlink'])].startswith('http'))

    def test_unique_indexes(self):
        """Test that no duplicate authorities are created during oai_ead import"""
        with self.admin_access.cnx() as cnx:
            cnx.create_entity('LocationAuthority',
                              label=u'Paris (Île-de-France, Paris)')
            cnx.create_entity('AgentAuthority',
                              label=u'Préfecture de la Marne')
            cnx.commit()
            repo = self.create_repo(
                cnx,
                u'FRAD051',
                url=u'file://{path}?verb=ListRecords&metadataPrefix=ead'.format(
                    path=self.datapath('oai_ead/oai_ead_sample.xml')
                )
            )
            cnx.commit()
            oai.import_delta(cnx, repo.eid)
            fa = cnx.find('FindingAid', eadid=u'FRAD051_000000028_203M').one()
            self.assertEqual(
                u'Préfecture de la Marne',
                cnx.find('AgentAuthority').one().label)
            self.assertEqual(
                u'Paris (Île-de-France, Paris)',
                cnx.find('LocationAuthority').one().label)
            # we test a fa has only one Geogname linked to the LocationAuthority
            # Paris (Île-de-France, Paris)
            self.assertEqual(fa.eid,
                             cnx.find('Geogname').one().index[0].eid)

    @patch('cubicweb_francearchives.dataimport.oai.import_oai')
    def test_from_parameter_first_import(self, import_oai):
        """check _from parameter is not set on first harvesting pass"""
        with self.admin_access.cnx() as cnx:
            repo = self.create_repo(
                cnx,
                u'FRAD051',
                url=u'http://oai.frad051.fr/?verb=ListRecords&metadataPrefix=ape_ead'
            )
            oai.import_delta(cnx, repo.eid)
            import_oai.assert_called_with(
                cnx,
                u'http://oai.frad051.fr/?verb=ListRecords&metadataPrefix=ape_ead',
                log=None,
                service_infos={
                    'code': u'FRAD051',
                    'name': u'AD FRAD051',
                    'eid': repo.service[0].eid,
                })
            self.assertEqual(
                len(repo.tasks), 1, 'we should have exactly one import task')
            twf = repo.tasks[0].cw_adapt_to('IWorkflowable')
            twf.entity.cw_clear_all_caches()
            self.assertEqual(twf.state, 'wfs_oaiimport_completed')

    @patch('cubicweb_francearchives.dataimport.oai.import_oai')
    def test_from_parameter_last_succcessful_import(self, import_oai):
        """check _from parameter is inserted when re-harvesting"""
        with self.admin_access.cnx() as cnx:
            repo = self.create_repo(
                cnx,
                u'FRAD051',
                url=u'http://oai.frad051.fr/?verb=ListRecords&metadataPrefix=ape_ead'
            )
            # create a successful import task in the past and make sure _from
            # is set accordingly on next harvesting
            task = cnx.create_entity('OAIImportTask', oai_repository=repo)
            cnx.commit()
            twf = task.cw_adapt_to('IWorkflowable')
            twf.fire_transition('wft_faimport_complete')
            task.cw_clear_all_caches()
            trinfo = twf.latest_trinfo()
            trinfo.cw_set(creation_date=datetime(2001, 2, 3))
            oai.import_delta(cnx, repo.eid)
            import_oai.assert_called_with(
                cnx,
                u'http://oai.frad051.fr/?verb=ListRecords&metadataPrefix=ape_ead&from=2001-02-03',
                log=None,
                service_infos={
                    'code': u'FRAD051',
                    'name': u'AD FRAD051',
                    'eid': repo.service[0].eid,
                })


if __name__ == '__main__':
    unittest.main()
