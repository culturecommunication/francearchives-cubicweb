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

from cubicweb.devtools.testlib import CubicWebTC
from cubicweb_francearchives.testutils import PostgresTextMixin, EADImportMixin

from pgfixtures import setup_module, teardown_module  # noqa


class FaPropertiesTests(EADImportMixin, PostgresTextMixin, CubicWebTC):
    def test_findingaid_inherited_bounce_url_from_service(self):
        """a FindingAid without extptr must inherit from the related service"""
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                'Service', code=u'FRAD051',
                category=u'L',
                search_form_url=u'http://francearchives.fr')
            cnx.commit()
            filepath = self.datapath('ir_data/FRAD051_est_ead_affichage.xml')
            service_infos = {"code": service.code, 'eid': service.eid}
            self.import_filepath(cnx, filepath, service_infos=service_infos)
            fa = cnx.find('FindingAid').one()
            self.assertTrue(fa.related_service.eid, service.eid)
            self.assertFalse(fa.did[0].extptr)
            self.assertEqual(fa.related_service.search_form_url,
                             fa.bounce_url)

    def test_facomponent_inherited_bounce_url_from_service(self):
        """a FAComponent without extptr must inherit from the related
        Service if it's FindingAid has not extptr neither
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                'Service', code=u'FRAD051',
                category=u'L',
                search_form_url=u'http://francearchives.fr')
            cnx.commit()
            filepath = self.datapath('ir_data/FRAD051_est_ead_affichage.xml')
            service_infos = {"code": service.code, 'eid': service.eid}
            self.import_filepath(cnx, filepath, service_infos=service_infos)
            fc_rql = 'Any X WHERE X is FAComponent, X did D, D unitid %(u)s'
            fa = cnx.find('FindingAid').one()
            self.assertFalse(fa.did[0].extptr)
            fc = cnx.execute(fc_rql, {'u': u'6E 1-15863'}).one()
            self.assertFalse(fc.did[0].extptr)
            self.assertEqual(service.eid,
                             fc.related_service.eid)
            self.assertTrue(
                fc.related_service.bounce_url,
                fc.bounce_url)

    def test_findingaid_proper_bounce_url(self):
        """FindingAid with a proper extptr must not inhertit
        from the service"""
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                'Service', code=u'FRAD034',
                category=u'L',
                search_form_url=u'http://francearchives.fr')
            cnx.commit()
            filepath = self.datapath('ir_data/FRAD034_000000248.xml')
            service_infos = {"code": service.code, 'eid': service.eid}
            self.import_filepath(cnx, filepath, service_infos=service_infos)
            fa = cnx.find('FindingAid').one()
            self.assertTrue(fa.related_service.eid, service.eid)
            expected_fa_extptr = 'http://google.fr'
            self.assertFalse(fa.did[0].extptr)
            self.assertEqual(expected_fa_extptr,
                             fa.website_url)
            self.assertEqual(expected_fa_extptr,
                             fa.bounce_url)

    def test_facomponent_inherited_bounce_url_from_findingaid(self):
        """ if <did/unitid/extptr> was not found for a FAComponent
        it's bounce_url must inherit from the FindingAid
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                'Service', code=u'FRAD034',
                category=u'L',
                search_form_url=u'http://francearchives.fr')
            cnx.commit()
            filepath = self.datapath('ir_data/FRAD034_000000248.xml')
            service_infos = {"code": service.code, 'eid': service.eid}
            self.import_filepath(cnx, filepath, service_infos=service_infos)
            fa = cnx.find('FindingAid').one()
            expected_fa_extptr = 'http://google.fr'
            self.assertEqual(expected_fa_extptr,
                             fa.bounce_url)
            fc_rql = 'Any X WHERE X is FAComponent, X did D, D unitid %(u)s'
            fc = cnx.execute(fc_rql, {'u': u'2 O 156/2'}).one()
            self.assertFalse(fc.did[0].extptr)
            self.assertEqual(expected_fa_extptr,
                             fc.bounce_url)

    def test_facomponent_proper_bounced_url(self):
        """ <did/unitid/extptr> was found for a FAComponent
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                'Service', code=u'FRAD034',
                category=u'L',
                search_form_url=u'http://francearchives.fr')
            cnx.commit()
            filepath = self.datapath('ir_data/FRAD034_000000248.xml')
            service_infos = {"code": service.code, 'eid': service.eid}
            self.import_filepath(cnx, filepath, service_infos=service_infos)
            fa = cnx.find('FindingAid').one()
            expected_fa_extptr = 'http://google.fr'
            self.assertFalse(fa.did[0].extptr)
            self.assertEqual(expected_fa_extptr,
                             fa.website_url)
            self.assertEqual(expected_fa_extptr,
                             fa.bounce_url)
            fc_rql = 'Any X WHERE X is FAComponent, X did D, D unitid %(u)s'
            fc = cnx.execute(fc_rql, {'u': u'test lien facomponent'}).one()
            self.assertEqual('https://francearchives.fr/file/38f8190f0295966915d3c867581eaa91a08f1fe5/integration_FA_documentation_technique.pdf', # noqa
                             fc.bounce_url)

    def test_illustration_url_FRBNF(self):
        """specific BNF case"""
        url = u'' # noqa
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                'Service', code=u'FRBNF',
                category=u'L',
                thumbnail_url=u'{url}.thumbnail')
            cnx.commit()
            service_infos = {"code": service.code, 'eid': service.eid}
            self.import_filepath(cnx,
                                 self.datapath('ir_data/FRBNF_EAD000096744.xml'),
                                 service_infos=service_infos)
            fc_rql = 'Any X WHERE X is FAComponent, X did D, D unitid %(u)s'
            fc = cnx.execute(fc_rql, {'u': u'2011/001/0474'}).one()
            self.assertEqual(fc.related_service.eid, service.eid)
            self.assertTrue(1, len(fc.digitized_versions))
            expected_url = 'https://gallica.bnf.fr/ark:/12148/btv1b530314180.thumbnail'
            self.assertEqual(expected_url, fc.illustration_url)


if __name__ == '__main__':
    unittest.main()
