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

import urllib.parse

from cubicweb.devtools.testlib import CubicWebTC
from cubicweb_francearchives.testutils import PostgresTextMixin, EADImportMixin

from pgfixtures import setup_module, teardown_module  # noqa


class FaPropertiesTests(EADImportMixin, PostgresTextMixin, CubicWebTC):
    def test_findingaid_inherited_bounce_url_from_service(self):
        """Test FindingAid bounce_url. If FindingAid does not have extptr, bounce_url
        must be inherited from its related service.

        Trying: FindingAid does not have extptr and search_form_url is set on the related service
        Expecting: bounce_url is search_form_url
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                "Service", code="FRAD051", category="L", search_form_url="http://francearchives.fr"
            )
            cnx.commit()
            filepath = self.datapath("ir_data/FRAD051_est_ead_affichage.xml")
            service_infos = {"code": service.code, "eid": service.eid}
            self.import_filepath(cnx, filepath, service_infos=service_infos)
            fa = cnx.find("FindingAid").one()
            self.assertTrue(fa.related_service.eid, service.eid)
            self.assertFalse(fa.did[0].extptr)
            self.assertEqual(fa.related_service.search_form_url, fa.bounce_url)

    def test_facomponent_inherited_bounce_url_from_service(self):
        """Test FAComponent bounce_url. If neither FAComponent nor its FindingAid
        have extptr, bounce_url must be inherited from its related service.

        Trying: neither FAComponent nor its related FindingAid have extptr and
        search_form_url is set on the related service
        Expecting: bounce_url is search_form_url
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                "Service", code="FRAD051", category="L", search_form_url="http://francearchives.fr"
            )
            cnx.commit()
            filepath = self.datapath("ir_data/FRAD051_est_ead_affichage.xml")
            service_infos = {"code": service.code, "eid": service.eid}
            self.import_filepath(cnx, filepath, service_infos=service_infos)
            fc_rql = "Any X WHERE X is FAComponent, X did D, D unitid %(u)s"
            fa = cnx.find("FindingAid").one()
            self.assertFalse(fa.did[0].extptr)
            fc = cnx.execute(fc_rql, {"u": "6E 1-15863"}).one()
            self.assertFalse(fc.did[0].extptr)
            self.assertEqual(service.eid, fc.related_service.eid)
            self.assertTrue(fc.related_service.bounce_url, fc.bounce_url)

    def test_findingaid_proper_bounce_url(self):
        """Test FindingAid bounce_url. If FindingAid does not have extptr and eadid tag contains
        URL (website_url), it is used instead of inheriting from its related service.

        Trying: FindingAid does not have extptr and eadid tag contains URL
        Expecting: bounce_url is website_url
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                "Service", code="FRAD034", category="L", search_form_url="http://francearchives.fr"
            )
            cnx.commit()
            filepath = self.datapath("ir_data/FRAD034_000000248.xml")
            service_infos = {"code": service.code, "eid": service.eid}
            self.import_filepath(cnx, filepath, service_infos=service_infos)
            fa = cnx.find("FindingAid").one()
            self.assertTrue(fa.related_service.eid, service.eid)
            expected_fa_extptr = "http://google.fr"
            self.assertFalse(fa.did[0].extptr)
            self.assertEqual(expected_fa_extptr, fa.website_url)
            self.assertEqual(expected_fa_extptr, fa.bounce_url)

    def test_facomponent_inherited_bounce_url_from_findingaid(self):
        """Test FAComponent bounce_url. If FAComponent does not have extptr, it must inherit
        its FindingAid's bounce_url.

        Trying: FAComponent does not have extptr and FindingAid does not have extptr
        Expecting: bounce_url of FAComponent is bounce_url of FindingAid which is
        eadid tag's URL attribute
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                "Service", code="FRAD034", category="L", search_form_url="http://francearchives.fr"
            )
            cnx.commit()
            filepath = self.datapath("ir_data/FRAD034_000000248.xml")
            service_infos = {"code": service.code, "eid": service.eid}
            self.import_filepath(cnx, filepath, service_infos=service_infos)
            fa = cnx.find("FindingAid").one()
            expected_fa_extptr = "http://google.fr"
            self.assertEqual(expected_fa_extptr, fa.bounce_url)
            fc_rql = "Any X WHERE X is FAComponent, X did D, D unitid %(u)s"
            fc = cnx.execute(fc_rql, {"u": "2 O 156/2"}).one()
            self.assertFalse(fc.did[0].extptr)
            self.assertEqual(expected_fa_extptr, fc.bounce_url)

    def test_facomponent_proper_bounced_url(self):
        """Testing FAComponent bounce_url.

        Trying: FAComponent has extptr
        Expecting: bounce_url is extptr
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                "Service", code="FRAD034", category="L", search_form_url="http://francearchives.fr"
            )
            cnx.commit()
            filepath = self.datapath("ir_data/FRAD034_000000248.xml")
            service_infos = {"code": service.code, "eid": service.eid}
            self.import_filepath(cnx, filepath, service_infos=service_infos)
            fa = cnx.find("FindingAid").one()
            expected_fa_extptr = "http://google.fr"
            self.assertFalse(fa.did[0].extptr)
            self.assertEqual(expected_fa_extptr, fa.website_url)
            self.assertEqual(expected_fa_extptr, fa.bounce_url)
            fc_rql = "Any X WHERE X is FAComponent, X did D, D unitid %(u)s"
            fc = cnx.execute(fc_rql, {"u": "test lien facomponent"}).one()
            self.assertEqual(
                "https://francearchives.fr/file/38f8190f0295966915d3c867581eaa91a08f1fe5/integration_FA_documentation_technique.pdf",  # noqa
                fc.bounce_url,
            )

    def test_facomponent_proper_bounced_url_from_search_form_url(self):
        """Test FAComponent bounce_url.

        Trying: FAComponent has unitid and search_form_url is set on its related service
        Expecting: bounce_url is formatted search_form_url
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                "Service",
                code="FRAD039",
                category="L",
                website_url="http://www.archives39.fr/",
                search_form_url="http://archives39.fr/search?query=%(unitid)s&search-query=&search-query=1",  # noqa
            )
            cnx.commit()
            filepath = self.datapath("ir_data/FRAD039_3P_Inventaire.xml")
            service_infos = {"code": service.code, "eid": service.eid}
            self.import_filepath(cnx, filepath, service_infos=service_infos)
            fa = cnx.find("FindingAid").one()
            expected_fa_extptr = "http://archives39.fr/search?query=3P&search-query=&search-query=1"
            self.assertEqual(expected_fa_extptr, fa.bounce_url)
            unitid = "3Pplan6802/4"
            fc_rql = "Any X WHERE X is FAComponent, X did D, D unitid %(u)s"
            fc = cnx.execute(fc_rql, {"u": unitid}).one()
            q = urllib.parse.urlencode({"query": "3Pplan6802/4"})
            expected = "http://archives39.fr/search?{}&search-query=&search-query=1".format(
                q
            )  # noqa
            self.assertEqual(expected, fc.bounce_url)

    def test_facomponent_proper_bounced_url_2(self):
        """ <did/unitid/extptr> was found for a FAComponent
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity("Service", code="FRAD034", category="L")
            cnx.commit()
            filepath = self.datapath("ir_data/FRAD063_000051242.xml")
            service_infos = {"code": service.code, "eid": service.eid}
            self.import_filepath(cnx, filepath, service_infos=service_infos)
            fa = cnx.find("FindingAid").one()
            self.assertEqual(fa.did[0].extptr, "ark:/72847/vta1a56e5e06dfce452")
            self.assertFalse(fa.website_url)
            self.assertFalse(fa.bounce_url)
            fc_rql = "Any X WHERE X is FAComponent, X did D, D unitid %(u)s"
            fc = cnx.execute(fc_rql, {"u": "B MO 283, 288"}).one()
            self.assertEqual(
                "http://www.archivesdepartementales.puydedome.fr/ark:/72847/2581053",  # noqa
                fc.bounce_url,
            )

    def test_facomponent_inherited_extptr(self):
        """Test FAComponent's bounce_url. If related did does not contain
        extptr the FAComponent must inherit its FindingAid's extptr.

        Trying: FAComponent does not have extptr and FindingAid has extptr
        Expecting: FAComponent's bounce_url is FindingAid's extptr
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity("Service", code="FRAD034", category="L")
            cnx.commit()
            filepath = self.datapath("ir_data/FRAD034_000000248_extptr_on_fa.xml")
            service_infos = {"code": service.code, "eid": service.eid}
            self.import_filepath(cnx, filepath, service_infos=service_infos)
            fa = cnx.find("FindingAid").one()
            self.assertEqual(
                fa.did[0].extptr,
                (
                    "https://francearchives.fr/file/38f8190f0295966915d3c867581eaa91a08f1fe5/"
                    "integration_FA_documentation_technique.pdf"
                ),
            )
            fc = cnx.execute(
                "Any X WHERE X is FAComponent, X did D, D unitid %(unitid)s",
                {"unitid": "2 O 156/1"},
            ).one()
            self.assertEqual(fc.bounce_url, fa.did[0].extptr)

    def test_illustration_url_FRBNF(self):
        """Testing illustration_url FAComponent.

        Trying: BnF FindingAid and no dao tag contains supported role
        Expecting: URL in any dao tag is used
        """
        url = ""  # noqa
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                "Service", code="FRBNF", category="L", thumbnail_url="{url}.thumbnail"
            )
            cnx.commit()
            service_infos = {"code": service.code, "eid": service.eid}
            self.import_filepath(
                cnx, self.datapath("ir_data/FRBNF_EAD000096744.xml"), service_infos=service_infos
            )
            fc_rql = "Any X WHERE X is FAComponent, X did D, D unitid %(u)s"
            fc = cnx.execute(fc_rql, {"u": "2011/001/0474"}).one()
            self.assertEqual(fc.related_service.eid, service.eid)
            self.assertTrue(1, len(fc.digitized_versions))
            expected_url = "https://gallica.bnf.fr/ark:/12148/btv1b530314180.thumbnail"
            self.assertEqual(expected_url, fc.illustration_url)

    def test_thumbnail_dest(self):
        """Test thumbnail_dest of FAComponent.

        Trying: thumbnail_dest is not set and dao tag contains absolute URL
        Expecting: dao tag URL is used
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity("Service", code="FRBNF", category="L")
            cnx.commit()
            self.import_filepath(
                cnx,
                self.datapath("ir_data/FRBNF_EAD000096744.xml"),
                service_infos={"code": service.code, "eid": service.eid},
            )
            fa_component = cnx.execute(
                "Any X WHERE X is FAComponent, X did D, D unitid %(unitid)s",
                {"unitid": "2011/001/0474"},
            ).one()
            expected = "https://archivesetmanuscrits.bnf.fr/ark:/12148/cc96744w"
            self.assertEqual(expected, fa_component.thumbnail_dest)

    def test_facomponent_absolute_illustration_url(self):
        """Test illustration_url of FAComponent.

        Trying: each of the dao tags contains an absolute URL and supported role
        ('thumbnail', 'image')
        Expected: one of the dao tags' URL is used and not formatted
        """
        fc_rql = "Any X WHERE X is FAComponent, X did D, D unitid %(u)s"
        expected = [
            (
                "http://v-earchives.vaucluse.fr/viewer/instrument_recherche/74J_Eysseric/"
                "FRAD084_74J02_01.jpg"
            ),
            (
                "http://cdn-earchives.vaucluse.fr/prepared_images/thumb/destination/"
                "instrument_recherche/74J_Eysseric/FRAD084_74J02_01.jpg"
            ),
            (
                "http://v-earchives.vaucluse.fr/viewer/instrument_recherche/74J_Eysseric/"
                "FRAD084_74J02_02.jpg"
            ),
            (
                "http://cdn-earchives.vaucluse.fr/prepared_images/thumb/destination/"
                "instrument_recherche/74J_Eysseric/FRAD084_74J02_02.jpg"
            ),
        ]
        name, code, category = "FRAD084", "FRAD084", "foo"
        path = "ir_data/FRAD084_IR0000412.xml"
        with self.admin_access.cnx() as cnx:
            # thumbnail_url is not set
            service = cnx.create_entity("Service", category=category, name=name, code=code)
            cnx.commit()
            self.import_filepath(
                cnx, self.datapath(path), {"name": name, "eid": service.eid, "code": code,}
            )
            fc = cnx.execute(fc_rql, {"u": "74 J 2"}).one()
            # one of the dao tags' URL is used
            self.assertTrue(fc.illustration_url in expected)

    def test_facomponent_absolute_illustration_url_thumbnail_url(self):
        """Test illustration_url of FAComponent.

        Trying: dao tag contains absolute URL and supported role ('thumbnail', 'image')
        and thumbnail_url is set
        Expecting: absolute URL takes precedence and is not formatted
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                "Service",
                code="FRAD040",
                category="L",
                thumbnail_url="http://www.archives.landes.org/{url}",
            )
            cnx.commit()
            filepath = self.datapath("ir_data/FRAD040_000020FI__fiche_img.xml")
            service_infos = {"code": service.code, "eid": service.eid}
            self.import_filepath(cnx, filepath, service_infos=service_infos)
            fc_rql = "Any X WHERE X is FAComponent, X did D, D unitid %(u)s"
            fc = cnx.execute(fc_rql, {"u": "20 FI 2"}).one()
            expected = "http://www.archives.landes.fr/ark:/35227/e005a4e62d8b8759/5a4e62d8bf8b7"
            self.assertEqual(fc.illustration_url, expected)

    def test_facomponent_relative_illustration_url(self):
        """Test thumbnail_dest and illustration_url of FAComponent.

        Trying: dao tag contains relative URL and thumbnail_dest is set on its related service
        Expecting: thumbnail_dest is formatted relative URL and illustration_url is not set
        """
        thumbnail_dest = "http://{url}"
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                "Service", code="FRAD040", category="L", thumbnail_dest=thumbnail_dest
            )
            cnx.commit()
            filepath = self.datapath("ir_data/FRAD040_000020FI__fiche_img.xml")
            service_infos = {"code": service.code, "eid": service.eid}
            self.import_filepath(cnx, filepath, service_infos=service_infos)
            rql = "Any X WHERE X is FAComponent, X did D, D unitid %(unitid)s"
            fa_component = cnx.execute(rql, {"unitid": "20 FI 9"}).one()
            expected = thumbnail_dest.format(url="example.com")
            self.assertEqual(fa_component.thumbnail_dest, expected)
            self.assertIsNone(fa_component.illustration_url)

    def test_facomponent_relative_illustration_url_thumbnail_url(self):
        """Test thumbnail_dest and thumbnail_url of FAComponent.

        Trying: dao tag contains relative URL and thumbnail_url is set on its related service
        Expecting: illustration_url is formatted relative URL and thumbnail_dest is bounce_url
        """
        thumbnail_url = "http://{url}"
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                "Service", code="FRAD040", category="L", thumbnail_url=thumbnail_url
            )
            cnx.commit()
            filepath = self.datapath("ir_data/FRAD040_000020FI__fiche_img.xml")
            service_infos = {"code": service.code, "eid": service.eid}
            self.import_filepath(cnx, filepath, service_infos=service_infos)
            rql = "Any X WHERE X is FAComponent, X did D, D unitid %(unitid)s"
            fa_component = cnx.execute(rql, {"unitid": "20 FI 9"}).one()
            expected = thumbnail_url.format(url="example.com")
            self.assertEqual(fa_component.thumbnail_dest, fa_component.bounce_url)
            self.assertEqual(fa_component.illustration_url, expected)


if __name__ == "__main__":
    unittest.main()
