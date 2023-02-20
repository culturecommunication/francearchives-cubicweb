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
import datetime
import unittest
from itertools import chain

from mock import patch

from cubicweb.devtools.testlib import CubicWebTC

from cubicweb_francearchives import SUPPORTED_LANGS
from cubicweb_francearchives.testutils import PostgresTextMixin
from pgfixtures import setup_module, teardown_module  # noqa


def lang_urls(rest_path):
    urls = ["^/{}$".format(rest_path)]
    for lang in SUPPORTED_LANGS:
        urls.append("^/{}/{}$".format(lang, rest_path))
    return urls


class VarnishTests(PostgresTextMixin, CubicWebTC):
    def setUp(self):
        super(VarnishTests, self).setUp()
        self.config.global_set_option("varnishcli-hosts", "127.0.0.1:6082")
        self.config.global_set_option("varnish-version", 4)

    def assertBanned(self, call_args_list, urls):
        ban_commands = [("ban req.url ~", url) for url in urls]
        self.assertCountEqual([call[0] for call in call_args_list], ban_commands)

    @patch("cubicweb_varnish.varnishadm.VarnishCLI.execute")
    @patch("cubicweb_varnish.varnishadm.VarnishCLI.connect")
    def test_newscontent_homepage(self, _connect, cli_execute):
        with self.admin_access.cnx() as cnx:
            news = cnx.create_entity(
                "NewsContent", title="title", start_date=datetime.datetime(2015, 10, 12)
            )
            cnx.commit()
            # first we set on_homepage so we should purge homepage
            cli_execute.reset_mock()
            news.cw_set(on_homepage="onhp_hp")
            cnx.commit()
            rest_path = news.rest_path()
            self.assertBanned(
                cli_execute.call_args_list,
                chain(
                    lang_urls(rest_path),
                    lang_urls("actualite"),
                    lang_urls("actualites"),
                    lang_urls("sitemap"),
                    lang_urls("gerer"),
                    lang_urls(""),
                ),
            )
            # then we reset on_homepage so news is not on home page anymore
            # we should purge homepage again
            cli_execute.reset_mock()
            news.cw_set(on_homepage=None)
            cnx.commit()
            rest_path = news.rest_path()
            self.assertBanned(
                cli_execute.call_args_list,
                chain(
                    lang_urls(rest_path),
                    lang_urls("actualite"),
                    lang_urls("actualites"),
                    lang_urls("sitemap"),
                    lang_urls("gerer"),
                    lang_urls(""),
                ),
            )
            # finally we change title but we should not purge home page
            cli_execute.reset_mock()
            news.cw_set(title="title2")
            cnx.commit()
            rest_path = news.rest_path()
            self.assertBanned(
                cli_execute.call_args_list,
                chain(
                    lang_urls(rest_path),
                    lang_urls("actualite"),
                    lang_urls("actualites"),
                    lang_urls("sitemap"),
                ),
            )

    @patch("cubicweb_varnish.varnishadm.VarnishCLI.execute")
    @patch("cubicweb_varnish.varnishadm.VarnishCLI.connect")
    def test_basecontent_cache_invalidation(self, _connect, cli_execute):
        with self.admin_access.cnx() as cnx:
            basecontent = cnx.create_entity("BaseContent", title="title")
            cnx.commit()
            cli_execute.reset_mock()
            basecontent.cw_set(title="title2")
            cnx.commit()
            rest_path = basecontent.rest_path()
            self.assertBanned(
                cli_execute.call_args_list,
                chain(
                    lang_urls(rest_path),
                    lang_urls("article"),
                    lang_urls("articles"),
                    lang_urls("sitemap"),
                ),
            )

    @patch("cubicweb_varnish.varnishadm.VarnishCLI.execute")
    @patch("cubicweb_varnish.varnishadm.VarnishCLI.connect")
    def test_circular_cache_invalidation(self, _connect, cli_execute):
        with self.admin_access.cnx() as cnx:
            circular = cnx.create_entity(
                "Circular", title="circ1", circ_id="circ1", status="revoked"
            )
            cnx.commit()
            cli_execute.reset_mock()
            circular.cw_set(title="circ2")
            cnx.commit()
            rest_path = circular.rest_path()
            self.assertBanned(
                cli_execute.call_args_list,
                chain(
                    lang_urls(rest_path),
                    lang_urls("circulaire"),
                    lang_urls("circulaires"),
                    lang_urls("sitemap"),
                ),
            )

    @patch("cubicweb_varnish.varnishadm.VarnishCLI.execute")
    @patch("cubicweb_varnish.varnishadm.VarnishCLI.connect")
    def test_service_cache_invalidation(self, _connect, cli_execute):
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity("Service", category="s1")
            cnx.commit()
            cli_execute.reset_mock()
            service.cw_set(category="s2")
            cnx.commit()
            rest_path = service.rest_path()
            self.assertBanned(
                cli_execute.call_args_list,
                chain(lang_urls(rest_path), lang_urls("annuaire"), lang_urls("services")),
            )

    @patch("cubicweb_varnish.varnishadm.VarnishCLI.execute")
    @patch("cubicweb_varnish.varnishadm.VarnishCLI.connect")
    def test_card_cache_invalidation(self, _connect, cli_execute):
        with self.admin_access.cnx() as cnx:
            card = cnx.create_entity("Card", wikiid="about-mi", title="about")
            cnx.commit()
            cli_execute.reset_mock()
            card.cw_set(title="about again")
            cnx.commit()
            self.assertBanned(cli_execute.call_args_list, chain(lang_urls("about")))

    @patch("cubicweb_varnish.varnishadm.VarnishCLI.execute")
    @patch("cubicweb_varnish.varnishadm.VarnishCLI.connect")
    def test_section_cache_invalidation(self, _connect, cli_execute):
        with self.admin_access.cnx() as cnx:
            section = cnx.create_entity("Section", title="s1")
            cnx.commit()
            cli_execute.reset_mock()
            section.cw_set(title="s2")
            cnx.commit()
            rest_path = section.rest_path()
            self.assertBanned(
                cli_execute.call_args_list, chain(lang_urls(rest_path), lang_urls("sitemap"))
            )

    @patch("cubicweb_varnish.varnishadm.VarnishCLI.execute")
    @patch("cubicweb_varnish.varnishadm.VarnishCLI.connect")
    def test_section_ancestors_cache_invalidation(self, _connect, cli_execute):
        """make sure section ancestors are also purged"""
        with self.admin_access.cnx() as cnx:
            s3 = cnx.create_entity("Section", title="s3")
            s2 = cnx.create_entity("Section", title="s2", children=s3)
            s1 = cnx.create_entity("Section", title="s1", children=s2)
            cnx.commit()
            cli_execute.reset_mock()
            s3.cw_set(title="s3bis")
            cnx.commit()
            s1_rest_path = s1.rest_path()
            s2_rest_path = s2.rest_path()
            s3_rest_path = s3.rest_path()
            self.assertBanned(
                cli_execute.call_args_list,
                chain(
                    lang_urls(s1_rest_path),
                    lang_urls(s2_rest_path),
                    lang_urls(s3_rest_path),
                    lang_urls("sitemap"),
                ),
            )

    @patch("cubicweb_varnish.varnishadm.VarnishCLI.execute")
    @patch("cubicweb_varnish.varnishadm.VarnishCLI.connect")
    def test_topsection_cache_invalidation(self, _connect, cli_execute):
        """make sure topsection dedicated urls are also purged"""
        with self.admin_access.cnx() as cnx:
            section = cnx.create_entity("Section", title="s1", name="decouvrir")
            cnx.commit()
            cli_execute.reset_mock()
            section.cw_set(title="s2")
            cnx.commit()
            rest_path = section.rest_path()
            self.assertBanned(
                cli_execute.call_args_list,
                chain(lang_urls(rest_path), lang_urls("decouvrir"), lang_urls("sitemap")),
            )

    @patch("cubicweb_varnish.varnishadm.VarnishCLI.execute")
    @patch("cubicweb_varnish.varnishadm.VarnishCLI.connect")
    def test_commemoration_cache_invalidation(self, _connect, cli_execute):
        with self.admin_access.cnx() as cnx:
            commemo = cnx.create_entity(
                "CommemorationItem",
                title="item1",
                alphatitle="item1",
                commemoration_year=2010,
            )
            section = cnx.create_entity("Section", title="politique", children=commemo)
            cnx.commit()
            cli_execute.reset_mock()
            commemo.cw_set(title="item1bis")
            cnx.commit()
            commemo_rest_path = commemo.rest_path()
            self.assertBanned(
                cli_execute.call_args_list,
                chain(
                    lang_urls(commemo_rest_path),
                    lang_urls(section.rest_path()),
                    lang_urls("sitemap"),
                ),
            )

    @patch("cubicweb_varnish.varnishadm.VarnishCLI.execute")
    @patch("cubicweb_varnish.varnishadm.VarnishCLI.connect")
    def test_findingaid_cache_invalidation(self, _connect, cli_execute):
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
            cnx.commit()
            cli_execute.reset_mock()
            fa.cw_set(description="descr")
            cnx.commit()
            self.assertBanned(
                cli_execute.call_args_list,
                chain(lang_urls("search/"), lang_urls(fa.rest_path()), lang_urls("inventaires/")),
            )
            cli_execute.reset_mock()
            service = cnx.create_entity("Service", category="s1", code="FRAN", reverse_service=fa)
            cnx.commit()
            self.assertBanned(
                cli_execute.call_args_list,
                chain(
                    lang_urls("search/"),
                    lang_urls(fa.rest_path()),
                    lang_urls("inventaires/"),
                    lang_urls("inventaires/FRAN"),
                    lang_urls(service.rest_path()),
                    lang_urls("annuaire"),
                    lang_urls("services"),
                ),
            )

    @patch("cubicweb_varnish.varnishadm.VarnishCLI.execute")
    @patch("cubicweb_varnish.varnishadm.VarnishCLI.connect")
    def test_facomponent_cache_invalidation(self, _connect, cli_execute):
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
            service = cnx.create_entity("Service", category="s1", code="FRAN")
            fa = cnx.create_entity(
                "FindingAid",
                name="the-fa",
                stable_id="FRAD084_xxx",
                eadid="FRAD084_xxx",
                publisher="FRAD084",
                did=fadid,
                service=service,
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
            cnx.commit()
            cli_execute.reset_mock()
            facomp.cw_set(description="descr")
            cnx.commit()
            self.assertBanned(
                cli_execute.call_args_list,
                chain(
                    lang_urls("search/"),
                    lang_urls(facomp.rest_path()),
                    lang_urls("inventaires/"),
                    lang_urls("inventaires/FRAN"),
                ),
            )

    @patch("cubicweb_varnish.varnishadm.VarnishCLI.execute")
    @patch("cubicweb_varnish.varnishadm.VarnishCLI.connect")
    def test_findingaid_cache_invalidation_with_index(self, _connect, cli_execute):
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            fadid = ce("Did", unitid="maindid", unittitle="maindid-title")
            fa = ce(
                "FindingAid",
                name="the-fa",
                stable_id="FRAD084_xxx",
                eadid="FRAD084_xxx",
                publisher="FRAD084",
                did=fadid,
                fa_header=ce("FAHeader"),
            )
            agent1 = ce("AgentAuthority", label="joe")
            loc1 = ce("LocationAuthority", label="Paris")
            ce("AgentName", label="joe", index=fa, authority=agent1)
            ce("Geogname", label="Paris", index=fa, authority=loc1)
            cnx.commit()
            cli_execute.reset_mock()
            fa.cw_set(name="foo")
            cnx.commit()
            self.assertBanned(
                cli_execute.call_args_list,
                chain(
                    lang_urls("search/"),
                    lang_urls(fa.rest_path()),
                    lang_urls("inventaires/"),
                    lang_urls(agent1.rest_path()),
                    lang_urls(loc1.rest_path()),
                ),
            )

    @patch("cubicweb_varnish.varnishadm.VarnishCLI.execute")
    @patch("cubicweb_varnish.varnishadm.VarnishCLI.connect")
    def test_facomponent_cache_invalidation_with_index(self, _connect, cli_execute):
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
                scopecontent="fc-scoppecontent",
                description="fc-descr",
            )
            agent1 = ce("AgentAuthority", label="joe")
            loc1 = ce("LocationAuthority", label="Paris")
            ce("AgentName", label="joe", index=fa, authority=agent1)
            ce("Geogname", label="Paris", index=facomp, authority=loc1)
            cnx.commit()
            cli_execute.reset_mock()
            facomp.cw_set(description="descr")
            cnx.commit()
            self.assertBanned(
                cli_execute.call_args_list,
                chain(
                    lang_urls("search/"),
                    lang_urls(facomp.rest_path()),
                    lang_urls("inventaires/"),
                    # agent1 should not be touched since it's not
                    # linked to the facomp
                    lang_urls(loc1.rest_path()),
                ),
            )

    @patch("cubicweb_varnish.varnishadm.VarnishCLI.execute")
    @patch("cubicweb_varnish.varnishadm.VarnishCLI.connect")
    def test_glossaryterm_cache_invalidation(self, _connect, cli_execute):
        with self.admin_access.repo_cnx() as cnx:
            term = cnx.create_entity(
                "GlossaryTerm",
                term="Dr Who",
                short_description="doctor Who?",
                sort_letter="d",
                description="doctor Who?",
            )
            term.cw_set(anchor=str(term.eid))
            cnx.commit()
            cli_execute.reset_mock()
            term.cw_set(description="Who?")
            cnx.commit()
            rest_path = term.rest_path()
            self.assertBanned(
                cli_execute.call_args_list, chain(lang_urls(rest_path), lang_urls("glossaire"))
            )

    @patch("cubicweb_varnish.varnishadm.VarnishCLI.execute")
    @patch("cubicweb_varnish.varnishadm.VarnishCLI.connect")
    def test_basecontenttranslation_cache_invalidation(self, _connect, cli_execute):
        with self.admin_access.cnx() as cnx:
            basecontent = cnx.create_entity("BaseContent", title="title")
            translation = cnx.create_entity(
                "BaseContentTranslation",
                title="title_en",
                language="en",
                translation_of=basecontent,
            )
            cnx.commit()
            cli_execute.reset_mock()
            translation.cw_set(title="title")
            cnx.commit()
            rest_path = basecontent.rest_path()
            self.assertBanned(
                cli_execute.call_args_list,
                chain(
                    lang_urls(rest_path),
                    lang_urls("article"),
                    lang_urls("articles"),
                    lang_urls("sitemap"),
                ),
            )

    @patch("cubicweb_varnish.varnishadm.VarnishCLI.execute")
    @patch("cubicweb_varnish.varnishadm.VarnishCLI.connect")
    def test_faqitem_cache_invalidation(self, _connect, cli_execute):
        with self.admin_access.repo_cnx() as cnx:
            term = cnx.create_entity(
                "FaqItem",
                question="Dr Who?",
                answer="yes, doctor Who.",
            )
            cnx.commit()
            cli_execute.reset_mock()
            term.cw_set(answer="Who?")
            cnx.commit()
            rest_path = term.rest_path()
            self.assertBanned(
                cli_execute.call_args_list,
                chain(
                    lang_urls(rest_path),
                    lang_urls("faq/"),
                    lang_urls("search/"),
                    lang_urls("circulaires/"),
                    lang_urls("services/"),
                ),
            )

    @patch("cubicweb_varnish.varnishadm.VarnishCLI.execute")
    @patch("cubicweb_varnish.varnishadm.VarnishCLI.connect")
    def test_sitelink_cache_invalidation(self, _connect, cli_execute):
        with self.admin_access.repo_cnx() as cnx:
            link = cnx.create_entity(
                "SiteLink", link="@doc", label_fr="SHERPA", order=0, context="main_menu_links"
            )
            cnx.commit()
            cli_execute.reset_mock()
            link.cw_set(label_fr="@docs")
            cnx.commit()
            rest_path = link.rest_path()
            self.assertBanned(
                cli_execute.call_args_list, chain(lang_urls(rest_path), lang_urls("sitelinks"))
            )

    @patch("cubicweb_varnish.varnishadm.VarnishCLI.execute")
    @patch("cubicweb_varnish.varnishadm.VarnishCLI.connect")
    def test_nominarecord_cache_invalidation(self, _connect, cli_execute):
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                "Service", code="FRAD092", short_name="AD 92", level="level-D", category="foo"
            )
            agent = cnx.create_entity("AgentAuthority", label="Jean Valjean")
            record = cnx.create_entity(
                "NominaRecord",
                stable_id="FRAD008_42",
                json_data={"p": [{"n": "Valjean"}], "t": "RM"},
                service=service.eid,
                same_as=agent,
            )
            cnx.commit()
            rest_path = record.rest_path()
            self.maxDiff = None
            expected = list(
                chain(
                    lang_urls(rest_path),  # record
                    lang_urls("basedenoms/"),
                    lang_urls(agent.rest_path()),  # agent
                    lang_urls(service.rest_path()),  # service
                    lang_urls("annuaire"),  # service
                    lang_urls("services"),  # service
                )
            )
            self.assertBanned(cli_execute.call_args_list, expected)
            cli_execute.reset_mock()
            record.cw_set(json_data={"p": [{"n": "Valjean", "f": "Jean"}], "t": "RM"})
            cnx.commit()
            expected = list(
                chain(
                    lang_urls(rest_path),
                    lang_urls("basedenoms/"),
                )
            )
            self.assertBanned(cli_execute.call_args_list, expected)


if __name__ == "__main__":
    unittest.main()
