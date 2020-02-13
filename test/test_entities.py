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
import os.path as osp

import unittest

from cubicweb import Binary
from cubicweb.devtools import testlib

from cubicweb.devtools import PostgresApptestConfiguration

from cubicweb_francearchives.testutils import HashMixIn

from pgfixtures import setup_module, teardown_module  # noqa


class EntitiesTC(HashMixIn, testlib.CubicWebTC):
    configcls = PostgresApptestConfiguration

    def test_map(self):
        with self.admin_access.cnx() as cnx:
            title = "Etat civil et registres " "paroissiaux numérisés et mis en ligne"
            with open(self.datapath("maps", "Carte_Etat-civil.csv"), "rb") as f:
                data = Binary(f.read())
                cw_map = cnx.create_entity(
                    "Map", title=title, map_file=data, top_content="<h1>Top</h1>"
                )
                cnx.commit()
            data = cw_map.data()
            expected = {
                "url": "http://www.archives-numerisees.ain.fr/archives/recherche/etatcivil/n:88",
                "color": "#044694",
                "code": "01",
                "legend": (
                    "Archives ayant mis en ligne l'\xe9tat civil, "
                    "int\xe9gralement ou partiellement "
                ),
            }

            self.assertCountEqual(data[0], expected)

    def test_html_integrity(self):
        with self.admin_access.cnx() as cnx:
            content = """<div style="background: red"
            javascript="onclick('alert')">style</div>"""
            article = cnx.execute(
                "INSERT BaseContent X : X title %(t)s, " "X content %(c)s ",
                {"t": "title", "c": content},
            ).one()
            cnx.commit()
            self.assertEqual(article.content, """<div style="background: red">style</div>""")
            content = """<div style="color: red"
            javascript="onclick('alert')">style</div>"""
            cnx.execute("SET X content %(c)s WHERE X eid %(e)s", {"e": article.eid, "c": content})
            cnx.commit()
            article = cnx.find("BaseContent", eid=article.eid).one()
            self.assertEqual(article.content, """<div style="color: red">style</div>""")

    def test_html_iframe_kept(self):
        """ensure <iframe> tags are kept"""
        with self.admin_access.cnx() as cnx:
            content = (
                "<h1>Hello</h1>"
                '<iframe width="560" height="315" '
                'src="https://www.youtube.com/embed/T3nEhn4g1iU"'
                ' frameborder="0" allowfullscreen></iframe>'
            )
            article = cnx.execute(
                "INSERT BaseContent X : X title %(t)s, " "X content %(c)s ",
                {"t": "title", "c": content},
            ).one()
            cnx.commit()
            self.assertEqual(article.content, content)

    def test_anom_bounce_url(self):
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
                extptr="ark:/61561/bo755dxx3y5z",
            )
            fa = cnx.create_entity(
                "FindingAid",
                name="the-fa",
                stable_id="FRANOM_xxx",
                eadid="FRANOM_xxx",
                publisher="FRAMP<",
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
                facomp.bounce_url,
                "http://anom.archivesnationales.culture.gouv.fr/ark:/61561/bo755dxx3y5z",
            )

    def test_bounce_url_unitid(self):
        with self.admin_access.cnx() as cnx:
            search_form_url = (
                "http://archives.lille.fr/search?preset=6&query=&quot;"
                "%(unitid)s&quot&search-query=&view=classification&search-query=1"
            )
            serviceid = cnx.create_entity(
                "Service",
                category="s1",
                short_name="Commune de Lille",
                code="FRAM059350",
                search_form_url=search_form_url,
            ).eid
            fadid = cnx.create_entity("Did", unitid="maindid", unittitle="maindid-title")
            fa = cnx.create_entity(
                "FindingAid",
                name="the-fa",
                stable_id="FRANOM_xxx",
                eadid="FRANOM_xxx",
                publisher="FRAMP<",
                did=fadid,
                service=serviceid,
                fa_header=cnx.create_entity("FAHeader"),
            )
            self.assertEqual(fa.bounce_url, search_form_url % {"unitid": fadid.unitid})

    def test_bounce_url_eadid(self):
        with self.admin_access.cnx() as cnx:
            search_form_url = (
                "https://www.archives71.fr/arkotheque/inventaires/"
                "ead_ir_consult.php?ref=%(eadid)s"
            )
            serviceid = cnx.create_entity(
                "Service",
                category="s1",
                short_name="CHALON-SUR-SAÔNE",
                code="FRAD071",
                search_form_url=search_form_url,
            ).eid
            fadid = cnx.create_entity("Did", unitid="maindid", unittitle="maindid-title")
            fa = cnx.create_entity(
                "FindingAid",
                name="the-fa",
                stable_id="FRAD071_2098W",
                eadid="FRAD071 1F 1-168_2F 1-568",
                publisher="FRAD071<",
                did=fadid,
                service=serviceid,
                fa_header=cnx.create_entity("FAHeader"),
            )
            self.assertEqual(fa.bounce_url, search_form_url % {"eadid": fa.eadid.replace(" ", "+")})

    def test_section(self):
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            image = cnx.create_entity(
                "Image",
                caption="image-caption",
                description="alt",
                image_file=ce(
                    "File",
                    data=Binary(b"some-image-data"),
                    data_name="image-name.png",
                    data_format="image/png",
                ),
            )
            section = ce("Section", title="sect-1", name="sect-1", section_image=image)
            cnx.commit()
            self.assertEqual(section.image.eid, image.eid)
            image_url = image.image_file[0].cw_adapt_to("IDownloadable").download_url()
            self.assertEqual(section.illustration_url, image_url)
            self.assertEqual(section.illustration_alt, "alt")

    def test_richstring_attrs(self):
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            section = ce(
                "Section",
                title="sect-1",
                name="sect-1",
                content='<a href="www.toto.fr" title="toto">toto</a>',
            )
            cnx.commit()
            self.assertEqual(section.richstring_attrs, ["content"])
            self.assertEqual(
                section.content,
                '<a href="www.toto.fr" rel="nofollow noopener '
                'noreferrer" target="_blank">toto</a>',
            )
            self.assertEqual(
                section.printable_value("content"),
                '<a href="www.toto.fr" rel="nofollow noopener '
                'noreferrer" target="_blank" title="toto - New window">toto</a>',
            )


class FileTests(testlib.CubicWebTC):
    configcls = PostgresApptestConfiguration

    def _create_similar_files(self, cnx):
        """create two cwFiles with the same filepath"""
        for i in range(2):
            for data, name in ((Binary(b"some-file-data"), "file.pdf"),):
                cnx.create_entity("File", data=data, data_name=name, data_format="application/pdf")
        cnx.commit()

    def test_delete_one_similar_file(self):
        """
        Trying: create two cwFiles with the same filepath and then
                delete one of the file
        Expecting: file is still present on the FS
        """
        with self.admin_access.cnx() as cnx:
            self._create_similar_files(cnx)
            fpaths = [
                f[0].getvalue() for f in cnx.execute("Any fspath(D) WHERE X data D, X is File")
            ]
            self.assertEqual(1, len(set(fpaths)))
            fobj = cnx.execute("Any X LIMIT 1 WHERE X is File").one()
            fobj.cw_delete()
            cnx.commit()
            cnx.find("File").one()
            fpath = cnx.execute("Any fspath(D) WHERE X data D, X is File")[0][0].getvalue()
            self.assertTrue(osp.exists(fpath))

    def test_delete_all_similar_files(self):
        """
        Trying: create tow cwFiles with the same filepath and then
                delete them both
        Expecting: file no longer exists on FS
        """
        with self.admin_access.cnx() as cnx:
            self._create_similar_files(cnx)
            fpaths = [
                f[0].getvalue() for f in cnx.execute("Any fspath(D) WHERE X data D, X is File")
            ]
            self.assertEqual(1, len(set(fpaths)))
            cnx.execute("DELETE File X WHERE X is File")
            cnx.commit()
            self.assertFalse(cnx.find("File"))
            self.assertFalse(osp.exists(fpaths[0]))

    def test_delete_file_with_apostrophe(self):
        """
        Trying: create a cwFile with apostrophe in filepath
        Expecting: file no longer exists on FS
        """
        with self.admin_access.cnx() as cnx:
            cnx.create_entity(
                "File",
                data=Binary(b"data"),
                data_name="FRSHD_INV_GR28P1_COMMISSARIAT_NATIONAL_A_L'INTERIEUR.xml",
                data_format="application/pdf",
            )
            cnx.commit()
            fpaths = [
                f[0].getvalue() for f in cnx.execute("Any fspath(D) WHERE X data D, X is File")
            ]
            self.assertEqual(1, len(set(fpaths)))
            cnx.execute("DELETE File X WHERE X is File")
            cnx.commit()
            self.assertFalse(cnx.find("File"))
            self.assertFalse(osp.exists(fpaths[0]))


class BreadcrumbTests(testlib.CubicWebTC):
    configcls = PostgresApptestConfiguration

    def setup_database(self):
        with self.admin_access.cnx() as cnx:
            self.service = cnx.create_entity(
                "Service", category="s1", short_name="AD de la Marne", code="FRAD051"
            ).eid
            cnx.commit()

    def test_person_breadcrumbs(self):
        with self.admin_access.cnx() as cnx:
            person = cnx.create_entity(
                "Person", name="Durand", forenames="Jean", publisher="FRAD051", service=self.service
            )
            ibc = person.cw_adapt_to("IBreadCrumbs")
            self.assertEqual(
                ibc.breadcrumbs(),
                [
                    ("http://testing.fr/cubicweb/", "Home"),
                    ("http://testing.fr/cubicweb/inventaires/FRAD051", "AD de la Marne"),
                    (None, "Jean Durand"),
                ],
            )

    def test_inventory_breadcrumbs(self):
        with self.admin_access.cnx() as cnx:
            fadid = cnx.create_entity("Did", unitid="maindid", unittitle="maindid-title")
            fa = cnx.create_entity(
                "FindingAid",
                name="the-fa",
                stable_id="FRAD051_xxx",
                eadid="FRAD051_xxx",
                publisher="FRAD051",
                service=self.service,
                did=fadid,
                fa_header=cnx.create_entity("FAHeader"),
            )
            ibc = fa.cw_adapt_to("IBreadCrumbs")
            self.assertEqual(
                ibc.breadcrumbs(),
                [
                    ("http://testing.fr/cubicweb/", "Home"),
                    ("http://testing.fr/cubicweb/inventaires/FRAD051", "AD de la Marne"),
                    (None, "Inventory - maindid"),
                ],
            )

    def test_inventory_breadcrumbs_noservice(self):
        with self.admin_access.cnx() as cnx:
            fadid = cnx.create_entity("Did", unitid="maindid", unittitle="maindid-title")
            fa = cnx.create_entity(
                "FindingAid",
                name="the-fa",
                stable_id="FRAD051_xxx",
                eadid="FRAD051_xxx",
                publisher="FRAD051",
                did=fadid,
                fa_header=cnx.create_entity("FAHeader"),
            )
            ibc = fa.cw_adapt_to("IBreadCrumbs")
            self.assertEqual(
                ibc.breadcrumbs(),
                [("http://testing.fr/cubicweb/", "Home"), (None, "Inventory - maindid")],
            )

    def test_facomponent_breadcrumbs(self):
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
                extptr="ark:/61561/bo755dxx3y5z",
            )
            fa = cnx.create_entity(
                "FindingAid",
                name="the-fa",
                stable_id="FRAD051_xxx",
                eadid="FRAD051_xxx",
                publisher="FRAD051",
                service=self.service,
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
            ibc = facomp.cw_adapt_to("IBreadCrumbs")
            self.assertEqual(
                ibc.breadcrumbs(),
                [
                    ("http://testing.fr/cubicweb/", "Home"),
                    ("http://testing.fr/cubicweb/inventaires/FRAD051", "AD de la Marne"),
                    ("http://testing.fr/cubicweb/findingaid/FRAD051_xxx", "Inventory - maindid"),
                    "fcdid-title",
                ],
            )


class AdapterTests(testlib.CubicWebTC):
    def test_service_vcard(self):
        """
        Trying: adapt a Service to Service2VcardAdapater
        Expecting: the adaption is correct
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                "Service",
                category="Département de la Savoie",
                name="Communauté d'agglomération du Grand Chambéry",
                name2="Service des archives",
                short_name="AD de la Marne",
                phone_number="04.79.68.30.75",
                contact_name="Lise Paulus-Levet",
                address="106 allée des Blachères",
                city="73000 Chambéry",
                opening_period="Sur rendez-vous",
                email="archives@grandchambery.fr",
            )
            cnx.commit()
            card = service.cw_adapt_to("vcard").vcard()
            got = card.serialize()
            for data in (
                "UID:{uuid}".format(uuid=service.uuid),
                "ADR:;;106 allée des Blachères;73000 Chambéry;;;FR",
                "AGENT:Lise Paulus-Levet\r\nEMAIL:archives@grandchambery.fr",
                (
                    "FN:Communauté d'agglomération du Grand Chambéry - "
                    "Service des archives\r\nN:;Communauté d'agglomération "
                    "du Grand Chambéry - Service des archives"
                ),
                "NOTE:Sur rendez-vous\r\nTEL:04.79.68.30.75\r\n",
            ):
                self.assertIn(data, got)

    def test_card_newsletter(self):
        """Test serializing Card which should not be indexed in ElasticSearch (do_index is False).

        Trying: adapting Card to IFullTextIndexSerializable and calling serialize() method
        Expecting: empty dict
        """
        with self.admin_access.cnx() as cnx:
            cnx.create_entity("Card", title="foo", wikiid="bar", do_index=False)
            newsletter = cnx.execute("Any X WHERE X is Card, X do_index False").one()
            adapter = newsletter.cw_adapt_to("IFullTextIndexSerializable")
            self.assertEqual(adapter.serialize(), {})


if __name__ == "__main__":
    unittest.main()
