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
import json

from mock import patch

from elasticsearch_dsl.search import Search
from elasticsearch_dsl.response import Response as ESResponse

from logilab.common.registry import yes

from pyramid.response import Response

from cubicweb.view import EntityView
from cubicweb.pyramid.test import PyramidCWTest

from cubicweb_francearchives.utils import merge_dicts
from cubicweb_francearchives.testutils import PostgresTextMixin
from pgfixtures import setup_module, teardown_module  # noqa

BASE_SETTINGS = {
    "cubicweb.bwcompat": "no",
    "cubicweb.session.secret": "stuff",
    "cubicweb.auth.authtkt.session.secret": "stuff",
    "cubicweb.auth.authtkt.persistent.secret": "stuff",
}


def mock_maintemplate_call(self, view):
    self.w(view.render())


class BWCompatRoutesTests(PostgresTextMixin, PyramidCWTest):
    settings = BASE_SETTINGS

    def setUp(self):
        super(BWCompatRoutesTests, self).setUp()
        self.config.global_set_option("appfiles-dir", self.datapath("appfiles"))

    def test_data_assets_route(self):
        self.webapp.get("/data/cubicweb.js", status=200)
        self.webapp.get("/data/icons/manifest.json", status=200)
        self.webapp.get("/data/this-resource-does-not-exist.css", status=404)

    def test_static_assets_route(self):
        self.webapp.get("/static/foo.css", status=404)
        resp = self.webapp.get("/static/subdir/static.txt", status=200)
        self.assertEqual(resp.body, b"hello static\n")

    def test_redirect_static_route(self):
        self.webapp.get("/static/9001", status=404)
        resp = self.webapp.get("/static/1023", status=302)
        self.assertTrue(
            resp.headers["location"].endswith(
                "file/dcdc24e139db869eb059c9355c89c382de15b987/static_1023.txt"
            )
        )

    def test_restpath_primaryview_route(self):
        self.webapp.get("/basecontent/1").follow(status=404)
        with self.admin_access.cnx() as cnx:
            bc = cnx.create_entity("BaseContent", title="the-article-title")
            cnx.commit()
        resp = self.webapp.get("/basecontent/{}".format(bc.eid), status=200)
        self.assertIn("<h1>{}</h1>".format(bc.title).encode("utf-8"), resp.body)

    @patch("cubicweb_francearchives.views.search.PniaElasticSearchView.customize_search")
    @patch("elasticsearch_dsl.search.Search.execute")
    @patch("elasticsearch_dsl.connections.connections.get_connection")
    def test_restpath_listview_route(self, cnxfactory, _execute, customize_search):
        self.webapp.get("/NewsContent", status=303)  # redirect to fuzzy search
        customize_search.assert_called_with("", {"cw_etype": "NewsContent"}, 0, 10)

    def test_lang_prefix(self):
        with self.admin_access.cnx() as cnx:
            bc = cnx.create_entity("BaseContent", title="the-article-title")
            cnx.commit()
        resp = self.webapp.get("/fr/basecontent/{}".format(bc.eid))
        self.assertEqual(resp.headers["content-language"], "fr")
        resp = self.webapp.get("/de/basecontent/{}".format(bc.eid))
        self.assertEqual(resp.headers["content-language"], "de")
        resp = self.webapp.get("/en/basecontent/{}".format(bc.eid))
        self.assertEqual(resp.headers["content-language"], "en")
        resp = self.webapp.get("/basecontent/{}".format(bc.eid))
        self.assertEqual(resp.headers["content-language"], "fr")
        self.webapp.get("/xx/basecontent/{}".format(bc.eid)).follow(status=404)


def mock_primary_view(entity_call):
    class MockPrimaryView(EntityView):
        __regid__ = "primary"
        __select__ = yes(42)  # make sure it is selected

        def entity_call(self, entity):
            self.w(entity_call(entity))

    return MockPrimaryView


class FARoutesTests(PostgresTextMixin, PyramidCWTest):
    settings = BASE_SETTINGS

    @patch(
        "cubicweb_francearchives.views.templates.PniaMainTemplate.call", new=mock_maintemplate_call
    )
    def test_commemoview(self):
        with self.admin_access.cnx() as cnx:
            coll = cnx.create_entity("CommemoCollection", title="recueil 2010", year=2010)
            commemo = cnx.create_entity(
                "CommemorationItem",
                title="item1",
                alphatitle="item1",
                commemoration_year=2010,
                collection_top=coll,
            )
            cnx.commit()

        mock_view = mock_primary_view(lambda e: "commemo {}".format(e.commemoration_year))
        with self.temporary_appobjects(mock_view):
            resp = self.webapp.get("/commemo/recueil-2010/{}".format(commemo.eid))
            self.assertEqual(resp.body, b"commemo 2010")

    @patch(
        "cubicweb_francearchives.views.templates.PniaMainTemplate.call", new=mock_maintemplate_call
    )
    def test_topsection(self):
        with self.admin_access.cnx() as cnx:
            cnx.create_entity("Section", name="gerer", title="gerer")
            cnx.commit()

        mock_view = mock_primary_view(lambda e: "section {}".format(e.name))

        with self.temporary_appobjects(mock_view):
            resp = self.webapp.get("/gerer")
            self.assertEqual(resp.body, b"section gerer")
            self.webapp.get("/gererrr").follow(status=404)

    @patch(
        "cubicweb_francearchives.views.templates.PniaMainTemplate.call", new=mock_maintemplate_call
    )
    def test_entrypoint_cards(self):
        with self.admin_access.cnx() as cnx:
            cnx.execute('SET C content "foo" WHERE C wikiid "cgu-fr"')
            cnx.commit()
        mock_view = mock_primary_view(lambda e: "card {}".format(e.title))

        with self.temporary_appobjects(mock_view):
            resp = self.webapp.get("/cgu")
            self.assertEqual(resp.body, "card Conditions générales d'utilisation".encode("utf-8"))

    @unittest.skip("Disable this test until pyramid 1.10 is pinned")
    @patch(
        "cubicweb_francearchives.views.templates.PniaMainTemplate.call", new=mock_maintemplate_call
    )
    def test_commemocoll(self):
        with self.admin_access.cnx() as cnx:
            cnx.create_entity("CommemoCollection", title="recueil 2010", year=2010)
            cnx.commit()
        mock_view = mock_primary_view(lambda e: "recueil {}".format(e.year))
        with self.temporary_appobjects(mock_view):
            resp = self.webapp.get("/commemo/recueil-2010", status=307)
            self.assertEqual(resp.location, "https://localhost:80/commemo/recueil-2010/")
            # test with slash
            resp = self.webapp.get("/commemo/recueil-2010/")
            self.assertEqual(resp.body, b"recueil 2010")

    def test_noresult_yields_404(self):
        self.webapp.get("/findingaid/abc123/rdf.xml", status=404)


class SanitizeTweenMixin(object):
    settings = merge_dicts(
        {},
        BASE_SETTINGS,
        {
            "francearchives.autoinclude": "no",
        },
    )

    def includeme(self, config):
        config.add_route("dumpform", "/dumpform")
        config.add_view(
            lambda req: Response(json.dumps(req.cw_request.form)), route_name="dumpform"
        )
        config.include("cubicweb_francearchives.pviews.cwroutes")
        config.include("cubicweb_francearchives.pviews.tweens")


class SanitizeParameterTest(SanitizeTweenMixin, PyramidCWTest):
    def test_sanitized(self):
        resp = self.webapp.get("/dumpform")
        self.assertDictEqual({}, json.loads(resp.text))
        resp = self.webapp.get("/dumpform?x=y&z=t")
        self.assertDictEqual({"x": "y", "z": "t"}, json.loads(resp.text))
        resp = self.webapp.get("/dumpform?x=y&z=t&vid=foo&rql=Any X&debug-es")
        self.assertDictEqual({"x": "y", "z": "t"}, json.loads(resp.text))


class NoSanitizeParameterTest(SanitizeTweenMixin, PyramidCWTest):
    settings = merge_dicts(
        {},
        SanitizeTweenMixin.settings,
        {
            "francearchives.sanitize_params": "no",
        },
    )

    def test_not_sanitized(self):
        resp = self.webapp.get("/dumpform")
        self.assertDictEqual({}, json.loads(resp.text))
        resp = self.webapp.get("/dumpform?x=y&z=t")
        self.assertDictEqual({"x": "y", "z": "t"}, json.loads(resp.text))
        resp = self.webapp.get("/dumpform?x=y&z=t&vid=foo&rql=Any X")
        self.assertDictEqual(
            {"x": "y", "z": "t", "vid": "foo", "rql": "Any X"}, json.loads(resp.text)
        )


def es_autosuggest_response(count):
    def _result(i):
        return {
            "_source": {
                "description": "test",
                "cwuri": "http://example.org/{}".format(i),
                "urlpath": "agent/{}".format(i),
                "eid": i,
                "cw_etype": "PniaAgent",
                "type": "persname",
                "text": "hello",
                "normalized": "hello",
                "count": i + 1,
                "additional": "",
            },
            "_type": "PniaAgent",
            "_score": 1,
        }

    def _search(*args, **kwargs):
        search = Search(doc_type="_doc", index="text_suggest")
        return ESResponse(
            search,
            {
                "hits": {
                    "hits": [_result(i) for i in range(count)],
                    "total": count,
                }
            },
        )

    return _search


class ESRouteTests(PyramidCWTest):
    settings = BASE_SETTINGS

    @patch("elasticsearch_dsl.search.Search.execute", new=es_autosuggest_response(2))
    @patch("elasticsearch_dsl.connections.connections.get_connection")
    def test_es_suggest_view(self, cnxfactory):
        resp = self.webapp.get("/_suggest?q=foo")
        self.assertListEqual(
            json.loads(resp.text),
            [
                {
                    "url": "http://testing.fr/cubicweb/agent/0",
                    "etype": "persname",
                    "text": "hello",
                    "additional": "",
                    "countlabel": "1 document",
                },
                {
                    "url": "http://testing.fr/cubicweb/agent/1",
                    "etype": "persname",
                    "text": "hello",
                    "additional": "",
                    "countlabel": "2 documents",
                },
            ],
        )


class NewsLetterTests(PyramidCWTest):
    settings = merge_dicts(
        {},
        BASE_SETTINGS,
        {
            "francearchives.autoinclude": "no",
        },
    )

    def includeme(self, config):
        config.include("cubicweb_francearchives.pviews")
        config.include("cubicweb_francearchives.pviews.edit")

    def test_newsletter_csv_export(self):
        with self.admin_access.cnx() as cnx:
            nls1 = cnx.create_entity("NewsLetterSubscriber", email="test1@test.fr")
            nls2 = cnx.create_entity("NewsLetterSubscriber", email="test2@test.fr")
            cnx.commit()
            res = self.webapp.get("/nlsexport", status=200)
            self.assertEqual(
                res.body,
                "test1@test.fr,{}\ntest2@test.fr,{}\n".format(
                    nls1.creation_date,
                    nls2.creation_date,
                ).encode("utf-8"),
            )


class CatchAllTC(PostgresTextMixin, PyramidCWTest):
    settings = BASE_SETTINGS

    def test_with_segment_is_enlarged_etype(self):
        """with ``segment_is_enlarged_etype`` predicate ``restpath`` route
        is still selectable"""
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            fadid = ce(
                "Did", unitid="maindid", extptr="http://www.fa-url", unittitle="maindid-title"
            )
            fa = ce(
                "FindingAid",
                name="the-fa",
                stable_id="FRAD084_xxx",
                eadid="FRAD084_xxx",
                publisher="FRAD084",
                did=fadid,
                fa_header=ce("FAHeader"),
            )
            cnx.commit()
            url = fa.rest_path()
        self.webapp.get(
            "/%s" % url,
            status=200,
            headers={
                "Accept": (
                    "text/html,application/xhtml+xml," "application/xml;q=0.9,image/webp,*/*;q=0.8"
                )
            },
        )


class CSVExportTests(PostgresTextMixin, PyramidCWTest):
    settings = merge_dicts(
        {},
        BASE_SETTINGS,
        {
            "francearchives.autoinclude": "no",
        },
    )

    def includeme(self, config):
        config.include("cubicweb_francearchives.pviews")

    def setup_database(self):
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            service = ce("Service", code="FRAD084", name="fc_service", category="test")
            fadid = ce(
                "Did",
                unitid="maindid",
                extptr="http://www.fa-url",
                origination="fc-origination",
                repository="fc-repo",
                unittitle="maindid-title",
            )
            fcdid = ce(
                "Did",
                unitid="fcdid",
                unittitle="fcdid-title",
                startyear=1234,
                stopyear=1245,
                extptr="http://www.fc-url",
                origination="fc-origination",
                repository="fc-repo",
            )
            fa = ce(
                "FindingAid",
                name="the-fa",
                stable_id="FRAD084_xxx",
                eadid="FRAD084_xxx",
                publisher="FRAD084",
                did=fadid,
                service=service,
                description="<div>fa-descr<br></div>",
                acquisition_info="""<div class="ead-section ead-acqinfo"><div class="ead-label">acquisition_info</div></div>""",  # noqa
                fa_header=ce("FAHeader"),
            )
            facomp = ce(
                "FAComponent",
                finding_aid=fa,
                stable_id="fc-stable-id",
                did=fcdid,
                scopecontent='<div class="ead-section"><div class="ead-wrapper">éaô fc-scoppecontent</div></div>',  # noqa
                description="<div>fc-descr</div>",
            )
            savonarole = ce(
                "AgentAuthority",
                label="Jérôme Savonarole",
                reverse_authority=ce(
                    "Person", name="Savonarole", forenames="Jérôme", publisher="nomina"
                ),
            )
            ce(
                "AgentName",
                type="persname",
                label="Jérôme Savonarole",
                authority=savonarole,
                index=facomp,
            )
            paris = ce(
                "LocationAuthority",
                label="Paris",
                same_as=ce("ExternalUri", uri="https://fr.wikipedia.org/wiki/Paris"),
            )
            ce("Geogname", label="Paris", authority=paris, index=fa)
            coll = cnx.create_entity("CommemoCollection", title="recueil 2010", year=2010)
            election = ce("SubjectAuthority", label="Élection")
            ce("Subject", label="Élection", authority=election)
            cnx.create_entity(
                "CommemorationItem",
                title="Élection",
                alphatitle="election",
                commemoration_year=2010,
                collection_top=coll,
                related_authority=election,
            )
            cnx.commit()
            self.fa_eid = fa.eid
            self.facomp_eid = facomp.eid

    def test_facomponent_csv_export(self):
        with self.admin_access.cnx() as cnx:
            facomp = cnx.find("FAComponent", eid=self.facomp_eid).one()
            res = self.webapp.get("/facomponent/%s.csv" % facomp.stable_id, status=200)
            expected = """\
title_label,period_label,publisher_label,scopecontent_label,unitid_label,related_finding_aid_label,bioghist_label,description_label,repository_label,persname_index_label
fcdid-title,1234 - 1245,fc_service,éaô fc-scoppecontent,fcdid,maindid-title,fc-origination,fc-descr,fc-repo,Jérôme Savonarole
"""  # noqa
            self.assertEqual(res.body, expected.encode("utf-8"))

    def test_facomponent_with_unitdate_csv_export(self):
        """check did.unitdate label is exported if {start,stop}year is not set"""
        with self.admin_access.cnx() as cnx:
            facomp = cnx.find("FAComponent", eid=self.facomp_eid).one()
            facomp.did[0].cw_set(startyear=None, stopyear=None, unitdate="some hard-to-parse date")
            cnx.commit()
            res = self.webapp.get("/facomponent/%s.csv" % facomp.stable_id, status=200)
            expected = """\
title_label,period_label,publisher_label,scopecontent_label,unitid_label,related_finding_aid_label,bioghist_label,description_label,repository_label,persname_index_label
fcdid-title,some hard-to-parse date,fc_service,éaô fc-scoppecontent,fcdid,maindid-title,fc-origination,fc-descr,fc-repo,Jérôme Savonarole
"""  # noqa
            self.assertEqual(res.body, expected.encode("utf-8"))

    def test_findingaid_csv_export(self):
        with self.admin_access.cnx() as cnx:
            fa = cnx.find("FindingAid", eid=self.fa_eid).one()
            res = self.webapp.get("/findingaid/%s.csv" % fa.stable_id, status=200)
            expected = """\
title_label,publisher_label,unitid_label,eadid_label,bioghist_label,acquisition_info_label,description_label,repository_label,geo_indexes_label
maindid-title,fc_service,maindid,FRAD084_xxx,fc-origination,acquisition_info,fa-descr,fc-repo,Paris
"""  # noqa
            self.assertEqual(res.body, expected.encode("utf-8"))

    def test_findingaid_with_unitdate_csv_export(self):
        """check did.unitdate label is exported if {start,stop}year is not set"""
        with self.admin_access.cnx() as cnx:
            fa = cnx.find("FindingAid", eid=self.fa_eid).one()
            fa.did[0].cw_set(unitdate="some hard-to-parse date")
            cnx.commit()
            res = self.webapp.get("/findingaid/%s.csv" % fa.stable_id, status=200)
            expected = """\
title_label,period_label,publisher_label,unitid_label,eadid_label,bioghist_label,acquisition_info_label,description_label,repository_label,geo_indexes_label
maindid-title,some hard-to-parse date,fc_service,maindid,FRAD084_xxx,fc-origination,acquisition_info,fa-descr,fc-repo,Paris
"""  # noqa
            self.assertEqual(res.body, expected.encode("utf-8"))

    def test_alignement_csv_export(self):
        with self.admin_access.cnx() as cnx:
            location_eid = cnx.find("LocationAuthority", label="Paris").one().eid
            res = self.webapp.get("/alignment.csv")
            expected = """\
index_entry,index_url,aligned_url
Paris,http://testing.fr/cubicweb/location/{},https://fr.wikipedia.org/wiki/Paris
""".format(
                location_eid
            )
            self.assertEqual(res.body, expected.encode("utf-8"))

    def test_indices_agent_csv_export(self):
        with self.admin_access.cnx() as cnx:
            res = self.webapp.get("/indices-agent.csv")
            facomp = cnx.find("FAComponent", eid=self.facomp_eid).one()
            expected = """\
index_entry,index_type,documents
Jérôme Savonarole,persname,http://testing.fr/cubicweb/facomponent/{}
""".format(
                facomp.stable_id
            )
            self.assertEqual(res.body, expected.encode("utf-8"))

    def test_indices_location_csv_export(self):
        with self.admin_access.cnx():
            res = self.webapp.get("/indices-location.csv")
            expected = """\
index_entry,index_type,documents
Paris,geogname,http://testing.fr/cubicweb/findingaid/FRAD084_xxx
"""
            self.assertEqual(res.body, expected.encode("utf-8"))

    def test_indices_subject_csv_export(self):
        with self.admin_access.cnx() as cnx:
            res = self.webapp.get("/indices-subject.csv")
            comitem = cnx.find("CommemorationItem", alphatitle="election").one()
            expected = """\
index_entry,index_type,documents
Élection,subject,http://testing.fr/cubicweb/{}
""".format(
                comitem.rest_path()
            )
            self.assertEqual(res.body, expected.encode("utf-8"))


class FaFCDataMixin(object):
    def setup_database(self):
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            fadid = ce("Did", unitid="maindid", unittitle="maindid-title")
            fcdid = ce(
                "Did",
                unitid="fcdid",
                unittitle="fcdid-title",
                startyear=1234,
                stopyear=1245,
                origination="fc-origination",
                repository="fc-repo",
            )
            dv = ce(
                "DigitizedVersion",
                illustration_url="//archive/FRAD021_Photot\xe8que/_12NUM_0021\\FRAD021_12NUM_0021_00001.jpg",  # noqa
            )
            fa = ce(
                "FindingAid",
                name="the-fa",
                stable_id="FRAD084_xxx",
                eadid="FRAD084_xxx",
                publisher="FRAD084",
                did=fadid,
                fa_header=ce("FAHeader"),
            )
            facomp = ce(
                "FAComponent",
                finding_aid=fa,
                stable_id="fc-stable-id",
                did=fcdid,
                digitized_versions=dv,
                scopecontent="<div>fc-scoppecontent</div>",
                description="<div>fc-descr</div>",
            )
            valjean = ce("SubjectAuthority", label="Jean Valjean")
            ce("Subject", label="Jean Valjean", authority=valjean, index=facomp)
            cnx.commit()
            self.fa_eid = fa.eid
            self.facomp_eid = facomp.eid


class ContentNegociationTests(PostgresTextMixin, FaFCDataMixin, PyramidCWTest):
    settings = BASE_SETTINGS

    def assertCorrectNegociation(self, accept_header, tested_url, mimetype, starts=None):
        headers = {}
        if accept_header:
            headers = {"Accept": accept_header}
        res = self.webapp.get(tested_url, status=200, headers=headers)
        self.assertEqual(res.headers["Content-Type"], mimetype)
        if starts:
            self.assertEqual(res.body[: len(starts)], starts.encode("utf-8"))

    def test_content_html_response(self):
        with self.admin_access.cnx() as cnx:
            facomp = cnx.find("FAComponent", eid=self.facomp_eid).one()
            url = "/facomponent/{}".format(facomp.stable_id)
            accept = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            self.assertCorrectNegociation(
                accept, url, "text/html;charset=UTF-8", starts="<!doctype html"
            )

    def test_content_rdf_xml_response(self):
        with self.admin_access.cnx() as cnx:
            facomp = cnx.find("FAComponent", eid=self.facomp_eid).one()
            url = "/facomponent/{}".format(facomp.stable_id)
            accept = "application/rdf+xml"
            self.assertCorrectNegociation(
                accept, url, "{}; charset=UTF-8".format(accept), starts="<?xml"
            )

    def test_content_rdf_n3_response(self):
        with self.admin_access.cnx() as cnx:
            facomp = cnx.find("FAComponent", eid=self.facomp_eid).one()
            url = "/facomponent/{}".format(facomp.stable_id)
            accept = "text/rdf+n3"
            self.assertCorrectNegociation(
                accept, url, "{}; charset=UTF-8".format(accept), starts="@prefix"
            )

    def test_content_rdf_nt_response(self):
        with self.admin_access.cnx() as cnx:
            fa = cnx.find("FindingAid", eid=self.fa_eid).one()
            url = "/findingaid/{}".format(fa.stable_id)
            accept = "text/plain"
            self.assertCorrectNegociation(
                accept, url, "{}; charset=UTF-8".format(accept), starts="<http:"
            )

    def test_content_rdf_ttl_response(self):
        with self.admin_access.cnx() as cnx:
            facomp = cnx.find("FAComponent", eid=self.facomp_eid).one()
            url = "/facomponent/{}".format(facomp.stable_id)
            accept = "application/x-turtle"
            self.assertCorrectNegociation(accept, url, accept, starts="@prefix")

    def test_content_rdf_jsld_response(self):
        with self.admin_access.cnx() as cnx:
            fa = cnx.find("FindingAid", eid=self.fa_eid).one()
            url = "/findingaid/{}".format(fa.stable_id)
            accept = "application/ld+json"
            self.assertCorrectNegociation(accept, url, accept, starts="{")


if __name__ == "__main__":
    unittest.main()
