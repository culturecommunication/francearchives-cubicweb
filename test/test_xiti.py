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

from mock import patch

from cubicweb import Binary
from cubicweb.devtools.testlib import CubicWebTC
from cubicweb_francearchives import views


class EntityXitiTests(CubicWebTC):
    def test_circular_chapters(self):
        with self.admin_access.cnx() as cnx:
            circular = cnx.create_entity(
                "Circular", circ_id="circ1", status="revoked", title="circ1"
            )
            self.assertEqual(circular.cw_adapt_to("IXiti").chapters, ["Circular", "circ1"])

    def test_card_chapters(self):
        with self.admin_access.cnx() as cnx:
            card = cnx.find("Card", wikiid="cgu-fr").one()
            self.assertEqual(card.cw_adapt_to("IXiti").chapters, ["Card", "cgu-fr"])

    def test_service_chapters_no_code(self):
        with self.admin_access.cnx() as cnx:
            s1 = cnx.create_entity("Service", category="cat", name="s1")
            self.assertEqual(s1.cw_adapt_to("IXiti").chapters, ["Service", "s1"])

    def test_service_chapters_zipcode(self):
        with self.admin_access.cnx() as cnx:
            s1 = cnx.create_entity("Service", category="cat", name="s1", zip_code="75013")
            self.assertEqual(s1.cw_adapt_to("IXiti").chapters, ["Service", "75013"])

    def test_service_chapters_ead_code(self):
        with self.admin_access.cnx() as cnx:
            s1 = cnx.create_entity(
                "Service", category="cat", name="s1", zip_code="75013", code="FRAD075"
            )
            self.assertEqual(s1.cw_adapt_to("IXiti").chapters, ["Service", "FRAD075"])

    def test_commemocollection_chapters(self):
        with self.admin_access.cnx() as cnx:
            coll = cnx.create_entity("CommemoCollection", year=2017, title="commemo 2017")
            self.assertEqual(coll.cw_adapt_to("IXiti").chapters, ["CommemoCollection", "2017"])

    def test_commemoitem_chapters(self):
        with self.admin_access.cnx() as cnx:
            item = cnx.create_entity(
                "CommemorationItem",
                commemoration_year=2017,
                alphatitle="foo",
                title="sortie francearchives",
            )
            self.assertEqual(
                item.cw_adapt_to("IXiti").chapters, ["Commemo", "2017", "sortie francearchives"]
            )

    def test_basecontent_chapters(self):
        with self.admin_access.cnx() as cnx:
            bc = cnx.create_entity("BaseContent", title="the-title")
            self.assertEqual(
                bc.cw_adapt_to("IXiti").chapters, ["BaseContent", bc.uuid, "the-title"]
            )

    def test_publication_chapters(self):
        with self.admin_access.cnx() as cnx:
            bc = cnx.create_entity(
                "BaseContent",
                title="the-title",
                reverse_children=cnx.create_entity(
                    "Section", title="Publication", name="publication"
                ),
            )
            self.assertEqual(
                bc.cw_adapt_to("IXiti").chapters, ["Publication", bc.uuid, "the-title"]
            )

    def test_newscontent_chapters(self):
        with self.admin_access.cnx() as cnx:
            news = cnx.create_entity("NewsContent", start_date="2017/01/01", title="the-title")
            self.assertEqual(
                news.cw_adapt_to("IXiti").chapters, ["NewsContent", news.uuid, "the-title"]
            )

    def test_map_chapters(self):
        with self.admin_access.cnx() as cnx:
            m1 = cnx.create_entity("Map", map_file=Binary(b""), title="the-title")
            self.assertEqual(m1.cw_adapt_to("IXiti").chapters, ["Map", m1.uuid, "the-title"])

    def test_findingaid_chapters_noservice(self):
        with self.admin_access.cnx() as cnx:
            fadid = cnx.create_entity("Did", unitid="maindid", unittitle="maindid-title")
            fa = cnx.create_entity(
                "FindingAid",
                name="the-fa",
                stable_id="FRAD084_xxx",
                eadid="FRAD084_xxx",
                publisher="FRAD084",
                did=fadid,
                fa_header=cnx.create_entity("FAHeader"),
            )
            self.assertEqual(
                fa.cw_adapt_to("IXiti").chapters, ["FindingAid", "unknown-service", "FRAD084_xxx"]
            )

    def test_findingaid_chapters_service(self):
        with self.admin_access.cnx() as cnx:
            fadid = cnx.create_entity("Did", unitid="maindid", unittitle="maindid-title")
            service = cnx.create_entity("Service", category="cat", code="FRAD084")
            fa = cnx.create_entity(
                "FindingAid",
                name="the-fa",
                stable_id="FRAD084_xxx",
                eadid="FRAD084_xxx",
                publisher="FRAD084",
                service=service,
                did=fadid,
                fa_header=cnx.create_entity("FAHeader"),
            )
            self.assertEqual(
                fa.cw_adapt_to("IXiti").chapters, ["FindingAid", "FRAD084", "FRAD084_xxx"]
            )

    def test_facomponent_chapters_noservice(self):
        with self.admin_access.cnx() as cnx:
            fadid = cnx.create_entity("Did", unitid="maindid", unittitle="maindid-title")
            fcdid = cnx.create_entity(
                "Did",
                unitid="fcdid",
                unittitle="fcdid-title",
                startyear=1234,
                stopyear=1245,
                origination="fc-origination",
                repository="fc-repo",
            )
            fa = cnx.create_entity(
                "FindingAid",
                name="the-fa",
                stable_id="FRAD084_xxx",
                eadid="FRAD084_xxx",
                publisher="FRAD084",
                did=fadid,
                fa_header=cnx.create_entity("FAHeader"),
            )
            facomp = cnx.create_entity(
                "FAComponent",
                finding_aid=fa,
                stable_id="fc-stable-id",
                did=fcdid,
                scopecontent="fc-scoppecontent",
                description="fc-descr",
            )
            self.assertEqual(
                facomp.cw_adapt_to("IXiti").chapters,
                ["FAComponent", "unknown-service", "fc-stable-id"],
            )

    def test_facomponent_chapters_service(self):
        with self.admin_access.cnx() as cnx:
            fadid = cnx.create_entity("Did", unitid="maindid", unittitle="maindid-title")
            fcdid = cnx.create_entity(
                "Did",
                unitid="fcdid",
                unittitle="fcdid-title",
                startyear=1234,
                stopyear=1245,
                origination="fc-origination",
                repository="fc-repo",
            )
            service = cnx.create_entity("Service", category="cat", code="FRAD084")
            fa = cnx.create_entity(
                "FindingAid",
                name="the-fa",
                stable_id="FRAD084_xxx",
                eadid="FRAD084_xxx",
                publisher="FRAD084",
                service=service,
                did=fadid,
                fa_header=cnx.create_entity("FAHeader"),
            )
            facomp = cnx.create_entity(
                "FAComponent",
                finding_aid=fa,
                stable_id="fc-stable-id",
                did=fcdid,
                scopecontent="fc-scoppecontent",
                description="fc-descr",
            )
            self.assertEqual(
                facomp.cw_adapt_to("IXiti").chapters, ["FAComponent", "FRAD084", "fc-stable-id"]
            )


def _template_context(req, vid):
    viewsreg = req.vreg["views"]
    view = viewsreg.select(vid, req, rset=None)
    tmpl = viewsreg.select("main-template", req, rset=None, view=view)
    return tmpl.template_context(view)


class ViewsNoXitiTests(CubicWebTC):
    """test suite to make sure no xiti markup is added when not configured"""

    def test_404_chapters(self):
        with self.admin_access.web_request() as req:
            ctx = _template_context(req, "404")
            self.assertNotIn("xiti", ctx)


class ViewsXitiTests(CubicWebTC):
    def setUp(self):
        super(ViewsXitiTests, self).setUp()
        # add the xiti configuration parameters required by thi test suite
        views.load_portal_config(self.config)
        views.PORTAL_CONFIG["xiti"] = {"site": "12345", "n2": "1"}

    def tearDown(self):
        super(ViewsXitiTests, self).tearDown()
        views.PORTAL_CONFIG.pop("xiti", None)

    def test_home_chapters(self):
        with self.admin_access.web_request() as req:
            ctx = _template_context(req, "index")
            self.assertDictEqual(
                ctx["xiti"],
                {
                    "site": "12345",
                    "n2": "1",
                    "pagename": "home",
                },
            )

    def test_no_department_map_chapters(self):
        with self.admin_access.web_request() as req:
            ctx = _template_context(req, "dpt-service-map")
            self.assertDictEqual(
                ctx["xiti"], {"site": "12345", "n2": "1", "pagename": "department_map"}
            )

    def test_404_chapters(self):
        with self.admin_access.web_request("some/url") as req:
            ctx = _template_context(req, "404")
            self.assertDictEqual(
                ctx["xiti"],
                {
                    "site": "12345",
                    "n2": "1",
                    "pagename": "404::some/url",
                },
            )

    @patch("cubicweb_francearchives.views.search.PniaElasticSearchView.do_search")
    def test_search_chapters(self, _search):
        with self.admin_access.web_request("inventaires") as req:
            ctx = _template_context(req, "esearch")
            self.assertDictEqual(
                ctx["xiti"],
                {
                    "site": "12345",
                    "n2": "1",
                    "pagename": "search::inventaires",
                },
            )

    @patch("cubicweb_francearchives.views.search.PniaElasticSearchView.do_search")
    def test_search_chapters_service(self, _search):
        with self.admin_access.web_request("inventaires", es_publisher="FRAD084") as req:
            ctx = _template_context(req, "esearch")
            self.assertDictEqual(
                ctx["xiti"],
                {
                    "site": "12345",
                    "n2": "1",
                    "pagename": "search::inventaires::frad084",
                },
            )

    def test_findingaid_access_to_service(self):
        with self.admin_access.cnx() as cnx:
            fadid = cnx.create_entity("Did", unitid="maindid", unittitle="maindid-title")
            service = cnx.create_entity(
                "Service",
                category="cat",
                code="FRAD084",
                search_form_url="http://francearchives.fr",
            )
            fa = cnx.create_entity(
                "FindingAid",
                name="the-fa",
                stable_id="FRAD084_xxx",
                eadid="FRAD084_xxx",
                publisher="FRAD084",
                service=service,
                did=fadid,
                fa_header=cnx.create_entity("FAHeader"),
            )
            self.assertEqual(
                fa.cw_adapt_to("IPublisherInfo").serialize()["xiti"],
                {
                    "type": "S",
                    "n2": "1",
                    "access_site": "service::frad084::site_access",
                    "thumbnail_access_site": "service::frad084::thumbnail_site_access",
                },
            )


if __name__ == "__main__":
    unittest.main()
