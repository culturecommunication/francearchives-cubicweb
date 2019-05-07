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

from cubicweb.devtools import testlib
from cubicweb import NoResultError

from cubicweb_francearchives.dataimport.directories import import_directory, get_dpt_code


class ImportDirectoryTC(testlib.CubicWebTC):

    def test_dpt_code_computation(self):
        res = get_dpt_code('2000')
        self.assertEqual(res, '02')
        res = get_dpt_code('3200')
        self.assertEqual(res, '03')
        res = get_dpt_code('20090')
        self.assertEqual(res, '2A')
        res = get_dpt_code('20200')
        self.assertEqual(res, '2B')
        res = get_dpt_code('20410')
        self.assertEqual(res, '2B')
        res = get_dpt_code('97150')
        self.assertEqual(res, '978')

    def test_import_directory(self):
        filepath = self.datapath('directory.csv')
        departements = self.datapath('departements.csv')
        logos_services = self.datapath('logos_services')
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but('es'):
                import_directory(cnx, filepath,
                                 departements, logos_services)
                cnx.commit()
                services = cnx.find('Service')
                # 15 services from filepath
                # 7 services from departements
                self.assertEqual(len(services), 21)
                # service from filepath, updated with departements info
                gard = cnx.find('Service', category=u'Département du Gard').one()
                self.assertEqual(gard.code, u'FRAD030')
                self.assertEqual(gard.name, u'Archives départementales')
                self.assertEqual(gard.name2, u'Service truc')
                self.assertEqual(gard.short_name, u'AD du Gard')
                self.assertEqual(gard.address, u'365 rue du Forez')
                self.assertEqual(gard.zip_code, '30000')
                self.assertEqual(gard.city, u'Nîmes')
                self.assertEqual(gard.website_url, u'http://archives.gard.fr')
                self.assertEqual(gard.browser_url, u'http://archives.gard.fr')
                self.assertEqual(gard.search_form_url, u'')
                self.assertEqual(gard.contact_name, u'Nadine Rouayroux')
                self.assertEqual(gard.phone_number, u'04.66.05.05.10')
                self.assertEqual(gard.fax, u'04.66.05.05.55')
                self.assertEqual(gard.email, u'archives@gard.fr')
                self.assertEqual(gard.annual_closure, u'se renseigner')
                self.assertEqual(gard.level, u'level-D')
                self.assertEqual(gard.opening_period, u'Lu.-Ve. 8 h 30 à 17 h')
                rset = cnx.execute('Any X WHERE X is Service, X annex_of Y')
                # self.assertNotEqual(len(rset), 0)
                rset = cnx.execute('Any X WHERE X is SocialNetwork, '
                                   'S service_social_network X')
                self.assertNotEqual(len(rset), 0)
                logo = gard.service_image[0]
                self.assertEqual(logo.caption, u'Logo')
                self.assertTrue(len(logo.image_file[0].data.getvalue()))
                # service from departements
                lot = cnx.find('Service',
                               category=u'Archives départementales du Lot').one()
                self.assertEqual(lot.name, None)
                self.assertEqual(lot.name2, u'Archives d\xe9partementales du Lot')
                self.assertEqual(lot.short_name, u'AD du Lot')
                self.assertEqual(lot.browser_url, u'http://archives.lot.fr/')
                self.assertEqual(lot.search_form_url,
                                 u'http://archives.lot.fr/search')
                # FRANOM
                franom = cnx.find('Service', code=u'FRANOM').one()
                self.assertEqual(franom.name, None)
                self.assertTrue(len(franom.service_image[0].image_file[0].data.getvalue()))
                # `concaténation` service from csv header is not created
                with self.assertRaises(NoResultError):
                    cnx.find('Service', code=u'concaténation').one()
                # test addresses
                cannes = cnx.find('Service',
                                  name2=u'Archives municipales de la commune de Cannes').one()
                self.assertEqual(cannes.address, u'9 avenue Montrose')
                self.assertEqual(cannes.zip_code, '6400')
                self.assertEqual(cannes.city, u'Cannes')
                self.assertEqual(cannes.mailing_address,
                                 u'Hôtel de ville, CS 30140,  Cannes Cedex')
                # FRAN
                fran = cnx.find('Service', code=u'FRAN').one()
                self.assertEqual(fran.name, u'Archives nationales')
                self.assertEqual(fran.name2, None)
                self.assertEqual(fran.short_name, u'Archives nationales')
                self.assertEqual(fran.browser_url,
                                 u'http://www.archives-nationales.culture.gouv.fr/')
                self.assertEqual(fran.level, u'level-N')
                self.assertEqual(fran.address, u'59 rue Guynemer')
                self.assertEqual(fran.zip_code, '93383')
                self.assertEqual(fran.city, u'Pierrefitte-sur-Seine')
                self.assertEqual(fran.mailing_address, None)
                self.assertEqual(fran.phone_number, u'01.75.47.20.02')
                martin = cnx.find('Service', category=u'Collectivité de Saint-Martin').one()
                self.assertEqual(martin.dpt_code, '978')
                gironde = cnx.find('Service', code=u'FRAD033').one()
                self.assertEqual(gironde.level, u'level-D')


if __name__ == '__main__':
    unittest.main()
