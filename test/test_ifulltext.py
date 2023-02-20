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
from mock import patch

import os.path as osp
import datetime as dt

import unittest

from cubicweb import Binary
from cubicweb.devtools import testlib

from cubicweb_francearchives.testutils import (
    PostgresTextMixin,
    EsSerializableMixIn,
    S3BfssStorageTestMixin,
)

from pgfixtures import setup_module, teardown_module as pg_teardown_module  # noqa

from esfixtures import teardown_module as es_teardown_module  # noqa

from cubicweb_francearchives.dataimport.ead import dates_for_es_doc
from cubicweb_francearchives.dataimport.oai_nomina import compute_nomina_stable_id


def teardown_module(module):
    pg_teardown_module(module)
    es_teardown_module(module)


class IFullTextIndexSerializableTC(
    S3BfssStorageTestMixin, EsSerializableMixIn, PostgresTextMixin, testlib.CubicWebTC
):
    @patch("elasticsearch.client.indices.IndicesClient.exists")
    @patch("elasticsearch.client.Elasticsearch.index")
    def test_circular_file(self, index, exists):
        with self.admin_access.cnx() as cnx:
            with open(osp.join(self.datadir, "pdf.pdf"), "rb") as pdf:
                ce = cnx.create_entity
                attachment = ce(
                    "File", data_name="pdf", data_format="application/pdf", data=Binary(pdf.read())
                )
                circular = ce(
                    "Circular",
                    circ_id="circ01",
                    title="Circular",
                    status="in-effect",
                    attachment=attachment,
                )
                cnx.commit()
                pdf_text = "Test\nCirculaire chat\n\n\x0c"
                # pdf text is not indexed on File
                rset = cnx.execute(
                    "Any X ORDERBY FTIRANK(X) DESC " "WHERE X has_text %(q)s", {"q": pdf_text}
                )
                self.assertEqual(rset.rows, [])
                rset = cnx.execute(
                    "Any X ORDERBY FTIRANK(X) DESC " "WHERE X has_text %(q)s", {"q": "chat"}
                )
                self.assertEqual(rset.rows, [])
                es_json = circular.cw_adapt_to("IFullTextIndexSerializable").serialize()
                self.assertEqual(pdf_text, es_json["attachment"])

    @patch("elasticsearch.client.indices.IndicesClient.exists")
    @patch("elasticsearch.client.Elasticsearch.index")
    def test_modify_circular_file(self, index, exists):
        """tests RelationsUpdateIndexES is called on File"""
        with self.admin_access.cnx() as cnx:
            with open(osp.join(self.datadir, "pdf.pdf"), "rb") as pdf:
                ce = cnx.create_entity
                circular = ce("Circular", circ_id="circ01", title="Circular", status="in-effect")
                cnx.commit()
                es_json = circular.cw_adapt_to("IFullTextIndexSerializable").serialize()
                self.assertEqual(None, es_json.get("attachment"))
                attachement = ce(
                    "File",
                    data_name="pdf",
                    data_format="application/pdf",
                    data=Binary(pdf.read()),
                    reverse_attachment=circular,
                )
                cnx.commit()
                pdf_text = "Test\nCirculaire chat\n\n\x0c"
                circular = cnx.find("Circular", eid=circular.eid).one()
                es_json = circular.cw_adapt_to("IFullTextIndexSerializable").serialize()
                self.assertEqual(pdf_text, es_json["attachment"])
                es_json_file = attachement.cw_adapt_to("IFullTextIndexSerializable").serialize()
                self.assertEqual(pdf_text, es_json_file["attachment"])

    @patch("elasticsearch.client.indices.IndicesClient.exists")
    @patch("elasticsearch.client.Elasticsearch.index")
    def test_circular_attachment_indexed_as_circular(self, index, exists):
        """check circular attachments are indexed as circulars"""
        with self.admin_access.cnx() as cnx:
            with open(osp.join(self.datadir, "pdf.pdf"), "rb") as pdf:
                ce = cnx.create_entity
                attachment = ce(
                    "File", data_name="pdf", data_format="application/pdf", data=Binary(pdf.read())
                )
                circular = ce(
                    "Circular",
                    circ_id="circ01",
                    title="Circular",
                    status="in-effect",
                    attachment=attachment,
                )
                cnx.commit()
                circ_ift = circular.cw_adapt_to("IFullTextIndexSerializable")
                f_ift = attachment.cw_adapt_to("IFullTextIndexSerializable")
                self.assertEqual(f_ift.es_id, circular.eid)
                self.assertEqual(f_ift.es_doc_type, "_doc")
                self.assertEqual(f_ift.serialize(), circ_ift.serialize())

    @patch("elasticsearch.client.indices.IndicesClient.exists")
    @patch("elasticsearch.client.Elasticsearch.index")
    def test_circular_additional_attachment_indexed_as_circular(self, index, exists):
        """check circular additional attachments are indexed as circulars"""
        with self.admin_access.cnx() as cnx:
            with open(osp.join(self.datadir, "pdf.pdf"), "rb") as pdf:
                ce = cnx.create_entity
                attachment = ce(
                    "File", data_name="pdf", data_format="application/pdf", data=Binary(pdf.read())
                )
                circular = ce(
                    "Circular",
                    circ_id="circ01",
                    title="Circular",
                    status="in-effect",
                    additional_attachment=attachment,
                )
                cnx.commit()
                circ_ift = circular.cw_adapt_to("IFullTextIndexSerializable")
                f_ift = attachment.cw_adapt_to("IFullTextIndexSerializable")
                self.assertEqual(f_ift.es_id, circular.eid)
                self.assertEqual(f_ift.es_doc_type, "_doc")
                self.assertEqual(f_ift.serialize(), circ_ift.serialize())

    @patch("elasticsearch.client.indices.IndicesClient.exists")
    @patch("elasticsearch.client.Elasticsearch.index")
    def test_is_in_publication_section(self, index, exists):
        """es_json['cw_etype'] of BaseContent which is a publication
        (in `publication` section) must be BaseContent for now
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity("Service", category="cat", name="Service", short_name="s1")
            basecontent = cnx.create_entity(
                "BaseContent",
                title="program",
                content="31 juin",
                basecontent_service=service,
                reverse_children=cnx.create_entity(
                    "Section", title="Publication", name="publication"
                ),
            )
            cnx.commit()
            es_json = basecontent.cw_adapt_to("IFullTextIndexSerializable").serialize()
            self.assertEqual("Article", es_json["cw_etype"])

    @patch("elasticsearch.client.indices.IndicesClient.exists")
    @patch("elasticsearch.client.Elasticsearch.index")
    def test_basecontent_cw_etype(self, index, exists):
        """Trying: create BaseContent and modify its content_type
        Expecting; es_json['cw_etype'] of BaseContent which be the same as content_type if specified
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity("Service", category="cat", name="Service", short_name="s1")
            basecontent = cnx.create_entity(
                "BaseContent",
                title="program",
                content="31 juin",
                basecontent_service=service,
                content_type="SearchHelp",
                reverse_children=cnx.create_entity("Section", title="Publication", name="toto"),
            )
            cnx.commit()
            es_json = basecontent.cw_adapt_to("IFullTextIndexSerializable").serialize()
            self.assertEqual("SearchHelp", basecontent.content_type)
            self.assertEqual("SearchHelp", es_json["cw_etype"])
            basecontent.cw_set(content_type="Publication")
            cnx.commit()
            es_json = basecontent.cw_adapt_to("IFullTextIndexSerializable").serialize()
            self.assertEqual("Publication", basecontent.content_type)
            self.assertEqual("Publication", es_json["cw_etype"])
            basecontent.cw_set(content_type="Article")
            cnx.commit()
            es_json = basecontent.cw_adapt_to("IFullTextIndexSerializable").serialize()
            self.assertEqual("Article", basecontent.content_type)
            self.assertEqual("Article", es_json["cw_etype"])

    @patch("elasticsearch.client.indices.IndicesClient.exists")
    @patch("elasticsearch.client.Elasticsearch.index")
    def test_basecontent(self, index, exists):
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity("Service", category="cat", name="Service", short_name="s1")
            basecontent = cnx.create_entity(
                "BaseContent", title="program", content="31 juin", basecontent_service=service
            )
            cnx.commit()
            es_json = basecontent.cw_adapt_to("IFullTextIndexSerializable").serialize()
            self.assertEqual("siteres", es_json["escategory"])
            self.assertEqual("31 juin", es_json["content"])
            self.assertEqual("program", es_json["title"])
            self.assertEqual(es_json["publisher"], ["s1"])
            self.assertEqual(
                es_json["service"],
                [
                    {
                        "code": service.code,
                        "eid": service.eid,
                        "level": service.level,
                        "title": service.dc_title(),
                    }
                ],
            )

    @patch("elasticsearch.client.indices.IndicesClient.exists")
    @patch("elasticsearch.client.Elasticsearch.index")
    def test_basecontent_services(self, index, exists):
        with self.admin_access.cnx() as cnx:
            s1 = cnx.create_entity(
                "Service", category="cat", short_name="s1_short", name2="s1_name2", name="s1_name"
            )
            s2 = cnx.create_entity("Service", category="cat", name2="n2_name2", name="s2_name")
            s3 = cnx.create_entity("Service", category="cat", name="s3_name")
            basecontent = cnx.create_entity(
                "BaseContent", title="program", content="31 juin", basecontent_service=[s1, s2, s3]
            )
            cnx.commit()
            es_json = basecontent.cw_adapt_to("IFullTextIndexSerializable").serialize()
            self.assertEqual(es_json["publisher"], ["s1_short", "n2_name2", "s3_name"])

    @patch("elasticsearch.client.indices.IndicesClient.exists")
    @patch("elasticsearch.client.Elasticsearch.index")
    def test_translated_basecontent(self, index, exists):
        with self.admin_access.cnx() as cnx:
            basecontent = cnx.create_entity(
                "BaseContent", title="programme", content="<h1>31 juin</h1>"
            )
            cnx.commit()
            translation = cnx.create_entity(
                "BaseContentTranslation",
                language="en",
                title="program",
                content="<h1>31 june</h1>",
                translation_of=basecontent,
            )
            basecontent = cnx.find("BaseContent", eid=basecontent.eid).one()
            translation = cnx.find("BaseContentTranslation", eid=translation.eid).one()
            es_json = basecontent.cw_adapt_to("IFullTextIndexSerializable").serialize()
            tes_json = translation.cw_adapt_to("IFullTextIndexSerializable").serialize()
            for attr, value in (
                ("cw_etype", "Article"),
                ("eid", basecontent.eid),
                ("content", "31 juin"),
                ("content_en", "31 june"),
                ("title", "programme"),
                ("title_en", "program"),
            ):
                self.assertEqual(tes_json[attr], value)
                self.assertEqual(es_json[attr], value)

    @patch("elasticsearch.client.indices.IndicesClient.exists")
    @patch("elasticsearch.client.Elasticsearch.index")
    def test_delete_translated_basecontent(self, index, exists):
        with self.admin_access.cnx() as cnx:
            basecontent = cnx.create_entity(
                "BaseContent", title="programme", content="<h1>31 juin</h1>"
            )
            cnx.commit()
            translation = cnx.create_entity(
                "BaseContentTranslation",
                language="en",
                title="program",
                content="<h1>31 june</h1>",
                translation_of=basecontent,
            )
            cnx.commit()
            translation.cw_delete()
            basecontent = cnx.find("BaseContent", eid=basecontent.eid).one()
            es_json = basecontent.cw_adapt_to("IFullTextIndexSerializable").serialize()
            for attr, value in (
                ("cw_etype", "Article"),
                ("eid", basecontent.eid),
                ("content", "31 juin"),
                ("title", "programme"),
            ):
                self.assertEqual(es_json[attr], value)
            for attr in ("content_en", "title_en"):
                self.assertNotIn(attr, es_json)

    @patch("elasticsearch.client.indices.IndicesClient.exists")
    @patch("elasticsearch.client.Elasticsearch.index")
    def test_virtualexhibit(self, index, exists):
        with self.admin_access.cnx() as cnx:
            s1 = cnx.create_entity(
                "Service", category="cat", level="level-D", name="Service", short_name="s1"
            )
            s2 = cnx.create_entity(
                "Service", category="cat", code="CRRP", name="Service", short_name="s2"
            )
            extref = cnx.create_entity(
                "ExternRef",
                reftype="Virtual_exhibit",
                title="externref-title",
                url="http://toto",
                start_year=1982,
                exref_service=[s1, s2],
            )
            es_json = extref.cw_adapt_to("IFullTextIndexSerializable").serialize()
            self.assertEqual(es_json["reftype"], "virtual_exhibit")
            self.assertEqual(es_json["cw_etype"], "Virtual_exhibit")
            self.assertEqual(es_json["start_year"], 1982)
            self.assertEqual(es_json["escategory"], "siteres")
            self.assertEqual(es_json["publisher"], ["s1", "s2"])
            self.assertEqual(es_json["dates"], {"gte": 1982, "lte": 1982})
            self.assertEqual(es_json["sortdate"], "1982-01-01")
            self.assertEqual(
                es_json["service"],
                [
                    {
                        "code": s1.code,
                        "eid": s1.eid,
                        "level": s1.level,
                        "title": s1.dc_title(),
                    },
                    {
                        "code": s2.code,
                        "eid": s2.eid,
                        "level": s2.level,
                        "title": s2.dc_title(),
                    },
                ],
            )

    @patch("elasticsearch.client.indices.IndicesClient.exists")
    @patch("elasticsearch.client.Elasticsearch.index")
    def test_virtualexhibit_neg_date(self, index, exists):
        with self.admin_access.cnx() as cnx:
            s1 = cnx.create_entity("Service", category="cat", name="Service", short_name="s1")
            s2 = cnx.create_entity("Service", category="cat", name="Service", short_name="s2")
            extref = cnx.create_entity(
                "ExternRef",
                reftype="Virtual_exhibit",
                title="externref-title",
                url="http://toto",
                start_year=-12,
                stop_year=12,
                exref_service=[s1, s2],
            )
            es_json = extref.cw_adapt_to("IFullTextIndexSerializable").serialize()
            self.assertEqual(es_json["reftype"], "virtual_exhibit")
            self.assertEqual(es_json["cw_etype"], "Virtual_exhibit")
            self.assertEqual(es_json["start_year"], -12)
            self.assertEqual(es_json["escategory"], "siteres")
            self.assertEqual(es_json["publisher"], ["s1", "s2"])
            self.assertEqual(es_json["dates"], {"gte": -12, "lte": 12})
            self.assertEqual(es_json["sortdate"], "0000-01-01")

    def test_newscontent_dates(self):
        """
        Trying: create a NewsContent with a start_date
        Expecting: the dates field contains the start_date year / stop_date year
                    as single interval value
        """
        with self.admin_access.cnx() as cnx:
            newscontent = cnx.create_entity(
                "NewsContent",
                title="the-news",
                content="the-content",
                start_date=dt.date(2011, 1, 1),
            )
            es_json = newscontent.cw_adapt_to("IFullTextIndexSerializable").serialize()
            self.assertEqual(es_json["dates"], {"gte": 2011, "lte": 2011})
            self.assertEqual(es_json["sortdate"], "2011-01-01")

    def test_commemorationitem_dates(self):
        """
        Trying: create a CommemorationItem with a "year"
        Expecting: the dates field contains the year value as single interval value
        """
        with self.admin_access.cnx() as cnx:
            commemo = cnx.create_entity(
                "CommemorationItem",
                title="commemoration",
                alphatitle="commemoration",
                subtitle="sous-titre",
                content="contenu",
                commemoration_year=2000,
                start_year=1952,
            )
            es_json = commemo.cw_adapt_to("IFullTextIndexSerializable").serialize()
            self.assertEqual(es_json["dates"], {"gte": 1952, "lte": 1952})

    def test_commemorationitem_sortdate(self):
        """
        Trying: create a CommemorationItem with a "year" 52
        Expecting: sortdate is correctly formated
        """
        with self.admin_access.cnx() as cnx:
            commemo = cnx.create_entity(
                "CommemorationItem",
                title="commemoration",
                alphatitle="commemoration",
                subtitle="sous-titre",
                content="contenu",
                start_year=52,
            )
            es_json = commemo.cw_adapt_to("IFullTextIndexSerializable").serialize()
            self.assertEqual(es_json["sortdate"], "0052-01-01")

    def test_circular_dates(self):
        """
        Trying: create a Circular with a siaf_daf_signing_date
        Expecting: the dates field contains the siaf_daf_signing_date year as single interval value
        """
        with self.admin_access.cnx() as cnx:
            circular = cnx.create_entity(
                "Circular", circ_id="circ01", title="Circular", status="in-effect"
            )
            es_json = circular.cw_adapt_to("IFullTextIndexSerializable").serialize()
            self.assertNotIn("dates", es_json)
            circular.cw_set(siaf_daf_signing_date=dt.date(2015, 3, 1))
            es_json = circular.cw_adapt_to("IFullTextIndexSerializable").serialize()
            self.assertEqual(es_json["dates"], {"gte": 2015, "lte": 2015})
            self.assertEqual(es_json["sortdate"], "2015-03-01")

    def test_basecontent_dates(self):
        """
        Trying: create a BaseContent with a previous modification_date, modify the Base Content
        Expecting: the dates field must contain the initial modification_date year, then current
            year after modification
        """
        with self.admin_access.cnx() as cnx:
            basecontent = cnx.create_entity(
                "BaseContent",
                title="TOTO Titre",
                content="Bonjour <em>Bourvil</em>",
                creation_date=dt.date(2007, 1, 21),
                modification_date=dt.date(2008, 2, 2),
            )
            es_json = basecontent.cw_adapt_to("IFullTextIndexSerializable").serialize()
            self.assertEqual(es_json["dates"], {"gte": 2008, "lte": 2008})
            self.assertEqual(es_json["sortdate"], "2008-02-02")
            basecontent.cw_set(title="POUET Titre")
            es_json = basecontent.cw_adapt_to("IFullTextIndexSerializable").serialize()
            now = dt.datetime.now()
            current_year = now.year
            self.assertEqual(es_json["dates"], {"gte": current_year, "lte": current_year})
            self.assertEqual(es_json["sortdate"], now.strftime("%Y-%m-%d"))

    def test_card_service_map_dates(self):
        """
        Trying: create a Card, a Service, a Map
        Expecting: the dates field must contain the current year
        """
        with self.admin_access.cnx() as cnx:
            current_year = dt.datetime.now().year
            card = cnx.create_entity(
                "Card", wikiid="card-de", title="the-card", content="some-content"
            )
            es_json = card.cw_adapt_to("IFullTextIndexSerializable").serialize()
            self.assertEqual(es_json["dates"], {"gte": current_year, "lte": current_year})

            service = cnx.create_entity("Service", category="cat", name="Service", short_name="s1")
            es_json = service.cw_adapt_to("IFullTextIndexSerializable").serialize()
            self.assertEqual(es_json["dates"], {"gte": current_year, "lte": current_year})

            map = cnx.create_entity("Map", title="map1", map_file=Binary(b""))
            es_json = map.cw_adapt_to("IFullTextIndexSerializable").serialize()
            self.assertEqual(es_json["dates"], {"gte": current_year, "lte": current_year})

    @patch("elasticsearch.client.indices.IndicesClient.exists")
    @patch("elasticsearch.client.Elasticsearch.index")
    def test_html_content_section(self, index, exists):
        with self.admin_access.cnx() as cnx:
            section = cnx.create_entity(
                "Section", title="section", content="<p><strong>content</strong></p>"
            )
            cnx.commit()
            es_json = section.cw_adapt_to("IFullTextIndexSerializable").serialize()
            self.assertEqual("content", es_json["content"])

    @patch("elasticsearch.client.indices.IndicesClient.exists")
    @patch("elasticsearch.client.Elasticsearch.index")
    def test_translated_section(self, index, exists):
        """
        Trying: create a Section and its spanish Translation
        Expecting: Translation's IFullTextIndexSerializable adapter returns the Section
        """
        with self.admin_access.cnx() as cnx:
            section = cnx.create_entity(
                "Section",
                title="rubirque",
                subtitle="test",
                short_description="court",
                content="<p>content</p>",
            )
            cnx.commit()
            translation = cnx.create_entity(
                "SectionTranslation",
                language="es",
                title="tema",
                subtitle="prueba",
                content="<p>contenido</p>",
                short_description="corto",
                translation_of=section,
            )
            cnx.commit()
            section = cnx.find("Section", eid=section.eid).one()
            translation = cnx.find("SectionTranslation", eid=translation.eid).one()
            tes_json = translation.cw_adapt_to("IFullTextIndexSerializable").serialize()
            ses_json = section.cw_adapt_to("IFullTextIndexSerializable").serialize()
            for attr, value in (
                ("cw_etype", "Section"),
                ("eid", section.eid),
                ("content", "content"),
                ("content_es", "contenido"),
                ("title", "rubirque"),
                ("title_es", "tema"),
                ("subtitle_es", "prueba"),
                ("short_description_es", "corto"),
            ):
                self.assertEqual(tes_json[attr], value)
                self.assertEqual(ses_json[attr], value)
            for attr in ("subtitle", "short_description"):
                self.assertNotIn(attr, tes_json)
                self.assertNotIn(attr, ses_json)

    @patch("elasticsearch.client.indices.IndicesClient.exists")
    @patch("elasticsearch.client.Elasticsearch.index")
    def test_map_esdoc(self, index, exists):
        with self.admin_access.cnx() as cnx:
            s1 = cnx.create_entity("Section", title="s1", name="s1")
            s1_1 = cnx.create_entity("Section", title="s1_1", name="s1_1", reverse_children=s1)
            map1 = cnx.create_entity(
                "Map", title="map1", map_file=Binary(b""), reverse_children=s1_1
            )
            esdoc = map1.cw_adapt_to("IFullTextIndexSerializable").serialize()
            self.assertDictContainsSubset(
                {
                    "title": "map1",
                    "cw_etype": "Map",
                    "escategory": "siteres",
                    "ancestors": [s1.eid, s1_1.eid],
                },
                esdoc,
            )
            self.assertNotIn("map_file", esdoc, "map file content should not be indexed by ES")

    @patch("elasticsearch.client.indices.IndicesClient.exists")
    @patch("elasticsearch.client.Elasticsearch.index")
    def test_commemo_esdoc(self, index, exists):
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            commemo_item = ce(
                "CommemorationItem",
                title="Commemoration",
                alphatitle="commemoration",
                subtitle="commemo-subtitle",
                content="content",
                commemoration_year=1500,
            )
            esdoc = commemo_item.cw_adapt_to("IFullTextIndexSerializable").serialize()
            self.assertDictContainsSubset(
                {
                    "title": "Commemoration",
                    "cw_etype": "CommemorationItem",
                    "escategory": "siteres",
                    "subtitle": "commemo-subtitle",
                },
                esdoc,
            )

    @patch("elasticsearch.client.indices.IndicesClient.exists")
    @patch("elasticsearch.client.Elasticsearch.index")
    def test_translated_commemo(self, index, exists):
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            commemo = ce(
                "CommemorationItem",
                title="commemoration",
                alphatitle="commemoration",
                subtitle="sous-titre",
                content="contenu",
                commemoration_year=1500,
            )
            cnx.commit()
            translation = cnx.create_entity(
                "CommemorationItemTranslation",
                language="de",
                title="Gedenkschrift",
                subtitle="Untertitel",
                content="<h1>Inhalt</h1>",
                translation_of=commemo,
            )
            cnx.commit()
            commemo = cnx.find("CommemorationItem", eid=commemo.eid).one()
            translation = cnx.find("CommemorationItemTranslation", eid=translation.eid).one()
            es_json = commemo.cw_adapt_to("IFullTextIndexSerializable").serialize()
            tes_json = translation.cw_adapt_to("IFullTextIndexSerializable").serialize()
            for attr, value in (
                ("cw_etype", "CommemorationItem"),
                ("eid", commemo.eid),
                ("title", "commemoration"),
                ("title_de", "Gedenkschrift"),
                ("subtitle", "sous-titre"),
                ("subtitle_de", "Untertitel"),
                ("content", "contenu"),
                ("content_de", "Inhalt"),
            ):
                self.assertEqual(es_json[attr], value)
                self.assertEqual(tes_json[attr], value)

    @patch("elasticsearch.client.indices.IndicesClient.exists")
    @patch("elasticsearch.client.Elasticsearch.index")
    def test_authorityrecord(self, index, exists):
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                "Service", category="other", name="Service", code="CODE", short_name="ADP"
            )
            name = "Jean Cocotte"
            subject = cnx.create_entity(
                "AgentAuthority",
                label=name,
                reverse_authority=cnx.create_entity(
                    "AgentName",
                    role="person",
                    label="name",
                ),
            )
            kind_eid = cnx.find("AgentKind", name="person")[0][0]
            record = cnx.create_entity(
                "AuthorityRecord",
                record_id="FRAN_NP_006883",
                agent_kind=kind_eid,
                maintainer=service.eid,
                reverse_name_entry_for=(
                    cnx.create_entity("NameEntry", parts=name, form_variant="authorized"),
                    cnx.create_entity("NameEntry", parts="Janot CotCot"),
                ),
                xml_support="foo",
                start_date=dt.datetime(1940, 1, 1),
                end_date=dt.datetime(2000, 5, 1),
                reverse_occupation_agent=cnx.create_entity("Occupation", term="éleveur de poules"),
                reverse_history_agent=cnx.create_entity(
                    "History", text="<p>Il aimait les poules</p>"
                ),
                same_as=subject,
            )
            es_json = record.cw_adapt_to("IFullTextIndexSerializable").serialize()
            expected = {
                "alltext": "FRAN_NP_006883 Janot CotCot  éleveur de poules Il aimait les " "poules",
                "creation_date": record.creation_date,
                "cw_etype": "AuthorityRecord",
                "cwuri": f"http://testing.fr/cubicweb/{record.eid}",
                "dates": {"gte": 1940, "lte": 2000},
                "eid": record.eid,
                "estype": "AuthorityRecord",
                "modification_date": record.modification_date,
                "publisher": "ADP",
                "sortdate": "1940-01-01",
                "title": "Jean Cocotte",
            }
            self.assertDictEqual(expected, es_json)

    def test_dates_fa_es_doc(self):
        didattrs = {}
        self.assertTrue("dates" not in dates_for_es_doc(didattrs))
        didattrs = {"startyear": 1500}
        self.assertEqual(dates_for_es_doc(didattrs)["dates"], {"gte": 1500, "lte": 1500})
        self.assertEqual(dates_for_es_doc(didattrs)["sortdate"], "1500-01-01")
        didattrs = {"stopyear": 1600}
        self.assertEqual(dates_for_es_doc(didattrs)["dates"], {"gte": 1600, "lte": 1600})
        self.assertEqual(dates_for_es_doc(didattrs)["sortdate"], "1600-01-01")
        didattrs = {"startyear": 1500, "stopyear": 1600}
        self.assertEqual(dates_for_es_doc(didattrs)["dates"], {"gte": 1500, "lte": 1600})
        self.assertEqual(dates_for_es_doc(didattrs)["sortdate"], "1500-01-01")


class ISuggestIndexSerializableTC(
    S3BfssStorageTestMixin, EsSerializableMixIn, PostgresTextMixin, testlib.CubicWebTC
):
    def create_findingaid(self, cnx, eadid):
        return cnx.create_entity(
            "FindingAid",
            name=eadid,
            stable_id="stable_id{}".format(eadid),
            eadid=eadid,
            publisher="publisher",
            did=cnx.create_entity(
                "Did", unitid="unitid{}".format(eadid), unittitle="title{}".format(eadid)
            ),
            fa_header=cnx.create_entity("FAHeader"),
        )

    @patch("elasticsearch.client.indices.IndicesClient.exists")
    @patch("elasticsearch.client.Elasticsearch.index")
    def test_location_authority(self, index, exists):
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            loc1 = ce("LocationAuthority", label="location 1")
            fa1 = self.create_findingaid(cnx, "eadid1")
            ce("Geogname", label="index location 1", index=fa1, authority=loc1)
            # add a second index with the same FindingAid
            ce("Geogname", label="index location 2", index=fa1, authority=loc1)
            fa2 = self.create_findingaid(cnx, "eadid2")
            ce("Geogname", label="index location 3", index=fa2, authority=loc1)
            cnx.commit()
            esdoc = loc1.cw_adapt_to("ISuggestIndexSerializable").serialize()
            expected = {
                "count": 2,
                "archives": 2,
                "siteres": 0,
                "cw_etype": "LocationAuthority",
                "grouped": False,
                "letter": "l",
                "text": "location 1",
                "label": "location 1",
                "urlpath": "location/{}".format(loc1.eid),
                "eid": loc1.eid,
                "type": "geogname",
                "quality": False,
            }
            self.assertDictEqual(expected, esdoc)

    @patch("elasticsearch.client.indices.IndicesClient.exists")
    @patch("elasticsearch.client.Elasticsearch.index")
    def test_subject_authority(self, index, exists):
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            auth = ce("SubjectAuthority", label="Étienne Marcel", quality=True)
            cnx.commit()
            esdoc = auth.cw_adapt_to("ISuggestIndexSerializable").serialize()
            expected = {
                "count": 0,
                "archives": 0,
                "siteres": 0,
                "cw_etype": "SubjectAuthority",
                "grouped": False,
                "letter": "e",
                "text": "Étienne Marcel",
                "label": "Étienne Marcel",
                "urlpath": f"subject/{auth.eid}",
                "eid": auth.eid,
                "type": "subject",
                "quality": True,
            }
            self.assertDictEqual(expected, esdoc)

    @patch("elasticsearch.client.indices.IndicesClient.exists")
    @patch("elasticsearch.client.Elasticsearch.index")
    def test_authority_non_latin_letter(self, index, exists):
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            for label in ("Ленин", "猫"):
                auth = ce("AgentAuthority", label=label, quality=1)
                cnx.commit()
                esdoc = auth.cw_adapt_to("ISuggestIndexSerializable").serialize()
                self.assertEqual(esdoc["letter"], "#")

    @patch("elasticsearch.client.indices.IndicesClient.exists")
    @patch("elasticsearch.client.Elasticsearch.index")
    def test_authority_non_letter(self, index, exists):
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            for label, expected in ((None, ""), ("123 rue des petits chats", "0"), ("# test", "!")):
                auth = ce("AgentAuthority", label=label, quality=1)
                cnx.commit()
                esdoc = auth.cw_adapt_to("ISuggestIndexSerializable").serialize()
                self.assertEqual(esdoc["letter"], expected)

    @patch("elasticsearch.client.indices.IndicesClient.exists")
    @patch("elasticsearch.client.Elasticsearch.index")
    def test_grouped_agent_with_fa_commemo_and_extref(self, index, exists):
        """
        Trying: group an AgentAuthority having linked IRs and commemo
        Expecting: grouped agent have 0 related entities:
                   IRs, CommemorationItem or ExternRef
        """
        with self.admin_access.cnx() as cnx:
            fa = self.create_findingaid(cnx, "chirac ministre")
            label = "Chirac, Jacques (homme politique, président de la République)"
            index = cnx.create_entity("AgentName", label=label, index=fa)
            agent = cnx.create_entity("AgentAuthority", label=label, reverse_authority=index)
            cnx.commit()
            fa = self.create_findingaid(cnx, "Jacques Chirac")
            index = cnx.create_entity("AgentName", label="Chirac, Jacques", index=fa)
            commemo_item = cnx.create_entity(
                "CommemorationItem",
                title="Commemoration",
                alphatitle="commemoration",
                content="content",
                commemoration_year=2019,
            )
            extref = cnx.create_entity(
                "ExternRef", reftype="Virtual_exhibit", title="externref-title"
            )
            grouped_agent = cnx.create_entity(
                "AgentAuthority",
                label="Chirac, Jacques",
                quality=False,
                reverse_authority=index,
                reverse_related_authority=[commemo_item, extref],
            )
            cnx.commit()
            esdoc = grouped_agent.cw_adapt_to("ISuggestIndexSerializable").serialize()
            expected = {
                "count": 3,
                "cw_etype": "AgentAuthority",
                "grouped": False,
                "text": "Chirac, Jacques",
                "type": "agent",
                "quality": False,
                "siteres": 2,
                "archives": 1,
            }
            self.assertDictContainsSubset(expected, esdoc)
            agent.group([grouped_agent.eid])
            cnx.commit()
            grouped_agent = cnx.find("AgentAuthority", eid=grouped_agent.eid).one()
            esdoc = grouped_agent.cw_adapt_to("ISuggestIndexSerializable").serialize()
            expected = {
                "count": 0,
                "cw_etype": "AgentAuthority",
                "grouped": True,
                "text": "Chirac, Jacques",
                "type": "agent",
                "quality": False,
                "siteres": 0,
                "archives": 0,
            }
            self.assertDictContainsSubset(expected, esdoc)

    @patch("elasticsearch.client.indices.IndicesClient.exists")
    @patch("elasticsearch.client.Elasticsearch.index")
    def test_card_cw_etype(self, index, exists):
        """Trying: create a Card
        Expecting; es_json['cw_etype'] of a Card must be "Article"
        """
        with self.admin_access.cnx() as cnx:
            card = cnx.find("Card", wikiid="emplois-fr").one()
            es_json = card.cw_adapt_to("IFullTextIndexSerializable").serialize()
            self.assertEqual("Article", es_json["cw_etype"])
            self.assertEqual("Card", es_json["estype"])

    @patch("elasticsearch.client.indices.IndicesClient.exists")
    @patch("elasticsearch.client.Elasticsearch.index")
    def test_nomina_record_rm(self, index, exists):
        """es_json['cw_etype'] of NominaRecords of RM type"""
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                "Service", category="cat", name="Landes", short_name="Landes", code="FRAD040"
            )
            stable_id = compute_nomina_stable_id(service.code, "23")
            nomina = cnx.create_entity(
                "NominaRecord",
                stable_id=stable_id,
                json_data={
                    "c": {"c": "R P 392", "e": "0", "n": "22", "o": ["laboureur"]},
                    "e": {
                        "N": [
                            {
                                "d": {"y": "1867"},
                                "l": {
                                    "c": "France",
                                    "cc": "FR",
                                    "d": "Landes",
                                    "dc": "40",
                                    "p": "Arue",
                                },
                            }
                        ],
                        "R": [
                            {
                                "l": {
                                    "c": "France",
                                    "cc": "FR",
                                    "d": "Landes",
                                    "dc": "40",
                                    "p": "Cère",
                                }
                            }
                        ],
                        "RM": [
                            {
                                "d": {"y": "1887-1889"},
                                "l": {
                                    "c": "France",
                                    "cc": "FR",
                                    "d": "Landes",
                                    "dc": "40",
                                    "p": "Mont-de-Marsan",
                                },
                            }
                        ],
                    },
                    "p": [{"f": "Barthélémy", "n": "Duprat"}],
                    "t": "RM",
                    "u": "http://www.archives.landes.fr/ark:/35227/s0052cbf404e1290/52cc0a4a27570",
                },
                service=service,
            )
            cnx.commit()
            es_json = nomina.cw_adapt_to("INominaIndexSerializable").serialize()
            expected = {
                "acte_type": "RM",
                "alltext": "R P 392 NMN_E_0 22 laboureur NMN_BN 1867 NMN_R NMN_RM 1887-1889",
                "authority": [],
                "creation_date": nomina.creation_date,
                "cw_etype": "NominaRecord",
                "cwuri": f"http://testing.fr/cubicweb/basedenoms/{nomina.stable_id}",
                "dates": {"gte": "1887", "lte": "1889"},
                "eid": nomina.eid,
                "forenames": ["Barthélémy"],
                "locations": ["Arue", "Cère", "France", "Landes", "Mont-de-Marsan"],
                "modification_date": nomina.modification_date,
                "names": ["Duprat"],
                "service": service.eid,
                "stable_id": stable_id,
            }
            self.assertEqual(expected, es_json)

    @patch("elasticsearch.client.indices.IndicesClient.exists")
    @patch("elasticsearch.client.Elasticsearch.index")
    def test_nomina_record_mort_14_18(self, index, exists):
        """es_json['cw_etype'] of NominaRecords of Mort 14_18 type"""
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                "Service", category="cat", name="Ardennes", short_name="Ardennes", code="FRAD008"
            )
            stable_id = compute_nomina_stable_id(service.code, "888")
            nomina = cnx.create_entity(
                "NominaRecord",
                stable_id=stable_id,
                oai_id="888",
                json_data={
                    "c": {"c": "1R 155", "n": "110", "o": ["ferronnier"]},
                    "e": {
                        "N": {"d": [{"y": "1880"}], "l": [{"d": "Ardennes", "p": "Renwez"}]},
                        "R": {
                            "l": [
                                {"d": "Ardennes", "p": "Château-Regnault-Bogny (Bogny-sur-Meuse)"}
                            ]
                        },
                        "RM": {
                            "d": [{"y": "1900"}],
                            "l": [{"c": "France", "cc": "FR", "d": "Ardennes", "p": "Mézières"}],
                        },
                    },
                    "p": [
                        {"f": "Léon Gustave", "n": "Suquez"},
                        {"f": "Jean Gustave", "n": "Suquez"},
                    ],
                    "t": "Môrt 14-18",
                    "u": "https://archives.cd08.fr/ark:/75583/s0053eb9b6047b1f/53eb9b604f5b9",
                },
                service=service,
            )
            cnx.commit()
            es_json = nomina.cw_adapt_to("INominaIndexSerializable").serialize()
            expected = {
                "acte_type": "MORT 14-18",
                "alltext": "1R 155 110 ferronnier NMN_BN 1880 NMN_R NMN_RM 1900",
                "authority": [],
                "creation_date": nomina.creation_date,
                "cw_etype": "NominaRecord",
                "cwuri": f"http://testing.fr/cubicweb/basedenoms/{nomina.stable_id}",
                "dates": None,
                "eid": nomina.eid,
                "forenames": ["Léon Gustave", "Jean Gustave"],
                "names": ["Suquez", "Suquez"],
                "locations": [
                    "Ardennes",
                    "Château-Regnault-Bogny (Bogny-sur-Meuse)",
                    "France",
                    "Mézières",
                    "Renwez",
                ],
                "modification_date": nomina.modification_date,
                "service": service.eid,
                "stable_id": stable_id,
            }
            self.assertEqual(expected, es_json)

    @patch("elasticsearch.client.indices.IndicesClient.exists")
    @patch("elasticsearch.client.Elasticsearch.index")
    def test_nomina_same_as_index(self, index, exists):
        """Check that agent autority label"""
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                "Service", category="cat", name="Ardennes", short_name="Ardennes", code="FRAD008"
            )
            agent = cnx.create_entity("AgentAuthority", label="Toto Poulet")
            stable_id = compute_nomina_stable_id(service.code, "888")
            nomina = cnx.create_entity(
                "NominaRecord",
                stable_id=stable_id,
                oai_id="888",
                json_data={
                    "c": {"c": "1R 155", "n": "110", "o": ["ferronnier"]},
                    "e": {
                        "RM": {
                            "d": [{"y": "1900"}],
                            "l": [{"c": "France", "cc": "FR", "d": "Ardennes", "p": "Mézières"}],
                        },
                    },
                    "p": [{"f": "Léon Gustave", "n": "Suquez"}],
                    "t": "RM",
                    "u": "https://archives.cd08.fr/ark:/75583/s0053eb9b6047b1f/53eb9b604f5b9",
                },
                service=service,
                same_as=agent,
            )
            cnx.commit()
            es_json = nomina.cw_adapt_to("INominaIndexSerializable").serialize()
            expected = {
                "acte_type": "RM",
                "alltext": "1R 155 110 ferronnier NMN_RM 1900 Toto Poulet",
                "authority": [agent.eid],
                "creation_date": nomina.creation_date,
                "cw_etype": "NominaRecord",
                "cwuri": f"http://testing.fr/cubicweb/basedenoms/{nomina.stable_id}",
                "dates": {"gte": "1900", "lte": "1900"},
                "eid": nomina.eid,
                "forenames": ["Léon Gustave"],
                "names": ["Suquez"],
                "locations": [
                    "Ardennes",
                    "France",
                    "Mézières",
                ],
                "modification_date": nomina.modification_date,
                "service": service.eid,
                "stable_id": stable_id,
            }
            self.assertEqual(expected, es_json)

    @patch("elasticsearch.client.indices.IndicesClient.exists")
    @patch("elasticsearch.client.Elasticsearch.index")
    def test_nomina_acte_type(self, index, exists):
        """Check the es acte_type is correct"""
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                "Service", category="cat", name="Ardennes", short_name="Ardennes", code="FRAD008"
            )
            stable_id = compute_nomina_stable_id(service.code, "888")
            nomina = cnx.create_entity(
                "NominaRecord",
                stable_id=stable_id,
                oai_id="888",
                json_data={
                    "c": {"c": "1R 155", "n": "110", "o": ["ferronnier"]},
                    "p": [{"f": "Léon Gustave", "n": "Suquez"}],
                    "t": "zz",
                    "u": "https://archives.cd08.fr/ark:/75583/s0053eb9b6047b1f/53eb9b604f5b9",
                },
                service=service,
            )
            cnx.commit()
            es_json = nomina.cw_adapt_to("INominaIndexSerializable").serialize()
            expected = {
                "acte_type": "AU",
                "alltext": "1R 155 110 ferronnier",
                "authority": [],
                "creation_date": nomina.creation_date,
                "cw_etype": "NominaRecord",
                "cwuri": f"http://testing.fr/cubicweb/basedenoms/{nomina.stable_id}",
                "dates": None,
                "eid": nomina.eid,
                "forenames": ["Léon Gustave"],
                "modification_date": nomina.modification_date,
                "names": ["Suquez"],
                "service": service.eid,
                "stable_id": stable_id,
            }
            self.assertEqual(expected, es_json)


if __name__ == "__main__":
    unittest.main()
