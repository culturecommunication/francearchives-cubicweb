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

from datetime import datetime

from io import StringIO

from lxml import etree

from mock import patch

from os import path as osp


from cubicweb import NoResultError

from cubicweb.devtools.testlib import BaseTestCase, CubicWebTC
from cubicweb.dataimport.stores import RQLObjectStore

from cubicweb_francearchives.testutils import (
    PostgresTextMixin,
    EADImportMixin,
    HashMixIn,
    S3BfssStorageTestMixin,
)
from cubicweb_francearchives.testutils import format_date
from cubicweb_francearchives.utils import merge_dicts, pick
from cubicweb_francearchives.dataimport import (
    ead,
    eadreader,
    usha1,
    load_services_map,
    service_infos_from_filepath,
)
from cubicweb_francearchives.dataimport.sqlutil import delete_from_filename

from pgfixtures import setup_module, teardown_module  # noqa


def find_component(cnx, unitid):
    rset = cnx.execute(
        "Any X WHERE X is FAComponent, X did D, " "D unitid %(unitid)s", {"unitid": unitid}
    )
    if rset:
        return rset.one()
    return None


def get_concept(cnx, label):
    return cnx.execute("Any C WHERE L label_of C, L label %(l)s", {"l": label}).one()


def get_fa_redirects(cnx):
    query = """
    SELECT eadid, from_stable_id, to_stable_id
    FROM fa_redirects"""
    return cnx.system_sql(query).fetchall()


class EADTests(BaseTestCase, HashMixIn):
    def test_preprocess_c(self):
        ead_path = self.datapath("FRAD084_IRL000006.xml")
        tree = etree.parse(ead_path)
        self.assertIsNotNone(tree.find('.//c[@id="de-2587"]'))

    def test_preprocess_c_audience_internal(self):
        """The content of tags with audience="internal" attribute is not imported

        Trying: preprocess FRAD084_IRL000006.xml

        Expecting: <c audience="internal"> tags are not imported
        """
        ead_path = self.datapath("FRAD084_IRL000006.xml")
        clean_tree = eadreader.preprocess_ead(ead_path)
        self.assertIsNone(clean_tree.find('.//c[@id="de-2587"]'))

    def test_preprocess_nested_c(self):
        ead_path = self.datapath("FRAD084_IRL000006.xml")
        tree = etree.parse(ead_path)
        self.assertIsNotNone(tree.find('.//c[@id="tt2-114"]'))
        self.assertIsNotNone(tree.find('.//c[@id="de-2599"]'))
        clean_tree = eadreader.preprocess_ead(ead_path)
        self.assertIsNone(clean_tree.find('.//c[@id="tt2-114"]'))
        self.assertIsNone(clean_tree.find('.//c[@id="de-2599"]'))

    def test_preprocess_dap(self):
        ead_path = self.datapath("FRAD084_IRL000006.xml")
        tree = etree.parse(ead_path)
        self.assertIsNotNone(tree.find('.//dao[@id="dao-internal-test"]'))
        clean_tree = eadreader.preprocess_ead(ead_path)
        self.assertIsNone(clean_tree.find('.//dao[@id="dao-internal-test"]'))

    def test_parse_unitid(self):
        ead_path = self.datapath("FRAN_IR_0261167_excerpt.xml")
        tree = eadreader.preprocess_ead(ead_path)
        did = tree.find(".//dsc//did")
        infos = eadreader.did_infos(did)
        self.assertEqual(infos["unitid"], "20050526/1-20050526/26 - 20050526/1-20050526/6")

    def test_parse_empty_unitid(self):
        ead_path = self.datapath("ir_data/FRAD051_est_ead_affichage.xml")
        tree = eadreader.preprocess_ead(ead_path)
        did = tree.find('.//c[@id="a011497973827MCtiYb"]/did')
        infos = eadreader.did_infos(did)
        self.assertFalse(infos["unitid"])

    def test_html_in_titleproper(self):
        ead_path = self.datapath("FRAN_IR_0261167_excerpt.xml")
        tree = eadreader.preprocess_ead(ead_path)
        header_props = eadreader.eadheader_props(tree.find("eadheader"))
        self.assertEqual(
            header_props["titleproper"], "Environnement ; Direction de l'eau (1922-2001)"
        )

    def test_parse_unitdate(self):
        ead_path = self.datapath("FRAN_IR_000224.xml")
        tree = eadreader.preprocess_ead(ead_path)
        reader = eadreader.EADXMLReader(tree, lambda x: x)
        self.assertEqual(
            pick(reader.fa_properties["did"], "unitdate", "startyear", "stopyear"),
            {
                "unitdate": "XIXe-XXe siècles",
                "startyear": 1801,
                "stopyear": 2000,
            },
        )

    def test_parse_date_range(self):
        drange = eadreader.parse_normalized_daterange
        self.assertEqual(drange(None), None)
        self.assertEqual(drange(" "), None)
        self.assertEqual(drange("foo"), None)
        self.assertEqual(drange("82"), {"start": 82, "stop": 82})
        self.assertEqual(drange("823"), {"start": 823, "stop": 823})
        self.assertEqual(drange("823 - 1022"), {"start": 823, "stop": 1022})
        self.assertEqual(drange("  823 -1022  "), {"start": 823, "stop": 1022})
        self.assertEqual(drange("823 - 102"), {"start": 823, "stop": 823})
        self.assertEqual(drange("1234/01/02 - 1235/02/03"), {"start": 1234, "stop": 1235})
        self.assertEqual(drange("1234/01/02-1235/02/03"), {"start": 1234, "stop": 1235})
        self.assertEqual(drange("1234-01-02 / 1235-02-03"), {"start": 1234, "stop": 1235})
        self.assertEqual(drange("1234-01-02/1235-02-03"), {"start": 1234, "stop": 1235})
        self.assertEqual(drange("1801-01-01/2000-12-31"), {"start": 1801, "stop": 2000})

    def test_ignore_invalid_components(self):
        ead_path = self.datapath("FRAD0XX_00001.xml")
        tree = eadreader.preprocess_ead(ead_path)
        reader = eadreader.EADXMLReader(tree, lambda x: x)
        comp_ids = [cnode.get("id") for cnode, cprops in reader.walk()]
        self.assertEqual(comp_ids, ["tt1-1", "tt2", "tt2-1", "tt2-1-3"])

    def test_type_external_link(self):
        """Test using <unitid>'s <exptr> tag as first choice if
        <untid> tag has attribute type="external_link".

        Trying: importing file containing 1 FAComponent having <unitid type="external_link">
        and FAComponents without
        Expecting: former FAComponent's exptr_link is <exptr> tag's content and latter
        FAComponents' exptr_link values are not set
        """
        tree = eadreader.preprocess_ead(self.datapath("ir_data/FRAD037_E_3E18_excerpt.xml"))
        for c in tree.xpath("//c"):
            did = c.find("did")
            extptr = eadreader.did_infos(did)["extptr"]
            if c.attrib.get("id") == "a011532005657UEJhy8":
                self.assertEqual(extptr, "https://archives.touraine.fr/ark:/37621/gq7m1w4nrxf9")
            else:
                self.assertIsNone(extptr)


class EADNodropImporterTC(EADImportMixin, PostgresTextMixin, CubicWebTC):
    readerconfig = merge_dicts({}, EADImportMixin.readerconfig, {"nodrop": False})

    def test_facomponent_data_ok_with_nodrop(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRAN_IR_022409.xml")
            fa = cnx.find("FindingAid").one()
            self.assertEqual(fa.description, None)
            self.assertEqual(fa.description, None)
            self.assertEqual(fa.bibliography, None)
            scopecontent = """<div class="ead-section ead-scopecontent"><div class="ead-wrapper">
         <span class="ead-title">Sommaire</span>
         <div class="ead-p">Enqu&#xEA;te annuelle d&#x2019;entreprise, fichier informatique, 1990. Art 1 : Fichier informatique. Art 2 : Documentation associ&#xE9;e au fichier l&#x2019;acc&#xE8;s &#xE0; une description pr&#xE9;cise de ces documents est assure par l&#x2019;interrogation des fichiers constance</div>
      </div></div>"""  # noqa
            self.assertEqual(fa.scopecontent, scopecontent)


class EADImporterTC(EADImportMixin, PostgresTextMixin, CubicWebTC):
    @classmethod
    def init_config(cls, config):
        super(EADImporterTC, cls).init_config(config)
        config.set_option("instance-type", "consultation")

    def setup_database(self):
        super(EADImporterTC, self).setup_database()
        with self.admin_access.cnx() as cnx:
            cnx.create_entity(
                "Service",
                category="?",
                name="Les Archives Nationales",
                short_name="Les AN",
                code="fran",
            )
            cnx.commit()

    def test_record_id(self):
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            kind_eid = cnx.find("AgentKind", name="person")[0][0]
            name = "Observatoire économique et statistique des transports"
            ar = ce(
                "AuthorityRecord",
                record_id="FRAN_NP_006883",
                agent_kind=kind_eid,
                reverse_name_entry_for=cnx.create_entity(
                    "NameEntry", parts=name, form_variant="authorized"
                ),
                xml_support="foo",
            )
            cnx.commit()
            self.import_filepath(cnx, "FRAN_IR_022409.xml")
            fa = cnx.find("FindingAid").one()
            rset = cnx.execute(
                """Any R, I, L, T WHERE FA eid %(fae)s,
                    I index FA, I label L, I type T, I role R""",
                {"fae": fa.eid},
            )
            expected = [
                ("index", "entreprise", "subject"),
                ("index", "statistique", "function"),
                ("index", "statistique", "genreform"),
                ("index", "transport", "subject"),
                ("index", "transport aérien", "subject"),
                ("index", "transport ferroviaire", "subject"),
                ("index", "transport fluvial", "subject"),
                ("index", "transport maritime", "subject"),
                ("index", "transport routier", "subject"),
                (
                    "originator",
                    "Observatoire \xe9conomique et statistique des transports",
                    "corpname",
                ),
            ]
            self.assertCountEqual(
                expected, [(role, label, itype) for role, _, label, itype in rset.rows]
            )
            originator_eid = [row[1] for row in rset if row[0] == "originator"][0]
            originator = cnx.entity_from_eid(originator_eid)
            self.assertEqual(originator.authority[0].same_as[0].eid, ar.eid)
            self.assertEqual(originator.label, ar.dc_title())

    def test_facomponent_data(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRAN_IR_022409.xml")
            fa = cnx.find("FindingAid").one()
            self.assertEqual(fa.description, None)
            self.assertEqual(fa.description, None)
            self.assertEqual(fa.bibliography, None)
            scopecontent = """<div class="ead-section ead-scopecontent"><div class="ead-wrapper">
         <span class="ead-title">Sommaire</span>
         <div class="ead-p">Enqu&#xEA;te annuelle d&#x2019;entreprise, fichier informatique, 1990. Art 1 : Fichier informatique. Art 2 : Documentation associ&#xE9;e au fichier l&#x2019;acc&#xE8;s &#xE0; une description pr&#xE9;cise de ces documents est assure par l&#x2019;interrogation des fichiers constance</div>
      </div></div>"""  # noqa
            self.assertEqual(fa.scopecontent, scopecontent)

    def test_name_stable_id_ead(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRAN_IR_022409.xml")
            fa = cnx.find("FindingAid").one()
            self.assertEqual("FRAN_IR_022409", fa.eadid)
            self.assertEqual("FRAN_IR_022409.xml", fa.name)
            self.assertEqual(fa.stable_id, usha1(fa.name))

    def test_ir_stable_id_ead(self):
        """Test generated FindingAid and FAComponent stable_ids"""

        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRAN_IR_0261167_excerpt.xml")
            fi = cnx.find("FindingAid").one()
            self.assertEqual(fi.stable_id, "c4b17d67cb5e8e884590ab98a864c81d48239053")
            fa = cnx.find("FAComponent").one()
            self.assertEqual(fa.stable_id, "7a4b5ef85c8014a08654e3c741a337ffdee60b4f")

    def test_publicationstmt(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRAN_IR_022409.xml")
            faheader = cnx.find("FAHeader").one()
            self.assertEqual(
                faheader.titleproper,
                (
                    """Transports ; Enquête annuelle d'entreprises """
                    """auprès des entreprises de transport en 1990"""
                ),
            )
            self.assertEqual(
                faheader.publicationstmt,
                '<div class="ead-section ead-publisher">'
                '<div class="ead-wrapper">Archives nationales</div></div>\n'
                '<div class="ead-section ead-date">'
                '<div class="ead-wrapper">1993</div></div>',
            )

    def test_physdesc(self):
        fa_rql = "Any X WHERE X is FAComponent, X did D, D unitid %(u)s"
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "frad001_0000200j.xml")
            fa = cnx.execute(fa_rql, {"u": "200 J 28"}).one()
            did = fa.did[0]
            expected = """<div class="ead-section ead-physdesc"><div class="ead-wrapper"><div class="ead-p"><b class="ead-autolabel">Description physique:</b>  &lt;lb&gt;&lt;/lb&gt; </div></div>
<div class="ead-label">Registre</div>
<div class="ead-section ead-physfacet"><div class="ead-wrapper"><div class="ead-p"><b class="ead-autolabel">Registre:</b> Oui</div></div></div></div>"""  # noqa
            self.assertEqual(did.physdesc, expected)

    def test_titlestmt(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRAD095_00442.xml")
            faheader = cnx.find("FAHeader").one()
            expected = """<div class="ead-wrapper"><div>    <h1>Etude notariale de Franconville (1518-1907)</h1>R&#xE9;pertoire num&#xE9;rique.<div>Patrick Clervoy, sous la direction de Patrick Lapalu et Marie-H&#xE9;l&#xE8;ne Peltier, directeur des Archives d&#xE9;partementales du Val-d'Oise</div></div></div>"""  # noqa
            self.assertEqual(faheader.titlestmt, expected)

    def test_embedded_facomponent_dao(self):
        fc_rql = "Any X WHERE X is FAComponent, X did D, D unitid %(u)s"
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRAD095_00374.xml")
            fc = cnx.execute(fc_rql, {"u": "3Q7 753 - 893"}).one()
            did = fc.did[0]
            self.assertEqual(did.unittitle, "Instruments de recherche.")
            self.assertEqual(
                did.origination,
                (
                    """<div class="ead-wrapper"><div class="ead-p"><b class="ead-autolabel">producteur:</b> Seine-et-Oise. Direction de l'Enregistrement</div></div>"""  # noqa
                ),
            )
            self.assertEqual(fc.scopecontent, None)
            self.assertEqual(len(fc.digitized_versions), 0)
            fc = cnx.execute(fc_rql, {"u": "3Q7 753 - 773"}).one()
            did = fc.did[0]
            self.assertEqual(
                did.unittitle, "Décès, absences et successions : tables alphabétiques."
            )
            # make sure origination and scopecontent are html-wrapped
            self.assertEqual(
                did.origination,
                '<div class="ead-wrapper"><div class="ead-p">'
                '<b class="ead-autolabel">producteur:</b> '
                "Seine-et-Oise. Direction de l'Enregistrement</div></div>",
            )
            self.assertTrue(
                fc.scopecontent.startswith(
                    '<div class="ead-section ead-scopecontent">'
                    '<div class="ead-wrapper"><div class="ead-p">'
                )
            )

    def test_facomponent_dao_FRAD085_6(self):
        """specific rules for Vendée"""
        fc_rql = "Any X WHERE X is FAComponent, X did D, D unitid %(u)s"
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRAD085_6Fi.xml")
            fc = cnx.execute(fc_rql, {"u": "6 Fi 1130"}).one()
            got = [(d.url, d.illustration_url, d.role) for d in fc.digitized_versions]
            expected = [
                ("1", None, "nombre"),
                (None, "Fr\\Ad85\\2Num8\\2Num8_126\\2Num8_126_001.jpg", "thumbnail"),
            ]
            self.assertCountEqual(got, expected)

    def test_facomponent_dao_FRAD085_2C(self):
        """specific rules for Vendée"""
        fc_rql = "Any X WHERE X is FAComponent, X did D, D unitid %(u)s"
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRAD085_2C.xml")
            fc = cnx.execute(fc_rql, {"u": "2 C 2"}).one()
            got = [(d.url, d.illustration_url, d.role) for d in fc.digitized_versions]
            expected = [("52", None, "nombre"), ("FR\\Ad85\\2Num286\\018\\2C2", None, "répertoire")]
            self.assertCountEqual(got, expected)

    def test_facomponent_digitized_urls_FRAD084(self):
        """Test digitized_urls.

        Trying: all of the dao tags contain absolute URL and supported role
        Expecting: digitized_urls is empty
        """
        fc_rql = "Any X WHERE X is FAComponent, X did D, D unitid %(u)s"
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "ir_data/FRAD084_IR0000412.xml")
            fc = cnx.execute(fc_rql, {"u": "74 J 2"}).one()
            self.assertFalse(fc.digitized_urls)

    def test_findingaid_digitized_urls(self):
        """Test digitized_urls.

        Trying: import a FindingAid with daogroup
        Expecting: 1 digitized_versions is created for the FindingAid
        """
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "ir_data/FRAD066_1B.xml")
            fa = cnx.find("FindingAid").one()
            got = [(d.url, d.illustration_url, d.role) for d in fa.digitized_versions]
            expected = [
                ("https://archive.org/details/inventairesommai13arch/page/n6/mode/2up", None, None),
            ]
            self.assertCountEqual(got, expected)

    def test_findingaid_digitized_urls_not_in_es_doc(self):
        """Test digitized_urls.

        Trying: import a FindingAid with daogroup
        Expecting: 1 digitized_versions is created for the FindingAid and present in es
        """
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "ir_data/FRAD066_1B.xml")
            fa = cnx.find("FindingAid").one()
            dvs = fa.digitized_versions
            self.assertEqual(1, len(dvs))
            adapter = fa.cw_adapt_to("IFullTextIndexSerializable")
            self.assertNotIn("digitized_versions", adapter.serialize())

    def test_facomponent_relatedmaterial_FRAD067(self):
        """specific rules for Bas-Rhin"""
        fc_rql = "Any X WHERE X is FAComponent, X did D, D unitid %(u)s"
        with self.admin_access.cnx() as cnx:
            fpath = "FRAD067_1_FRAD067_EDF1_archives_paroissiales.xml"
            self.import_filepath(cnx, fpath)
            fc = cnx.execute(fc_rql, {"u": "2 G"}).one()
            url = "http://archives.bas-rhin.fr/media/96780/2G0Tabledesparoissesdef.pdf"
            relatedmaterial = (
                '<a href="{url}" rel="nofollow noopener noreferrer" '
                'target="_blank">{url}</a>'.format(url=url)
            )
            self.assertIn(relatedmaterial, fc.additional_resources)

    def test_facomponent_dao_FRAD062(self):
        """Pas de Calais"""
        fc_rql = "Any X WHERE X is FAComponent, X did D, D unitid %(u)s"
        with self.admin_access.cnx() as cnx:
            fpath = "FRAD062_ir_9fi_02_permaliens.xml"
            self.import_filepath(cnx, fpath)
            fc = cnx.execute(fc_rql, {"u": "9 Fi 1"}).one()
            # role image
            url = "http://archivesenligne.pasdecalais.fr/ark:/64297/5e7c97997adc45bcdafd11b170ae7b11"  # noqa
            self.assertTrue(fc.illustration_url, url)
            fc = cnx.execute(fc_rql, {"u": "9 Fi 2"}).one()
            # role thumbnail
            url = "http://archivesenligne.pasdecalais.fr/ark:/64297/1a9927cc6cbbe29139031df77d2be48"  # noqa
            self.assertTrue(fc.illustration_url, url)

    def test_index_entries_inheritance(self):
        fc_rql = "Any X WHERE X is FAComponent, X did D, D unitid %(u)s"
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRAD095_00374.xml")
            fc = cnx.execute(fc_rql, {"u": "3Q7 753 - 893"}).one()
            subjects = [i.label for i in fc.subject_indexes().entities()]
            self.assertCountEqual(subjects, ["ENREGISTREMENT"])
            fc = cnx.execute(fc_rql, {"u": "3Q7 753 - 773"}).one()
            subjects = [i.label for i in fc.subject_indexes().entities()]
            self.assertCountEqual(subjects, ["ENREGISTREMENT", "SUCCESSION", "TABLE ALPHABETIQUE"])

    def test_authority_entries_facomponent(self):
        with self.admin_access.cnx() as cnx:
            fc_rql = "Any X WHERE X is FAComponent, X did D, D unitid %(u)s"
            self.import_filepath(cnx, "FRAN_IR_050263.xml")
            for e in cnx.execute(
                fc_rql, {"u": "MC/ET/LXXXVI/1565-MC/ET/LXXXVI/2197 - MC/ET/LXXXVI/1984"}
            ).entities():
                if e.did[0].unittitle.startswith("Inventaire après dissolution"):
                    fc = e
            index_entries = [
                (
                    ie.authority[0].cw_etype,
                    ie.authority[0].label,
                    ie.type,
                )
                for ie in fc.reverse_index
            ]
            expected = [
                ("AgentAuthority", "Hugo, Victor", "persname"),
                ("SubjectAuthority", "inventaire", "genreform"),
                ("SubjectAuthority", "littérature", "subject"),
            ]
            self.assertCountEqual(expected, index_entries)

    def test_indexes_facomponents(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRAD090_2r_index.xml")
            fc = cnx.execute(
                "Any X WHERE X is FAComponent, X did D, D unitid %(u)s",
                {"u": "a011497973827MCtiYb"},
            ).one()
            index_entries = [
                (
                    ie.authority[0].cw_etype,
                    ie.authority[0].label,
                    ie.type,
                )
                for ie in fc.reverse_index
            ]
            expected = [
                ("SubjectAuthority", "archdesc-controlaccess-function", "function"),
                ("SubjectAuthority", "archdesc-controlaccess-genreform", "genreform"),
                ("SubjectAuthority", "archdesc-bioghist-subject", "subject"),
                ("SubjectAuthority", "archdesc-physdesc-genreform", "genreform"),
                ("LocationAuthority", "normal-archdesc-scopecontent-geogname", "geogname"),
                ("AgentAuthority", "archdesc-unittitle-corpname", "corpname"),
                ("AgentAuthority", "cdid-unittitle-famname", "famname"),
                ("LocationAuthority", "cdid-bioghist-geogname", "geogname"),
                ("AgentAuthority", "cdid-bioghist-corpname", "corpname"),
                ("SubjectAuthority", "cdid-scopecontent-subject-p", "subject"),
                ("SubjectAuthority", "normal-cdid-scopecontent-subject-bare", "subject"),
                ("SubjectAuthority", "cdid-controlaccess-subject", "subject"),
                ("SubjectAuthority", "cdid-controlacess-occupation", "occupation"),
                ("SubjectAuthority", "normal-cdid-physdesc-genreform", "genreform"),
            ]
            self.assertCountEqual(expected, index_entries)

    def test_indexes_findingaid(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRAD090_2r_index.xml")
            fa = cnx.find("FindingAid").one()
            index_entries = [
                (
                    ie.authority[0].cw_etype,
                    ie.authority[0].label,
                    ie.type,
                )
                for ie in fa.reverse_index
            ]
            expected = [
                ("SubjectAuthority", "archdesc-controlaccess-function", "function"),
                ("SubjectAuthority", "archdesc-controlaccess-genreform", "genreform"),
                ("SubjectAuthority", "archdesc-bioghist-subject", "subject"),
                ("LocationAuthority", "normal-archdesc-scopecontent-geogname", "geogname"),
                ("AgentAuthority", "archdesc-unittitle-corpname", "corpname"),
                ("SubjectAuthority", "archdesc-physdesc-genreform", "genreform"),
            ]
            self.assertCountEqual(expected, index_entries)

    def test_indexes_within_p(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "ir_data/FRAD001_0000002M.xml")
            fa = cnx.find("FindingAid").one()
            index_entries = [
                (
                    ie.authority[0].cw_etype,
                    ie.authority[0].label,
                    ie.type,
                )
                for ie in fa.reverse_index
            ]
            expected = [
                ("AgentAuthority", "Administration du département de l'Ain", "corpname"),
                ("AgentAuthority", "CHRISTIAN FIZE", "persname"),
                ("SubjectAuthority", "Document d'archives", "genreform"),
                ("LocationAuthority", "L'ILE AUX MERVEILLES", "geogname"),
                ("SubjectAuthority", "Recherche détaillée", "genreform"),
            ]
            self.assertCountEqual(expected, index_entries)
            fa = cnx.execute("Any X WHERE X is FAComponent, X did D, D unitid '2 L 58'").one()
            index_entries = [
                (
                    ie.authority[0].cw_etype,
                    ie.authority[0].label,
                    ie.type,
                )
                for ie in fa.reverse_index
            ]
            expected = [
                ("SubjectAuthority", "ACCUSES 26608", "subject"),
                ("AgentAuthority", "CHRISTIAN FIZE", "persname"),
                ("SubjectAuthority", "Document d'archives", "genreform"),
                ("SubjectAuthority", "LES LICORNES 26602", "subject"),
                ("LocationAuthority", "L'ILE AUX MERVEILLES", "geogname"),
                ("LocationAuthority", "L'ILE AUX MERVEILLES 26605", "geogname"),
                ("SubjectAuthority", "Recherche détaillée", "genreform"),
                ("SubjectAuthority", "Recherche détaillée 26608", "genreform"),
            ]
            self.assertCountEqual(expected, index_entries)

    def test_empty_unitid(self):
        with self.admin_access.cnx() as cnx:
            fc_rql = "Any X WHERE X is FAComponent, X did D, D unittitle %(u)s"
            fname = "ir_data/FRAD051_est_ead_affichage.xml"
            self.import_filepath(cnx, fname)
            fc = cnx.execute(fc_rql, {"u": "1458-1992"}).one()
            self.assertFalse(fc.did[0].unitid)

    def test_empty_oai_id(self):
        """
        Triyng: import a FindingAid
        Expected: FindingAid.oai_id attribute is None
        """
        with self.admin_access.cnx() as cnx:
            fname = "ir_data/FRAD051_est_ead_affichage.xml"
            self.import_filepath(cnx, fname)
            self.assertIsNone(cnx.find("FindingAid").one().oai_id)

    def test_findingaid_bioghist(self):
        with self.admin_access.cnx() as cnx:
            fname = "ir_data/FRAD051_est_ead_affichage.xml"
            self.import_filepath(cnx, fname)
            fa = cnx.execute("Any X WHERE X is FindingAid").one()
            expected = '<div class="ead-p">bioghist: A concise essay or chronology'
            self.assertIn(expected, fa.bioghist)

    def test_facomponent_physdesc(self):
        with self.admin_access.cnx() as cnx:
            fname = "ir_data/FRAD051_est_ead_affichage.xml"
            self.import_filepath(cnx, fname)
            fc_rql = "Any X WHERE X is FAComponent, X did D, D unittitle %(u)s"
            fc = cnx.execute(fc_rql, {"u": "1458-1992"}).one()
            for label in ("label extent", "dimensions_label"):
                self.assertIn(label, fc.did[0].physdesc)

    def test_facomponent_materialspec(self):
        with self.admin_access.cnx() as cnx:
            fname = "ir_data/FRAD051_est_ead_affichage.xml"
            self.import_filepath(cnx, fname)
            fc_rql = "Any X WHERE X is FAComponent, X did D, D unittitle %(u)s"
            fc = cnx.execute(fc_rql, {"u": "1458-1992"}).one()
            for label in (
                '<b class="ead-label">Mathematical Data:</b>',
                '<b class="ead-label">Scale:</b> 1:10000</div>',
                '<b class="ead-label">Projection:</b>',
            ):
                self.assertIn(label, fc.did[0].materialspec)

    def test_facomponent_notes(self):
        with self.admin_access.cnx() as cnx:
            fname = "ir_data/FRAD051_est_ead_affichage.xml"
            self.import_filepath(cnx, fname)
            fc_rql = "Any X WHERE X is FAComponent, X did D, D unittitle %(u)s"
            fc = cnx.execute(fc_rql, {"u": "1458-1992"}).one()
            expected = """<div class="ead-wrapper">
                    <ul class="ead-list-unmarked"><li>odd, item = Department of Economic Affairs: Industrial Policy Group:
                            Registered Files (1-IG and 2-IG Series) EW 26
                        </li><li>item = Department of Economic Affairs: Industrial Division and
                            Industrial Policy Division: Registered Files (IA Series) EW 27
                        </li></ul>
                </div>"""  # noqa
            self.assertEqual(expected, fc.notes)

    def test_findingaid_changes(self):
        with self.admin_access.cnx() as cnx:
            fname = "ir_data/FRAD051_est_ead_affichage.xml"
            self.import_filepath(cnx, fname)
            fa = cnx.execute("Any X WHERE X is FindingAid").one()
            self.assertIn("May 5, 1997", fa.fa_header[0].changes)
            expected = "This electronic finding aid was updated to"
            self.assertIn(expected, fa.fa_header[0].changes)

    def test_findingaid_notes(self):
        with self.admin_access.cnx() as cnx:
            fname = "ir_data/FRAD051_est_ead_affichage.xml"
            self.import_filepath(cnx, fname)
            fa = cnx.execute("Any X WHERE X is FindingAid").one()
            expected = """<div class="ead-wrapper">
            <ul class="ead-list-unmarked"><li>odd. item. Department of Economic Affairs: Industrial Policy Group: Registered
                    Files (1-IG and 2-IG Series) EW 26
                </li><li>Department of Economic Affairs: Industrial Division and Industrial Policy
                    Division: Registered Files (IA Series) EW
                        27
                </li></ul>
        </div>"""  # noqa
            self.assertEqual(expected, fa.notes)

    def test_services_normalization(self):
        with self.admin_access.cnx() as cnx:
            cnx.commit()
            self.import_filepath(cnx, "FRAN_IR_022409.xml")
            fa = cnx.find("FindingAid").one()
            service = cnx.find("Service", code="fran").one()
            self.assertEqual(fa.related_service.eid, service.eid)
            self.assertEqual(fa.publisher, "Les AN")

    def test_FRAD001_service_code(self):
        """Test EAD XML files.

        Trying: import a stored OAI EAD file from `FRAD001_EC_THOL` eadid
        Expecting: the createed FindingAid is related to right `FRAD001` service
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity("Service", code="FRAD001", category="foo")
            cnx.commit()
            self.import_filepath(cnx, "ir_data/frad001_ec_thol.xml")
            fa = cnx.find("FindingAid").one()
            self.assertEqual(fa.related_service, service)

    def test_agent_index_creation(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRAN_IR_0261167_excerpt.xml")
            self.assertEqual(len(cnx.find("AgentName")), 4)
            fa = cnx.find("FindingAid").one()
            agents = [
                (i.label, i.type, i.role, i.authfilenumber) for i in fa.agent_indexes().entities()
            ]
            expected = [
                ("Direction de l'eau", "corpname", "originator", "FRAN_NP_006122"),
                ("Jean-Michel", "persname", "index", None),
            ]
            self.assertCountEqual(expected, agents)
            comp = cnx.find("FAComponent").one()
            agents = [
                (i.label, i.type, i.role, i.authfilenumber) for i in comp.agent_indexes().entities()
            ]
            expected = [
                ("Direction de l'eau", "corpname", "originator", "FRAN_NP_006122"),
                ("Jean-Michel", "persname", "index", None),
                ("Jean-Paul", "persname", "index", None),
                ("jean-Michel", "persname", "index", None),
            ]
            self.assertCountEqual(expected, agents)

    def test_subject_index_creation(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRAN_IR_0261167_excerpt.xml")
            self.assertEqual(len(cnx.find("Subject")), 13)
            fa = cnx.find("FindingAid").one()
            subjects = [(i.label, i.type, i.role) for i in fa.subject_indexes().entities()]
            expected = [
                ("aquaculture", "subject", "index"),
                ("function", "function", "index"),
                ("notaire", "occupation", "index"),
                ("pisciculture", "subject", "index"),
                ("poisson", "function", "index"),
                ("poisson", "subject", "index"),
                ("étude", "genreform", "index"),
                ("unicode control character", "subject", "index"),
            ]
            self.assertCountEqual(expected, subjects)
            comp = cnx.find("FAComponent").one()
            subjects = [(i.label, i.type, i.role) for i in comp.subject_indexes().entities()]
            expected = [
                ("poisson", "subject", "index"),
                ("pisciculture", "subject", "index"),
                ("aquaculture", "subject", "index"),
                ("poisson", "function", "index"),
                ("function", "function", "index"),
                ("\xe9tude", "genreform", "index"),
                ("notaire", "occupation", "index"),
                ("Poisson", "subject", "index"),
                ("petits poissons", "subject", "index"),
                ("m\xe9decin", "function", "index"),
                ("plan", "genreform", "index"),
                ("avocat", "occupation", "index"),
                ("unicode control character", "subject", "index"),
            ]
            self.assertCountEqual(expected, subjects)

    def test_location_index_creation(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRAN_IR_0261167_excerpt.xml")
            self.assertEqual(len(cnx.find("Geogname")), 2)
            fa = cnx.find("FindingAid").one()
            locations = [(i.label, i.type) for i in fa.geo_indexes().entities()]
            expected = [("garonne (cours d'eau)", "geogname")]
            self.assertCountEqual(expected, locations)
            comp = cnx.find("FAComponent").one()
            locations = [(i.label, i.type) for i in comp.geo_indexes().entities()]
            expected = [
                ("Garonne (cours d'eau)", "geogname"),
                ("garonne (cours d'eau)", "geogname"),
            ]
            self.assertCountEqual(expected, locations)

    def test_pdf_unique_index_metadata(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "pdf/FRAC13004_IC_II.pdf")
            fa = cnx.find("FindingAid").one()
            self.assertEqual(20, fa.agent_indexes().rowcount)
            self.assertEqual(46, fa.subject_indexes().rowcount)
            self.assertEqual(1, fa.geo_indexes().rowcount)

    def test_findingaid_data(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRAD095_00259.XML")
            fa = cnx.find("FindingAid").one()
            self.assertEqual(fa.eadid, "FRAD095_00259")
            self.assertEqual(fa.description, None)
            self.assertEqual(fa.bibliography, None)
            self.assertEqual(fa.acquisition_info, None)
            self.assertEqual(fa.scopecontent, None)
            did = fa.did[0]
            self.assertEqual(did.materialspec, None)
            origination = (
                '<div class="ead-wrapper"><div class="ead-p">'
                '<b class="ead-autolabel">producteur:</b> '
                "PRODUCTEURS MULTIPLES</div></div>"
            )
            self.assertEqual(did.origination, origination)

    def test_findingaid_data_FRAD09_1r(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRAD090_1r_retoucheFA.xml")
            fa = cnx.find("FindingAid").one()
            self.assertEqual(fa.eadid, "archref")
            self.assertEqual(fa.did[0].unitid, "unitid: 1 R 109-277")
            self.assertIn("archives administratives militaires (BCAAM)", fa.acquisition_info)
            self.assertIn("loi du 15 juillet 2008", fa.accessrestrict)
            self.assertIn("imprimante personnelle ou en salle de lecture", fa.userestrict)
            self.assertIn("anonyme, 38 p. Alouette", fa.additional_resources)  # otherfindaid
            self.assertIn(
                "Territoire de Belfort avant 1870", fa.additional_resources
            )  # separatedmaterial
            self.assertIn("Q pour les Biens nationaux", fa.additional_resources)  # relatedmaterial

    def test_authority_in_es_docs(self):
        with self.admin_access.cnx() as cnx:
            es_docs = self.import_filepath(cnx, "FRAN_IR_0261167_excerpt.xml")
            aa = cnx.find("AgentAuthority", label="Direction de l'eau").one()
            self.assertEqual(len(es_docs), 2)
            fa_es_doc, comp_es_doc = es_docs
            self.assertEqual(
                aa.eid,
                [
                    i
                    for i in fa_es_doc["_source"]["index_entries"]
                    if i["label"] == "Direction de l'eau"
                ][0]["authority"],
            )

    def test_singleton_bibliography_div(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRAD095_00442.xml")
            fa = cnx.find("FindingAid").one()
            self.assertFalse(fa.bibliography)

    def test_singleton_arrangement_div(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRAD095_00442.xml")
            fa = cnx.find("FindingAid").one()
            expected = (
                '<div class="ead-section ead-arrangement">'
                '<div class="ead-wrapper"><div class="ead-p">'
                "Classement chronologique</div></div></div>"
            )
            self.assertIn(expected, fa.description)

    def test_singleton_accruals_div(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRAD095_00442.xml")
            fa = cnx.find("FindingAid").one()
            expected = (
                """<div class="ead-section ead-accruals">"""
                """<div class="ead-wrapper"><div class="ead-p">"""
                """Fonds ouvert susceptible d'accroissement</div></div></div>"""
            )
            self.assertIn(expected, fa.description)

    def test_singleton_appraisal_div(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRAD095_00442.xml")
            fa = cnx.find("FindingAid").one()
            expected = (
                '<div class="ead-section ead-appraisal">'
                '<div class="ead-wrapper"><div class="ead-p">'
                "Aucun</div></div></div>"
            )
            self.assertIn(expected, fa.description)

    def test_multiple_accessrestrict_divs(self):
        """
        Trying: import an IR with multiple accessrestrict
        Expecting: all accessrestricts are present on the FindingAid
        """
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "ir_data/FRANMT_IR_1996_94.xml")
            fa = cnx.find("FindingAid").one()
            expected = """<div class="ead-section ead-accessrestrict"><div class="ead-wrapper">
      Archives priv&#xE9;es. Les documents produits avant 1946 sont consid&#xE9;r&#xE9;s comme des archives priv&#xE9;es. C'est &#xE0; cette date seulement que l'entreprise est nationalis&#xE9;e.
    </div>
<div class="ead-wrapper">
      Microfilms &#xAB; librement communicables &#xBB;. En effet, les d&#xE9;lais applicables sont ceux du Code du patrimoine par analogie avec les archives publiques : ils sont aujourd'hui tous &#xE9;chus.
    </div>
<div class="ead-wrapper">Publiable sur internet</div></div>"""  # noqa
            self.assertEqual(expected, fa.accessrestrict)

    def test_multiple_userestrict_divs(self):
        """
        Trying: import an IR with multiple userestrict
        Expecting: all userestrict are present in the FindingAid
        """
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "ir_data/FRANMT_IR_1996_94.xml")
            fa = cnx.find("FindingAid").one()
            expected = """<div class="ead-section ead-userestrict"><div class="ead-wrapper"> La r&#xE9;utilisation des documents microfilm&#xE9;s est gratuite et libre, sous r&#xE9;serve des dispositions relatives aux droits de propri&#xE9;t&#xE9; intellectuelle et au respect de la vie priv&#xE9;e (voir les modalit&#xE9;s d'application sur le site internet des ANMT). </div>
<div class="ead-wrapper"> Test. </div></div>"""  # noqa
            self.assertEqual(expected, fa.userestrict)

    def test_concept_alignment(self):
        """
        Trying: create a Concept in "thesaurus W" with `poIssON` label and import an IR with
        `poisson` and `Poisson` labeled subjects under "service/strict" index policy
        Expecting: both SubjectAuthorities are related to the `poIssON` concept
        """
        with self.admin_access.cnx() as cnx:
            scheme = cnx.create_entity("ConceptScheme", title="thesaurus W")
            c1 = cnx.create_entity("Concept", in_scheme=scheme)
            cnx.create_entity(
                "Label", label="hip", language_code="fr", kind="preferred", label_of=c1
            )
            c2 = cnx.create_entity("Concept", in_scheme=scheme, broader_concept=c1)
            cnx.create_entity(
                "Label", label="hop", language_code="fr", kind="preferred", label_of=c2
            )
            cnx.create_entity(
                "Label", label="poIssON", language_code="fr", kind="alternative", label_of=c2
            )
            for label in ("function", "notaire", "étude"):
                cnx.create_entity(
                    "Concept",
                    in_scheme=scheme,
                    reverse_label_of=cnx.create_entity(
                        "Label", label=label, language_code="fr", kind="preferred"
                    ),
                )
            cnx.commit()
            self.import_filepath(
                cnx,
                "FRAN_IR_0261167_excerpt.xml",
                autodedupe_authorities="service/strict",
            )

            same_as_rset = cnx.execute("Any X WHERE X is SubjectAuthority, X same_as C")
            self.assertEqual(len(same_as_rset), 5)
            for label in ("poisson", "Poisson"):
                poisson = cnx.find("SubjectAuthority", label="Poisson").one()
                self.assertEqual(poisson.same_as[0].eid, c2.eid)
            for label, stype in (
                ("function", "function"),
                ("notaire", "occupation"),
                ("étude", "genreform"),
            ):
                subject = cnx.find("SubjectAuthority", label=label).one()
                self.assertEqual(subject.same_as[0].eid, get_concept(cnx, label).eid)
                self.assertEqual(subject.reverse_authority[0].type, stype)
                self.assertTrue(subject.quality)

    def test_dao(self):
        url = "https://www.siv.archives-nationales.culture.gouv.fr/mm/media/download/FRDAFAN85_OF9v173541_L-min.jpg"  # noqa
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRAN_IR_051016_excerpt.xml")
            fc = cnx.find("FAComponent", component_order=0).one()
            self.assertEqual(len(fc.digitized_versions), 2)
            self.assertEqual(fc.illustration_url, url)

    def test_daogrp(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRAD095_00374.xml")
            comp = find_component(cnx, "3Q7 1 - 752")
            self.assertEqual(len(comp.digitized_versions), 0)
            comp = find_component(cnx, "3Q7 1 - 7")
            self.assertEqual(len(comp.digitized_versions), 0)
            comp = find_component(cnx, "3Q7 753")
            dv_urls = [dv.illustration_url for dv in comp.digitized_versions]
            self.assertCountEqual(
                dv_urls,
                [
                    "/FRAD095_00374/FRAD095_3Q7_753/FRAD095_3Q7_753_0001.jpg",
                    "/FRAD095_00374/FRAD095_3Q7_753/FRAD095_3Q7_753_0091.jpg",
                ],
            )
            comp = find_component(cnx, "3Q7 754")
            dv_urls = [dv.illustration_url for dv in comp.digitized_versions]
            self.assertCountEqual(
                dv_urls,
                [
                    "/FRAD095_00374/FRAD095_3Q7_754/FRAD095_3Q7_754_0001.jpg",
                    "/FRAD095_00374/FRAD095_3Q7_754/FRAD095_3Q7_754_0111.jpg",
                ],
            )
            comp = find_component(cnx, "3Q7 755")
            dv_urls = [dv.illustration_url for dv in comp.digitized_versions]
            self.assertCountEqual(
                dv_urls,
                [
                    "/FRAD095_00374/FRAD095_3Q7_755/FRAD095_3Q7_755_0001.jpg",
                    "/FRAD095_00374/FRAD095_3Q7_755/FRAD095_3Q7_755_0048.jpg",
                ],
            )

    def test_component_order(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRAN_IR_051016_excerpt.xml")
            fac_unitids = sorted(
                (comp.component_order, comp.did[0].unitid)
                for comp in cnx.find("FAComponent").entities()
            )
            self.assertEqual(
                fac_unitids,
                [
                    (0, "19860711/412-19860711/415 - 19860711/412"),
                    (1, "19860711/412-19860711/411 - 19860711/409"),
                ],
            )

    def test_findingaid_support_hash_import_pdf(self):
        """
        Trying: import pdf file
        Expecting: findingaid_support data_hash is correctly set
        """
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRSHD_PUB_00000345_0001.pdf")[0]
            fa_support = cnx.execute("Any X WHERE F findingaid_support X").one()
            self.assertEqual(fa_support.data_hash, fa_support.compute_hash())
            self.assertTrue(fa_support.check_hash())

    def test_pdf_metadata(self):
        with self.admin_access.cnx() as cnx:
            es_doc = self.import_filepath(cnx, "FRSHD_PUB_00000345_0001.pdf")[0]
            fa = cnx.find("FindingAid").one()
            jmo = cnx.find("SubjectAuthority", label="Journal des marches et opérations (JMO)")
            self.assertEqual(len(jmo), 1)
            index_entries = es_doc["_source"]["index_entries"]
            self.assertEqual(len(index_entries), 2)
            self.assertCountEqual(
                index_entries,
                [
                    {
                        "authfilenumber": None,
                        "authority": jmo[0][0],
                        "label": "Journal des marches et opérations (JMO)",
                        "normalized": "journal des marches et operations jmo",
                        "role": "index",
                        "type": "subject",
                    },
                    {
                        "authfilenumber": None,
                        "authority": cnx.find(
                            "SubjectAuthority", label="Instrument de recherche (archives)"
                        )[0][0],
                        "label": "Instrument de recherche (archives)",
                        "normalized": "instrument de recherche archives",
                        "role": "index",
                        "type": "genreform",
                    },
                ],
            )
            self.assertEqual(
                fa.dc_title(),
                "[Archives de l'armée de Terre]. Inventaire des archives "
                "de commandement et journaux des marches et opérations des "
                "formations de l’armée de terre. Sous-série GR 7 U (1946-1964).",
            )
            self.assertEqual(fa.did[0].startyear, 1946)
            self.assertEqual(fa.did[0].stopyear, 1964)
            self.assertEqual(fa.did[0].physdesc, None)
            self.assertEqual(fa.did[0].lang_description, None)
            self.assertTrue(1, len(fa.digitized_versions))
            expected_url = "http://francearchives.fr/image.png"
            self.assertEqual(expected_url, fa.illustration_url)
            self.assertEqual(expected_url, fa.thumbnail_dest)
            self.assertIn("Service historique", fa.did[0].origination)

    def test_name_stable_id_pdf_with_metadata(self):
        """stable_id is based in the filename with extension:
        - column 'identifiant_fichier' of metadata file with extension:"""
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRSHD_PUB_00000345_0001.pdf")
            fa = cnx.find("FindingAid").one()
            self.assertEqual("FRSHD_PUB_00000345_0001", fa.eadid)
            self.assertEqual("FRSHD_PUB_00000345_0001.pdf", fa.name)
            self.assertEqual(fa.stable_id, usha1(fa.name))

    def test_name_stable_id_pdf_without_metadata(self):
        """stable id is based on filename without extension"""
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "pdf/FRSHD_PUB_00000345_0002.pdf")
            fa = cnx.find("FindingAid").one()
            self.assertEqual("FRSHD_PUB_00000345_0002", fa.eadid)
            self.assertEqual("FRSHD_PUB_00000345_0002", fa.name)
            self.assertEqual(fa.stable_id, usha1(fa.name))

    def test_nonregr_unittile_not_null(self):
        """unittitle should not be null: use unitdata instead (cf. #58785477)"""
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "ir_data/FRANOM_01250_excerpt.xml")
            title = cnx.execute(
                "Any DT WHERE D is Did, D unitid %(id)s, D unittitle DT",
                {"id": "FR ANOM 91 / 2 M 242 a"},
            )[0][0]
            self.assertEqual(title, "1845-1898")

    def test_extptr_when_ark_is_specified(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "ir_data/FRANOM_01250_excerpt.xml")
            extpr = cnx.execute(
                "Any X WHERE D extptr X, D unitid %(id)s", {"id": "FR ANOM 91 / 2 M 242 a"}
            )[0][0]
            self.assertEqual(extpr, "ark:/61561/kd508auuzxb")

    def test_ape_ead_path(self):
        with self.admin_access.cnx() as cnx:
            filepath = "ir_data/v1/FRAD095_00374.xml"
            self.import_filepath(cnx, filepath)
            fa = cnx.find("FindingAid").one()
            self.assertEqual(len(fa.ape_ead_file), 1)
            ape_filepath = cnx.execute(
                "Any FSPATH(D) WHERE X ape_ead_file F, F data D, X eid %(x)s", {"x": fa.eid}
            )[0][0].getvalue()
            # FIXME s3 we shoud not take account of cnx.vreg.config["appfiles-dir"] which must be ""
            expected_path = self.get_filepath_by_storage(
                f"{self.config['appfiles-dir']}/ape-ead/FRAD095/ape-FRAD095_00374.xml"
            ).encode("utf-8")
            self.assertEqual(ape_filepath, expected_path)
            self.assertTrue(self.fileExists(ape_filepath))

    def test_ape_ead_deleted(self):
        with self.admin_access.cnx() as cnx:
            filepath = "ir_data/v1/FRAD095_00374.xml"
            self.import_filepath(cnx, filepath)
            fa = cnx.find("FindingAid").one()
            self.assertTrue(cnx.execute("Any X WHERE X ape_ead_file F"))
            delete_from_filename(
                cnx, fa.stable_id, is_filename=False, interactive=False, esonly=False
            )
            cnx.commit()
            self.assertFalse(cnx.find("FindingAid"))
            self.assertFalse(cnx.execute("Any X WHERE X ape_ead_file F"))

    def test_ape_ead_legalstatus(self):
        """Test legalstatus display of FAComponent.

        Trying: import in IR with <legalstatus type="arch_privee" altrender="Archives privées">
        Expecting: legalstatus@altrender value is found in ape_ead <accessrestrict>

        """
        with self.admin_access.cnx() as cnx:
            cnx.create_entity(
                "Service",
                code="FRAD040",
                category="L",
            )
            cnx.commit()
            filepath = "ir_data/FRAD040_000020FI__fiche_img.xml"
            self.import_filepath(cnx, filepath)
            fi = cnx.find("FindingAid").one()
            ape_ead_file = fi.ape_ead_file[0]
            content = ape_ead_file.data.read()
            tree = etree.fromstring(content)
            for accessrestrict in tree.xpath(
                "//e:archdesc/e:accessrestrict", namespaces={"e": tree.nsmap[None]}
            ):
                html = etree.tostring(accessrestrict).decode("utf-8")
                if "<head>Statut juridique</head>" in html:
                    expected = """<p>Archives priv&#233;es. Les documents produits avant 1946"""
                    self.assertIn(expected, html)

    def test_ape_ead_archdesc_tags_1(self):
        """Test legalstatus display of FAComponent.

        Trying: import in IR
        Expecting: exptected attributes are found in ape_ead <accessrestrict>

        """
        with self.admin_access.cnx() as cnx:
            cnx.create_entity(
                "Service",
                code="FRAD040",
                category="L",
            )
            cnx.commit()
            filepath = "ir_data/FRAD040_000020FI__fiche_img.xml"
            self.import_filepath(cnx, filepath)
            fi = cnx.find("FindingAid").one()
            ape_ead_file = fi.ape_ead_file[0]
            content = ape_ead_file.data.read()
            tree = etree.fromstring(content)
            for tag in ("bioghist", "acqinfo", "scopecontent", "arrangement", "userestrict"):
                res = tree.xpath(f"//e:archdesc/e:{tag}", namespaces={"e": tree.nsmap[None]})
                self.assertEqual(1, len(res))

            accessrestricts = tree.xpath(
                "//e:archdesc/e:accessrestrict", namespaces={"e": tree.nsmap[None]}
            )
            self.assertEqual(2, len(accessrestricts))

    def test_ape_ead_archdesc_tags_2(self):
        """Test legalstatus display of FAComponent.

        Trying: import in IR
        Expecting: exptected attributes are found in ape_ead <accessrestrict>

        """
        with self.admin_access.cnx() as cnx:
            cnx.create_entity(
                "Service",
                code="FRAD040",
                category="L",
            )
            cnx.commit()
            filepath = "ir_data/FRANMT_IR_1996_94.xml"
            self.import_filepath(cnx, filepath)
            fi = cnx.find("FindingAid").one()
            ape_ead_file = fi.ape_ead_file[0]
            content = ape_ead_file.data.read()
            tree = etree.fromstring(content)
            for tag in (
                "custodhist",
                "arrangement",
                "scopecontent",
                "phystech",
                "bioghist",
                "acqinfo",
                "userestrict",
                "langmaterial",
                "originalsloc",
                "relatedmaterial",
                "bibliography",
                "controlaccess",
            ):
                res = tree.xpath(f"//e:archdesc/e:{tag}", namespaces={"e": tree.nsmap[None]})
                if tag in ("userestrict",):
                    self.assertEqual(2, len(res))
                else:
                    self.assertEqual(1, len(res))

            accessrestricts = tree.xpath(
                "//e:archdesc/e:accessrestrict", namespaces={"e": tree.nsmap[None]}
            )
            self.assertEqual(3, len(accessrestricts))

    def test_ape_ead_accessrestrict(self):
        """Test multiples accessrestrict of FindingAid.

        Trying: import in IR with multiple accessrestrict
        Expecting: all accessrestricts are present in ape_ead

        """
        with self.admin_access.cnx() as cnx:
            cnx.commit()
            filepath = "ir_data/FRANMT_IR_1996_94.xml"
            self.import_filepath(cnx, filepath)
            fi = cnx.find("FindingAid").one()
            ape_ead_file = fi.ape_ead_file[0]
            content = ape_ead_file.data.read()
            tree = etree.fromstring(content)
            nodes = tree.xpath("//e:archdesc/e:accessrestrict", namespaces={"e": tree.nsmap[None]})
            for accessrestrict in tree.xpath(
                "//e:archdesc/e:accessrestrict", namespaces={"e": tree.nsmap[None]}
            ):
                p = accessrestrict.xpath("e:p", namespaces={"e": tree.nsmap[None]})
                self.assertTrue(
                    any(
                        p[0].text.startswith(word)
                        for word in ("Archives", "Microfilms", "Publiable")
                    )
                )
            self.assertEqual(3, len(nodes))

    def test_index_authorities(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRAC95300_1DHP_rpnum_001.xml")
            fa = cnx.find("FindingAid").one()
            for itype in ("persname", "corpname", "name", "famname", "geogname"):
                agents = list(fa.main_indexes(itype).entities())
                self.assertEqual(len(agents), 0)

    def test_import_findingaid_bioghist(self):
        with self.admin_access.cnx() as cnx:
            filepath = "ir_data/FRMAEE/FRMAEE_0001MA030.xml"
            self.import_filepath(cnx, filepath)
            fa = cnx.find("FindingAid").one()
            expected = "Rabat le 28 mai 1947"
            self.assertIn(expected, fa.bioghist)

    def test_import_findingaid_fa_support(self):
        """
        Trying: import a XML file
        Expecting: findingaid_support exists
        """
        with self.admin_access.cnx() as cnx:
            filepath = "ir_data/FRMAEE/FRMAEE_0001MA030.xml"
            self.import_filepath(cnx, filepath)
            fa = cnx.find("FindingAid").one()
            fa_support_filepath = cnx.execute(
                "Any FSPATH(D) WHERE X findingaid_support F, F data D, X eid %(x)s", {"x": fa.eid}
            )[0][0].getvalue()
            self.assertEqual(fa_support_filepath, self.imported_filepath.encode("utf-8"))
            self.assertTrue(self.fileExists(fa_support_filepath))

    def test_findingaid_support_hash_import_ead(self):
        """
        Trying: import a XML file
        Expecting: findingaid_support data_hash is correctly set
        """
        with self.admin_access.cnx() as cnx:
            filepath = "ir_data/FRMAEE/FRMAEE_0001MA030.xml"
            self.import_filepath(cnx, filepath)
            fa_support = cnx.execute("Any X WHERE F findingaid_support X").one()
            expected = "da645ebf68b20274d25dae40d9109dba0bd42f4c"
            self.assertEqual(expected, fa_support.data_hash)
            self.assertEqual(fa_support.data_hash, fa_support.compute_hash())
            self.assertTrue(fa_support.check_hash())

    def test_import_findingaid_referenced_files(self):
        with self.admin_access.cnx() as cnx:
            filepath = "ir_data/FRMAEE/FRMAEE_0001MA030.xml"
            self.import_filepath(cnx, filepath)
            fa = cnx.find("FindingAid").one()
            sha1_maroc = "c7e79ea17f70586cb16c723b06832a7d9154fa20"
            maroc = "{}/FRMAEE_MN_179CPCOM_Maroc.pdf".format(sha1_maroc)
            sha1_61 = "05651f43e045d343c3d220950b7b060978e3c322"
            f61 = "{}/9BIP_1914-1961.pdf".format(sha1_61)
            f1, f2, f3, f4 = fa.fa_referenced_files
            self.assertCountEqual(
                [f.data_hash for f in fa.fa_referenced_files], [sha1_maroc] * 3 + [sha1_61]
            )
            for fsha1 in [maroc, f61]:
                expected = '<a href="../file/{}"'.format(fsha1)
                self.assertIn(expected, fa.additional_resources)
            fac = cnx.find("FAComponent").one()
            sha1_91 = "e5d25c18f08e3e4a0d15d360dc2b7bfad86832d9"
            f91 = "{}/FRMAEE_1BIP_1919-1994.pdf".format(sha1_91)
            self.assertCountEqual(
                [f.data_hash for f in fac.fa_referenced_files], [sha1_91, sha1_maroc, sha1_61]
            )
            for fsha1 in [f91]:
                expected = '<a href="../file/{}"'.format(f91)
                self.assertIn(expected, fac.additional_resources)
            self.assertEqual(cnx.find("File").rowcount, 9)
            for fpath in cnx.execute(
                f"""Any {self.fkeyfunc}(D) WHERE X fa_referenced_files F, F data D"""
            ):
                self.assertTrue(self.fileExists(fpath[0].getvalue()))

    def test_import_relfiles(self):
        with self.admin_access.cnx() as cnx:
            self.assertFalse(cnx.execute("Any X WHERE X is File"))
            filepath = "ir_data/FRMAEE/FRMAEE_0001MA030.xml"
            self.import_filepath(cnx, filepath)
            filepath = "ir_data/FRMAEE/RELFILES/FRMAEE_1BIP_1919-1994.pdf"
            self.import_filepath(cnx, filepath)
            self.assertEqual(len(cnx.find("FindingAid")), 1)
            self.assertEqual(len(cnx.find("FAComponent")), 1)

    def test_import_relfiles_symlink(self):
        with self.admin_access.cnx() as cnx:
            filepath = "ir_data/FRMAEE/FRMAEE_0001MA030.xml"
            self.import_filepath(cnx, filepath)
            rset = cnx.execute(
                """Any S, FSPATH(D) LIMIT 1 WHERE F data_hash S,
                   X fa_referenced_files F, F data D,
                   F data_name 'FRMAEE_MN_179CPCOM_Maroc.pdf'"""
            )
            data_sha1hex = rset[0][0]
            pdfpath = rset[0][1].getvalue()
            self.assertTrue(self.fileExists(self.get_filepath_by_storage(filepath)))
            # old symlinks
            if self.s3_bucket_name:
                destpath = self.get_filepath_by_storage(
                    f"{data_sha1hex}_{osp.basename(pdfpath).decode('utf-8')}"
                )
            else:
                destpath = self.get_filepath_by_storage(
                    f"{self.config['appfiles-dir']}/{data_sha1hex}_{osp.basename(pdfpath).decode('utf-8')}"  # noqa
                )
            self.assertNotEqual(destpath.encode("utf-8"), pdfpath)
            self.assertTrue(self.fileExists(destpath))
            if not self.s3_bucket_name:
                self.assertTrue(osp.islink(destpath))

    def _test_files(self, cnx, fdata, deleted=False):
        for data_sha1hex, fpath in fdata:
            self.assertTrue(self.fileExists(fpath))
            self.assertTrue(self.fileExists(self.get_filepath_by_storage(fpath)))
            # test symlinks
            if self.s3_bucket_name:
                destpath = self.get_filepath_by_storage(f"{data_sha1hex}_{osp.basename(fpath)}")
                if deleted:
                    self.assertFalse(self.fileExists(destpath))
                else:
                    self.assertTrue(self.fileExists(destpath))
            else:
                destpath = self.get_filepath_by_storage(
                    f"{self.config['appfiles-dir']}/{data_sha1hex}_{osp.basename(fpath)}"  # noqa
                )
                # not implement yet
                self.assertTrue(self.fileExists(destpath))

    def test_delete_findingaid_referenced_files(self):
        """
        Trying: create a findingaid with referenced files and pdf and delete it
        Expecting: all files are removed
        """
        with self.admin_access.cnx() as cnx:
            filepath = "ir_data/FRMAEE/FRMAEE_0001MA030.xml"
            self.import_filepath(cnx, filepath)
            fa = cnx.find("FindingAid").one()
            sha1_maroc = "c7e79ea17f70586cb16c723b06832a7d9154fa20"
            maroc = "{}/FRMAEE_MN_179CPCOM_Maroc.pdf".format(sha1_maroc)
            sha1_61 = "05651f43e045d343c3d220950b7b060978e3c322"
            f61 = "{}/9BIP_1914-1961.pdf".format(sha1_61)
            f1, f2, f3, f4 = fa.fa_referenced_files
            self.assertCountEqual(
                [f.data_hash for f in fa.fa_referenced_files], [sha1_maroc] * 3 + [sha1_61]
            )
            for fsha1 in [maroc, f61]:
                expected = '<a href="../file/{}"'.format(fsha1)
                self.assertIn(expected, fa.additional_resources)
            fac = cnx.find("FAComponent").one()
            sha1_91 = "e5d25c18f08e3e4a0d15d360dc2b7bfad86832d9"
            f91 = "{}/FRMAEE_1BIP_1919-1994.pdf".format(sha1_91)
            self.assertCountEqual(
                [f.data_hash for f in fac.fa_referenced_files], [sha1_91, sha1_maroc, sha1_61]
            )
            for fsha1 in [f91]:
                expected = '<a href="../file/{}"'.format(f91)
                self.assertIn(expected, fac.additional_resources)
            self.assertEqual(cnx.find("File").rowcount, 9)
            fdata = [
                (h, f.getvalue().decode("utf-8"))
                for h, f in cnx.execute(
                    f"""DISTINCT Any S, {self.fkeyfunc}(D) WHERE X fa_referenced_files F,
                        F data D, F data_hash S"""
                )
            ]
            self._test_files(cnx, fdata)
            delete_from_filename(
                cnx, fa.stable_id, is_filename=False, interactive=False, esonly=False
            )
            cnx.commit()
            self.assertFalse(cnx.find("FindingAid"))
            self._test_files(cnx, fdata, deleted=True)

    def test_import_pdffiles(self):
        with self.admin_access.cnx() as cnx:
            self.assertFalse(cnx.execute("Any X WHERE X is File"))
            filepath = "ir_data/FRMAEE/FRMAEE_0001MA030.xml"
            self.import_filepath(cnx, filepath)
            filepath = "ir_data/FRMAEE/PDF/FRMAEE_1BIP_1919-1994.pdf"
            self.import_filepath(cnx, filepath)
            self.assertEqual(len(cnx.find("FindingAid")), 2)
            self.assertEqual(len(cnx.find("FAComponent")), 1)

    def test_import_pdffiles_symlink(self):
        """test that the symlink to the appfiles-dir is set for the pdf file"""
        with self.admin_access.cnx() as cnx:
            filepath = "ir_data/FRMAEE/PDF/FRMAEE_1BIP_1919-1994.pdf"
            self.import_filepath(cnx, filepath)
            pdffile = cnx.execute("Any F WHERE X findingaid_support F").one()
            self.assertEqual(pdffile.data_hash, pdffile.compute_hash())
            self.assertTrue(pdffile.check_hash())
            self.assertTrue(self.fileExists(self.get_filepath_by_storage(filepath)))
            if self.s3_bucket_name:
                destpath = self.get_filepath_by_storage(
                    f"{pdffile.data_hash}_{osp.basename(filepath)}"
                )
            else:
                destpath = self.get_filepath_by_storage(
                    f"{self.config['appfiles-dir']}/{pdffile.data_hash}_{osp.basename(filepath)}"
                )
            self.assertNotEqual(destpath, filepath)
            self.assertTrue(self.fileExists(destpath))
            if not self.s3_bucket_name:
                self.assertTrue(osp.islink(destpath))

    def test_delete_s3_pdffiles_symlink(self):
        """
        Trying: create a findingaid from PDF and delete it
        Expecting: Pdf file is no more accessible
        """
        if not self.s3_bucket_name:
            from pytest import skip

            skip("Not implemented for BFSS storage")
        with self.admin_access.cnx() as cnx:
            filepath = "ir_data/FRMAEE/PDF/FRMAEE_1BIP_1919-1994.pdf"
            self.import_filepath(cnx, filepath)
            fa = cnx.find("FindingAid").one()
            pdffile = cnx.execute("Any F WHERE X findingaid_support F").one()
            destpath = self.get_filepath_by_storage(f"{pdffile.data_hash}_{osp.basename(filepath)}")
            self.assertTrue(self.fileExists(destpath))
            delete_from_filename(
                cnx, fa.stable_id, is_filename=False, interactive=False, esonly=False
            )
            cnx.commit()
            self.assertFalse(self.fileExists(destpath))

    def test_imported_authority_in_es_docs(self):
        """Test that index_entires are correcty set in esdoc for imported PDFs"""
        with self.admin_access.cnx() as cnx:
            cnx.create_entity("Service", code="FRANMT", category="foo")
            cnx.create_entity("LocationAuthority", label="Dunkerque (Nord, France)")
            cnx.commit()
            filepath = "ir_data/FRANMT/PDF/FRANMT_3_AQ_INV.pdf"
            es_docs = self.import_filepath(cnx, filepath)
            self.assertEqual(1, len(cnx.find("FindingAid")))
            for es_doc in es_docs:
                self.assertIn("index_entries", list(es_doc["_source"].keys()))
                for index_entry in es_doc["_source"]["index_entries"]:
                    self.assertIn("authority", index_entry)
                    self.assertIn("role", index_entry)

    def test_creation_date_in_es_docs(self):
        """Test integrating new creation_date attribute in ElasticSearch index.

        Trying: importing new FindingAid
        Expecting: FindingAid and FAComponent have creation_date attribute
        """
        with self.admin_access.cnx() as cnx:
            fa_es_doc, comp_es_doc = self.import_filepath(cnx, "FRAN_IR_0261167_excerpt.xml")
            fa = cnx.find(eid=fa_es_doc["_source"]["eid"], etype="FindingAid").one()
            self.assertEqual(
                format_date(fa.creation_date), format_date(fa_es_doc["_source"]["creation_date"])
            )
            facomp = cnx.find(eid=comp_es_doc["_source"]["eid"], etype="FAComponent").one()
            self.assertEqual(
                format_date(facomp.creation_date),
                format_date(comp_es_doc["_source"]["creation_date"]),
            )

    def test_findingaid_stable_id(self):
        """Import a FindingAid with prefix
        Trying: import a FindingAid
        Expecting: this stable_id is the one expected
        """
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "ir_data/FRAN_IR_000061.xml")
            self.assertEqual(
                cnx.execute("Any N WHERE X findingaid_support F, F data_name N")[0][0],
                "FRAN_IR_000061.xml",
            )
            self.assertEqual(
                cnx.execute("Any S WHERE X is FindingAid, X stable_id S")[0][0],
                "549fb7cbf0e1115ee00c488d1ab0e11ff771f3dc",
            )

    def test_AN_sortdate(self):
        """Test for sortdate index
        Trying: import and reimport a FindingAid
        Expecting: an FAComponent with len(did.startyear) < 4  has no es["sortdate"]
        """
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "ir_data/FRAN_IR_000061.xml")
            fc = cnx.execute(
                "Any F WHERE F is FAComponent, F stable_id %(f)s",
                {"f": "3d9ba1d8864018be11e1aedfe32073186c655d30"},
            ).one()
            self.assertEqual(fc.did[0].startyear, 149)
            doc = fc.cw_adapt_to("IFullTextIndexSerializable").serialize()
            self.assertEqual(doc["sortdate"], None)


class EADReImportTC(EADImportMixin, PostgresTextMixin, CubicWebTC):
    @classmethod
    def init_config(cls, config):
        super(EADReImportTC, cls).init_config(config)
        config.set_option("instance-type", "consultation")

    readerconfig = merge_dicts(
        {}, EADImporterTC.readerconfig, {"reimport": True, "nodrop": False, "force_delete": True}
    )

    def setup_database(self):
        super(EADReImportTC, self).setup_database()
        with self.admin_access.cnx() as cnx:
            cnx.create_entity(
                "Service",
                category="?",
                name="Les Archives Nationales",
                short_name="Les AN",
                code="fran",
            )
            cnx.commit()

    def test_index_reimport(self):
        with self.admin_access.cnx() as cnx:
            fpath = "FRAN_IR_050263.xml"
            self.import_filepath(cnx, fpath)
            hugo = cnx.execute(
                "Any X WHERE X is AgentAuthority, X label %(l)s", {"l": "Hugo, Victor"}
            ).one()
            self.assertEqual(len(hugo.reverse_authority[0].index), 1)
            # reimport the same file
            self.import_filepath(cnx, fpath)
            # we shell have only one AgentAuthority for Hugo, Victor
            new_hugo = cnx.execute(
                "Any X WHERE X is AgentAuthority, X label %(l)s", {"l": "Hugo, Victor"}
            ).one()
            self.assertEqual(hugo.eid, new_hugo.eid)

    def test_files_after_reimport(self):
        """reimport a version of FRMAEE_0001MA030.xml without
        `fa_references_files` and check that old files are deleted"""
        with self.admin_access.cnx() as cnx:
            self.assertFalse(cnx.find("File").rowcount)
            filepath = "ir_data/FRMAEE/FRMAEE_0001MA030.xml"
            self.import_filepath(cnx, filepath)
            fa = cnx.find("FindingAid").one()
            self.assertEqual(
                [f.data_name for f in fa.fa_referenced_files],
                ["9BIP_1914-1961.pdf"] + ["FRMAEE_MN_179CPCOM_Maroc.pdf"] * 3,
            )
            fac = cnx.find("FAComponent").one()
            self.assertCountEqual(
                [f.data_name for f in fac.fa_referenced_files],
                ["FRMAEE_1BIP_1919-1994.pdf", "9BIP_1914-1961.pdf", "FRMAEE_MN_179CPCOM_Maroc.pdf"],
            )
            deleted_files = dict(
                (f[0], f[1].getvalue())
                for f in cnx.execute("Any F, FSPATH(D) WHERE X fa_referenced_files F,  F data D")
            )
            # ead.xml, ape.xml + 4 fa pdf + 3 fac pdf
            self.assertEqual(cnx.find("File").rowcount, 9)
            # reimport a new version
            filepath = "ir_data/FRMAEE_v2/FRMAEE_0001MA030.xml"
            self.import_filepath(cnx, filepath)
            fa = cnx.find("FindingAid").one()
            self.assertFalse(fa.fa_referenced_files)
            fac = cnx.find("FAComponent").one()
            self.assertEqual(
                [f.data_name for f in fac.fa_referenced_files],
                ["FRMAEE_1BIP_1919-1994.pdf", "FRMAEE_MN_179CPCOM_Maroc.pdf"],
            )
            # ead.xml, ape.xml + 0 fa pdf + 2 fac pdf
            self.assertEqual(cnx.find("File").rowcount, 4)
            for eid, path in list(deleted_files.items()):
                self.assertTrue(self.fileExists(path))
                # but not in db
                with self.assertRaises(NoResultError):
                    cnx.find("File", eid=eid).one()

    def test_reimport_findingaid_referenced_files(self):
        with self.admin_access.cnx() as cnx:
            self.assertFalse(cnx.execute("Any X WHERE X is File"))
            filepath = "ir_data/FRMAEE/FRMAEE_0001MA030.xml"
            self.import_filepath(cnx, filepath)
            fa = cnx.find("FindingAid").one()
            fa_support = fa.findingaid_support[0]
            fa_ead = fa.ape_ead_file[0]
            f1, f2, f3, f4 = fa.fa_referenced_files
            fac = cnx.find("FAComponent").one()
            self.assertEqual(len(fac.fa_referenced_files), 3)
            # reimport the same file
            self.import_filepath(cnx, filepath)
            new_fa = cnx.find("FindingAid").one()
            self.assertEqual(len(new_fa.fa_referenced_files), 4)
            self.assertEqual(cnx.execute("Any COUNT(X) WHERE X is File")[0][0], 9)
            self.assertNotEqual(fa.eid, new_fa.eid)
            # enshure old files are deleted:
            for eid in (fa_support.eid, fa_ead.eid, f1.eid, f2.eid, f3.eid, f4.eid):
                with self.assertRaises(NoResultError):
                    cnx.find("File", eid=eid).one()

    def test_reimport_fa_referenced_symlinks(self):
        """
        Trying: import and reimport a FindingAid with referenced_files
        Expecting: symlinks to the appfiles-dir are set for referenced files and still
        present after reimport
        """
        with self.admin_access.cnx() as cnx:
            filepath = "ir_data/FRMAEE/FRMAEE_0001MA030.xml"
            self.import_filepath(cnx, filepath)
            # reimport the same file
            self.import_filepath(cnx, filepath)
            rset = cnx.execute(
                """Any S, FSPATH(D) LIMIT 1 WHERE F data_hash S,
                   X fa_referenced_files F, F data D,
                   F data_name 'FRMAEE_MN_179CPCOM_Maroc.pdf'"""
            )
            data_sha1hex = rset[0][0]
            pdfpath = rset[0][1].getvalue()
            self.assertTrue(self.fileExists(self.get_filepath_by_storage(filepath)))
            # old symlinks
            if self.s3_bucket_name:
                destpath = self.get_filepath_by_storage(
                    f"{data_sha1hex}_{osp.basename(pdfpath).decode('utf-8')}"
                )
            else:
                destpath = self.get_filepath_by_storage(
                    f"{self.config['appfiles-dir']}/{data_sha1hex}_{osp.basename(pdfpath).decode('utf-8')}"  # noqa
                )
            self.assertNotEqual(destpath.encode("utf-8"), pdfpath)
            # ensure the original pdf still exists
            self.assertTrue(self.fileExists(destpath))
            if not self.s3_bucket_name:
                self.assertTrue(osp.islink(destpath))

    def test_reimport_pdffile_symlinks(self):
        """
        Trying: import and reimport a FindingAid from a Pdf
        Expecting: symlink to the appfiles-dir is set for the pdf file and still
        present after reimport
        """
        with self.admin_access.cnx() as cnx:
            filepath = "ir_data/FRMAEE/PDF/FRMAEE_1BIP_1919-1994.pdf"
            self.import_filepath(cnx, filepath)
            pdffile = cnx.execute("Any F WHERE X findingaid_support F").one()
            self.assertTrue(self.fileExists(self.get_filepath_by_storage(filepath)))
            if self.s3_bucket_name:
                destpath = self.get_filepath_by_storage(
                    f"{pdffile.data_hash}_{osp.basename(filepath)}"
                )
            else:
                destpath = self.get_filepath_by_storage(
                    f"{self.config['appfiles-dir']}/{pdffile.data_hash}_{osp.basename(filepath)}"
                )
            self.assertTrue(self.fileExists(destpath))
            if not self.s3_bucket_name:
                self.assertTrue(osp.islink(destpath))
            # reimport the same file
            self.import_filepath(cnx, filepath)
            self.assertTrue(self.fileExists(self.get_filepath_by_storage(filepath)))
            # ensure the original pdf still exists
            self.assertTrue(self.fileExists(destpath))
            if not self.s3_bucket_name:
                self.assertTrue(osp.islink(destpath))

    def test_failed_reimport(self):
        """tests that a previously imported FindingAid is not deleted after a failed
        reimport"""
        with self.admin_access.cnx() as cnx:
            filepath = "ir_data/FRMAEE_OK/FRMAEE_0001MA001.xml"
            self.import_filepath(cnx, filepath)
            fa = cnx.find("FindingAid").one()
            filepath = "ir_data/FRMAEE_KO/FRMAEE_0001MA001.xml"
            # ensure the second file has errors
            with self.assertRaises(Exception):
                etree.parse(filepath)
            # import the erroneous file
            self.import_filepath(cnx, filepath)
            # the previously imported FindingAid is still there
            self.assertEqual(fa.eid, cnx.find("FindingAid").one().eid)

    def test_reimport_ir_with_different_filename(self):
        """
        Trying: import and reimport IR with same eadid but different filenames
        Expecting: Only one FindingAid is created
        """
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "ir_data/FRANOM_01250_excerpt.xml")
            self.assertEqual(1, cnx.execute("Any COUNT(X) WHERE X is FindingAid")[0][0])
            fi = cnx.find("FindingAid", eadid="FRANOM_01250").one()
            stable_id = fi.stable_id
            modification_date = fi.modification_date
            # reimport an IR with eadid == FRANOM_01250
            for fpath in ("ir_data/Franom_01250.xml", "ir_data/FRANOM_01250_excerpt.xml"):
                self.import_filepath(cnx, fpath)
                self.assertEqual(1, cnx.execute("Any COUNT(X) WHERE X is FindingAid")[0][0])
                fi = cnx.find("FindingAid", eadid="FRANOM_01250").one()
                self.assertEqual(stable_id, fi.stable_id)
                self.assertNotEqual(modification_date, fi.modification_date)
                modification_date = fi.modification_date
            # reimport an IR with eadid == franom_01250
            self.import_filepath(cnx, "ir_data/franom_01250_test.xml")
            self.assertEqual(1, cnx.execute("Any COUNT(X) WHERE X is FindingAid")[0][0])
            fi = cnx.find("FindingAid", eadid="franom_01250").one()
            self.assertEqual(stable_id, fi.stable_id)
            self.assertNotEqual(modification_date, fi.modification_date)
            self.assertFalse(cnx.find("FindingAid", eadid="FRANOM_01250"))
            modification_date = fi.modification_date
            # reimport an IR with eadid == FRANOM_01250
            self.import_filepath(cnx, "ir_data/Franom_01250.xml")
            self.assertEqual(1, cnx.execute("Any COUNT(X) WHERE X is FindingAid")[0][0])
            fi = cnx.find("FindingAid", eadid="FRANOM_01250").one()
            self.assertEqual(stable_id, fi.stable_id)
            self.assertNotEqual(modification_date, fi.modification_date)
            self.assertFalse(cnx.find("FindingAid", eadid="franom_01250"))
            # check fa_redirects table
            self.assertCountEqual(
                [
                    ("franom_01250", "2cd1385685ef4eea4d8b8168085cddba9b63281b", stable_id),
                    ("FRANOM_01250", "b4508d9b609e96573486fcf740cd0b0764e219ea", stable_id),
                ],
                get_fa_redirects(cnx),
            )


class EADFullMigrationTC(EADImportMixin, PostgresTextMixin, CubicWebTC):
    """tests for full data reimport"""

    @classmethod
    def init_config(cls, config):
        super(EADFullMigrationTC, cls).init_config(config)
        config.set_option("instance-type", "consultation")

    readerconfig = merge_dicts(
        {},
        EADImporterTC.readerconfig,
        {
            "autodedupe_authorities": "global/normalize",
            "esonly": 0,
            "force_delete": False,
            "index-name": "cms",
            "nodrop": 0,
            "noes": True,
        },
    )

    def test_authorities(self):
        with self.admin_access.cnx() as cnx:
            cnx.create_entity(
                "Service",
                category="?",
                name="Les Archives Nationales",
                short_name="Les AN",
                code="fran",
            )
            cnx.commit()
            fpath = "FRAN_IR_050263.xml"
            self.import_filepath(cnx, fpath)
            authority_eids = cnx.execute(
                "Any X WHERE X is IN (AgentAuthority, " "SubjectAuthority, LocationAuthority)"
            ).rows
            index_rql = "Any X WHERE X index Y"
            self.assertEqual(73, cnx.execute(index_rql).rowcount)
            delete_from_filename(cnx, fpath, interactive=False, esonly=False)

            cnx.commit()
            self.assertEqual(0, cnx.execute(index_rql).rowcount)
            self.import_filepath(cnx, fpath)
            self.assertEqual(73, cnx.execute(index_rql).rowcount)
            # we shell still have the same authorities
            new_authority_eids = cnx.execute(
                "Any X WHERE X is IN (AgentAuthority, " "SubjectAuthority, LocationAuthority)"
            ).rows
            self.assertCountEqual(new_authority_eids, authority_eids)


class ESOnlyTests(S3BfssStorageTestMixin, PostgresTextMixin, CubicWebTC):
    @property
    def readerconfig(self):
        return {
            "esonly": True,
            "index-name": "dummy",
            "appid": "data",
            "appfiles-dir": self.datapath(),
        }

    def setup_database(self):
        # add FindingAId / FAcomponent matching stable ids of
        # FRAN_IR_0261167_excerpt.xml
        with self.admin_access.cnx() as cnx:
            did1 = cnx.create_entity("Did", unitid="did1", unittitle="title1")
            fa = cnx.create_entity(
                "FindingAid",
                name="fa",
                eadid="fa",
                stable_id="c4b17d67cb5e8e884590ab98a864c81d48239053",
                publisher="FRAN",
                fa_header=cnx.create_entity("FAHeader"),
                did=did1,
            )
            did2 = cnx.create_entity("Did", unitid="did2", unittitle="title2")
            comp = cnx.create_entity(
                "FAComponent",
                stable_id="7a4b5ef85c8014a08654e3c741a337ffdee60b4f",
                did=did2,
                finding_aid=fa,
            )
            cnx.commit()
            self.fa_eid = fa.eid
            self.comp_eid = comp.eid

    def import_filepath(self, cnx, filepath):
        store = RQLObjectStore(cnx)
        r = ead.Reader(self.readerconfig, store)
        services_map = load_services_map(cnx)
        filepath = self.get_or_create_imported_filepath(filepath)
        service_infos = service_infos_from_filepath(filepath, services_map)
        return r.import_filepath(filepath, service_infos)

    def test_esonly_indexation(self):
        with self.admin_access.cnx() as cnx:
            es_docs = self.import_filepath(cnx, "FRAN_IR_0261167_excerpt.xml")
            self.assertEqual(len(es_docs), 2)
            fa_es_doc, comp_es_doc = es_docs
            self.assertEqual(fa_es_doc["_id"], "c4b17d67cb5e8e884590ab98a864c81d48239053")
            self.assertEqual(fa_es_doc["_source"]["eid"], self.fa_eid)
            self.assertEqual(comp_es_doc["_id"], "7a4b5ef85c8014a08654e3c741a337ffdee60b4f")
            self.assertEqual(comp_es_doc["_source"]["eid"], self.comp_eid)

    def test_html_strip(self):
        with self.admin_access.cnx() as cnx:
            es_docs = self.import_filepath(cnx, "FRAN_IR_0261167_excerpt.xml")
            self.assertEqual(len(es_docs), 2)
            fa_es_doc, comp_es_doc = es_docs
            self.assertEqual(comp_es_doc["_id"], "7a4b5ef85c8014a08654e3c741a337ffdee60b4f")
            self.assertEqual(comp_es_doc["_source"]["description"], "Coucou tout le monde")

    def test_authority_in_es_index_docs(self):
        with self.admin_access.cnx() as cnx:
            es_docs = self.import_filepath(cnx, "FRAN_IR_0261167_excerpt.xml")
            self.assertEqual(len(es_docs), 2)
            fa_es_doc, comp_es_doc = es_docs
            self.assertIsNone(
                [
                    i
                    for i in fa_es_doc["_source"]["index_entries"]
                    if i["label"] == "Direction de l'eau"
                ][0]["authority"]
            )

    def test_authority_quality(self):
        """
        Trying: import IR and create authorities
        Expecting: authorities are not aligned and not qualified
        """
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRAN_IR_0261167_excerpt.xml")
            for cw_etype in ("SubjectAuthority", "AgentAuthority", "LocationAuthority"):
                for auth in cnx.find(cw_etype):
                    self.assertFalse(auth.same_as)
                    self.assertFalse(auth.quality)

    def test_originators_in_facomp_docs(self):
        with self.admin_access.cnx() as cnx:
            es_docs = self.import_filepath(cnx, "FRAN_IR_0261167_excerpt.xml")
            self.assertEqual(len(es_docs), 2)
            fa_es_doc, comp_es_doc = es_docs
            self.assertEqual(fa_es_doc["_source"]["originators"], ["Direction de l'eau"])
            self.assertEqual(comp_es_doc["_source"]["originators"], ["Direction de l'eau"])

    def test_dates_in_es_docs(self):
        with self.admin_access.cnx() as cnx:
            es_docs = self.import_filepath(cnx, "FRAN_IR_0261167_excerpt.xml")
            self.assertEqual(len(es_docs), 2)
            fa_es_doc, comp_es_doc = es_docs
            startyear, stopyear = 1922, 2001
            self.assertEqual(fa_es_doc["_source"]["year"], startyear)
            self.assertEqual(fa_es_doc["_source"]["startyear"], startyear)
            self.assertEqual(fa_es_doc["_source"]["stopyear"], 2001)
            self.assertEqual(fa_es_doc["_source"]["sortdate"], "{}-01-01".format(startyear))
            self.assertEqual(fa_es_doc["_source"]["dates"], {"gte": startyear, "lte": stopyear})


class ReimportESonlyTests(EADImportMixin, PostgresTextMixin, CubicWebTC):
    readerconfig = merge_dicts({}, EADImportMixin.readerconfig, {"esonly": True})

    def test_authority_in_es_index_docs(self):
        with self.admin_access.cnx() as cnx:
            self.readerconfig = dict(self.readerconfig, esonly=False)
            es_docs = self.import_filepath(cnx, "FRAN_IR_0261167_excerpt.xml")
            self.readerconfig = dict(self.readerconfig, esonly=True)
            firstaa = cnx.find("AgentAuthority", label="Direction de l'eau").one()
        with self.admin_access.cnx() as cnx:
            es_docs = self.import_filepath(cnx, "FRAN_IR_0261167_excerpt.xml")
            secondaa = cnx.find("AgentAuthority", label="Direction de l'eau").one()
            # eid should not have changed since we import in `nodrop` mode
            self.assertEqual(firstaa.eid, secondaa.eid)
            self.assertEqual(len(es_docs), 2)
            fa_es_doc, comp_es_doc = es_docs
            # esdoc should have a key `authority' which value is AgentAuthority eid
            self.assertEqual(
                secondaa.eid,
                [
                    i
                    for i in fa_es_doc["_source"]["index_entries"]
                    if i["label"] == "Direction de l'eau"
                ][0]["authority"],
            )

    def test_es_attributes(self):
        with self.admin_access.cnx() as cnx:
            self.readerconfig = dict(self.readerconfig, esonly=False)
            fa_docs, comp_docs = self.import_filepath(cnx, "FRAN_IR_0261167_excerpt.xml")
            service = fa_docs["_source"].pop("service")
            self.assertEqual(set(service.keys()), {"code", "eid", "level", "title"})
            self.assertEqual(
                set(fa_docs["_source"].keys()),
                {
                    "name",
                    "eadid",
                    "fatype",
                    "description",
                    "acquisition_info",
                    "index_entries",
                    "stable_id",
                    "publisher",
                    "scopecontent",
                    "originators",
                    "cw_etype",
                    "titleproper",
                    "author",
                    "fa_stable_id",
                    "did",
                    "eid",
                    "year",
                    "dates",
                    "stopyear",
                    "startyear",
                    "sortdate",
                    "escategory",
                    "digitized",
                    "creation_date",
                },
            )
            service = comp_docs["_source"].pop("service")
            self.assertEqual(set(service.keys()), {"code", "eid", "level", "title"})
            self.assertEqual(
                set(comp_docs["_source"].keys()),
                {
                    "name",
                    "eadid",
                    "fatype",
                    "stable_id",
                    "description",
                    "acquisition_info",
                    "scopecontent",
                    "did",
                    "year",
                    "dates",
                    "stopyear",
                    "startyear",
                    "sortdate",
                    "publisher",
                    "digitized",
                    "index_entries",
                    "originators",
                    "fa_stable_id",
                    "cw_etype",
                    "eid",
                    "escategory",
                    "creation_date",
                },
            )


class EADReImportTTC(EADImportMixin, PostgresTextMixin, CubicWebTC):
    readerconfig = merge_dicts({}, EADImportMixin.readerconfig, {"nodrop": False})

    @classmethod
    def init_config(cls, config):
        super(EADReImportTTC, cls).init_config(config)
        config.set_option("instance-type", "consultation")

    def test_reimport_ead(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "ir_data/v1/FRAD095_00374.xml")
            c1, c11, c12 = cnx.execute(
                "Any C ORDERBY I " "WHERE C is FAComponent, C did D, D unitid I"
            ).entities()
            self.assertEqual(len(c1.digitized_versions), 0)
            self.assertCountEqual(
                [dv.illustration_url for dv in c11.digitized_versions], ["foo.jpg", "bar.jpg"]
            )
            self.assertCountEqual(
                [dv.illustration_url for dv in c12.digitized_versions], ["bim.jpg", "bam.jpg"]
            )
            cnx.commit()
            delete_from_filename(cnx, "FRAD095_00374.xml", interactive=False, esonly=False)
            self.import_filepath(cnx, "ir_data/v2/FRAD095_00374.xml")
            c1new, c11new, c12new, c21new = cnx.execute(
                "Any C ORDERBY I " "WHERE C is FAComponent, C did D, D unitid I"
            ).entities()
            self.assertCountEqual(
                [dv.illustration_url for dv in c11new.digitized_versions], ["foo.jpg"]
            )
            self.assertCountEqual(
                [dv.illustration_url for dv in c12new.digitized_versions],
                ["bim.jpg", "bam.jpg", "boom.jpg"],
            )
            self.assertCountEqual([dv.url for dv in c21new.digitized_versions], ["hello"])

    @patch("cubicweb_francearchives.dataimport.ead.Reader.ignore_filepath")
    def test_config_reimport_esonly(self, ignore_mock):
        """in esonly mode ``ignore_filepath`` method should never be called"""
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRAN_IR_022409.xml", reimport=True, esonly=True)
            self.import_filepath(cnx, "FRAN_IR_022409.xml", reimport=True, esonly=True)
            self.assertFalse(ignore_mock.called)

    def test_config_reimport(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRAN_IR_022409.xml")
            self.import_filepath(cnx, "FRAN_IR_022409.xml", reimport=True)
            rset = cnx.find("FindingAid")
            self.assertEqual(len(rset), 1)

    def test_delete_from_filename(self):
        with self.admin_access.cnx() as cnx:
            self.readerconfig = dict(self.readerconfig, reimport=True, force_delete=True)
            filename = "FRAD085_2C_disparu d'Algérie.xml"
            self.import_filepath(cnx, filename)
            eid = cnx.find("FindingAid").one().eid
            self.import_filepath(cnx, filename)
            self.assertNotEqual(eid, cnx.find("FindingAid").one().eid)

    def test_creation_date_ead_import(self):
        """Test FindingAid, FAComponent creation date is keept between reimports

        Trying: import and reimport a FindingAid
        Expecting: reimported FindingAid and FAComponent have original creation_date
        """
        with self.admin_access.cnx() as cnx:
            filepath = "FRAN_IR_0261167_excerpt.xml"
            fmt = "%a %b %d %H:%M:%S %Y"
            self.readerconfig = dict(self.readerconfig, reimport=True, force_delete=True)
            fa_es_doc, comp_es_doc = self.import_filepath(cnx, filepath)
            creation_date = datetime(1914, 4, 5)
            fa_old = cnx.find("FindingAid").one()
            adapter = fa_old.cw_adapt_to("IFullTextIndexSerializable")
            self.assertEqual(
                format_date(fa_old.creation_date),
                format_date(adapter.serialize()["creation_date"]),
            )
            comp_old = cnx.find("FAComponent").one()
            adapter = comp_old.cw_adapt_to("IFullTextIndexSerializable")
            self.assertEqual(
                format_date(comp_old.creation_date),
                format_date(adapter.serialize()["creation_date"]),
            )
            fa_old.cw_set(creation_date=creation_date)
            comp_old.cw_set(creation_date=creation_date)
            cnx.commit()
            fa_old_date = cnx.find("FindingAid").one().creation_date
            self.assertEqual(
                creation_date.strftime(fmt),
                fa_old_date.strftime(fmt),
            )
            # reimport the file
            fa_es_doc, comp_es_doc = self.import_filepath(cnx, filepath)
            fa = cnx.find("FindingAid").one()
            comp = cnx.find("FAComponent").one()
            self.assertNotEqual(fa_old.eid, fa.eid)
            self.assertNotEqual(comp_old.eid, comp.eid)
            self.assertEqual(fa_old_date, fa.creation_date)
            adapter = fa.cw_adapt_to("IFullTextIndexSerializable")
            self.assertEqual(
                format_date(adapter.serialize()["creation_date"]),
                format_date(fa.creation_date),
            )
            self.assertEqual(fa_old_date, fa.creation_date)
            self.assertEqual(creation_date.strftime(fmt), comp.creation_date.strftime(fmt))
            adapter = comp.cw_adapt_to("IFullTextIndexSerializable")
            self.assertEqual(
                format_date(comp.creation_date), format_date(adapter.serialize()["creation_date"])
            )

    def test_creation_date_pdf_import(self):
        """Test FindingAid creation date is keept between reimports

        Trying: import and reimport a FindingAid
        Expecting: reimported FindingAid has original creation_date
        """
        with self.admin_access.cnx() as cnx:
            filepath = "FRSHD_PUB_00000345_0001.pdf"
            fmt = "%a %b %d %H:%M:%S %Y"
            self.readerconfig = dict(self.readerconfig, reimport=True, force_delete=True)
            self.import_filepath(cnx, filepath)[0]
            fi_old = cnx.find("FindingAid").one()
            adapter = fi_old.cw_adapt_to("IFullTextIndexSerializable")
            self.assertEqual(
                format_date(fi_old.creation_date),
                format_date(adapter.serialize()["creation_date"]),
            )
            creation_date = datetime(1914, 4, 5)
            fi_old.cw_set(creation_date=creation_date)
            cnx.commit()
            self.assertEqual(
                creation_date.strftime(fmt),
                cnx.find("FindingAid").one().creation_date.strftime(fmt),
            )
            self.import_filepath(cnx, filepath)[0]
            fi = cnx.find("FindingAid").one()
            self.assertNotEqual(fi_old.eid, fi.eid)
            self.assertEqual(creation_date.strftime(fmt), fi.creation_date.strftime(fmt))
            adapter = fi.cw_adapt_to("IFullTextIndexSerializable")
            self.assertEqual(
                format_date(fi.creation_date),
                format_date(adapter.serialize()["creation_date"]),
            )


class DeleteTests(EADImportMixin, PostgresTextMixin, CubicWebTC):
    def test_delete_ead_alone(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "ir_data/v1/FRAD095_00374.xml")
            c1, c11, c12 = cnx.execute(
                "Any C ORDERBY I " "WHERE C is FAComponent, C did D, D unitid I"
            ).entities()
            self.assertEqual(len(c1.digitized_versions), 0)
            self.assertCountEqual(
                [dv.illustration_url for dv in c11.digitized_versions], ["foo.jpg", "bar.jpg"]
            )
            self.assertCountEqual(
                [dv.illustration_url for dv in c12.digitized_versions], ["bim.jpg", "bam.jpg"]
            )
            cnx.commit()
            cnx.commit()
            self.assertGreater(len(cnx.find("Geogname")), 0)
            self.assertGreater(len(cnx.find("Subject")), 0)
            self.assertGreater(len(cnx.find("LocationAuthority")), 0)
            self.assertGreater(len(cnx.find("SubjectAuthority")), 0)
            delete_from_filename(cnx, "FRAD095_00374.xml", interactive=False, esonly=False)
            self.assertEqual(len(cnx.find("FindingAid")), 0)
            self.assertEqual(len(cnx.find("FAComponent")), 0)
            self.assertEqual(len(cnx.find("Geogname")), 0)
            self.assertEqual(len(cnx.find("Subject")), 0)
            self.assertEqual(len(cnx.find("DigitizedVersion")), 0)
            self.assertGreater(len(cnx.find("LocationAuthority")), 0)
            self.assertGreater(len(cnx.find("SubjectAuthority")), 0)

    def test_delete_one_ead(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRAN_IR_051016_excerpt.xml")
            initial_fas = [fa.eid for fa in cnx.find("FindingAid").entities()]
            initial_facs = [fac.eid for fac in cnx.find("FAComponent").entities()]
            initial_dvs = [dv.eid for dv in cnx.find("DigitizedVersion").entities()]
            self.import_filepath(cnx, "ir_data/v1/FRAD095_00374.xml")
            self.assertEqual(len(cnx.find("FindingAid")), 2)
            self.assertEqual(len(cnx.find("FAComponent")), len(initial_facs) + 3)
            cnx.commit()
            delete_from_filename(cnx, "FRAD095_00374.xml", interactive=False, esonly=False)
            final_fas = [fa.eid for fa in cnx.find("FindingAid").entities()]
            final_facs = [fac.eid for fac in cnx.find("FAComponent").entities()]
            final_dvs = [dv.eid for dv in cnx.find("DigitizedVersion").entities()]
            self.assertCountEqual(initial_fas, final_fas)
            self.assertCountEqual(initial_facs, final_facs)
            self.assertCountEqual(initial_dvs, final_dvs)


class PushEntitiesTests(PostgresTextMixin, CubicWebTC):
    def test_push_entities(self):
        with self.admin_access.cnx() as cnx:
            initial_nb_cards = len(cnx.find("Card"))
            cursor = cnx.cnxset.cu
            cursor.execute("CREATE TABLE foo(id varchar(16), title varchar(16), do_index boolean)")
            cursor.copy_from(StringIO("c1\tt1\tt\nc2\tt2\tt\n"), "foo")
            cursor.execute(
                "SELECT push_entities('Card', "
                "                     'cw_wikiid, cw_title, cw_do_index', "
                "                     'SELECT id, title, do_index FROM foo')"
            )
            cnx.commit()
            nb_cards = len(cnx.find("Card"))
            self.assertEqual(nb_cards, initial_nb_cards + 2)
            cnx.execute("Any C,W,T WHERE C is Card, C wikiid W, C title T")
            c1 = cnx.find("Card", wikiid="c1").one()
            self.assertEqual(c1.title, "t1")
            c2 = cnx.find("Card", wikiid="c2").one()
            self.assertEqual(c2.title, "t2")


class EADXMLReaderTests(BaseTestCase):
    def test_fa_properties(self):
        tree = eadreader.preprocess_ead(self.datapath("FRAN_IR_0261167_excerpt.xml"))
        reader = eadreader.EADXMLReader(tree, lambda x: x)
        fa_properties = reader.fa_properties
        self.assertIn("Art 1-6 : poissons migrateurs", fa_properties["scopecontent"])
        self.assertIn("dossiers par departement : syntheses", fa_properties["scopecontent"])
        # remove properties that are explicitly tested elsewhere and
        # make test results harder to read
        for untested in (
            "origination",
            "index_entries",
            "scopecontent_format",
            "scopecontent",
            "notes",
            "notes_format",
        ):
            fa_properties.pop(untested)
        fa_properties["did"].pop("origination")
        self.assertEqual(
            reader.fa_properties,
            {
                "accessrestrict": None,
                "accessrestrict_format": "text/html",
                "acquisition_info": None,
                "acquisition_info_format": "text/html",
                "additional_resources": None,
                "additional_resources_format": "text/html",
                "bibliography": None,
                "bibliography_format": "text/html",
                "bioghist": None,
                "bioghist_format": "text/html",
                "daos": [],
                "description": None,
                "description_format": "text/html",
                "did": {
                    "physloc": '<div class="ead-wrapper">Pierrefitte</div>',
                    "startyear": 1922,
                    "stopyear": 2001,
                    "unitdate": "1922-2001",
                    "unitid": "20050526/1-20050526/26",
                    "unittitle": "Environnement ; Direction de l'eau",
                },
                "fatype": "inventory",
                "userestrict": None,
                "userestrict_format": "text/html",
                "referenced_files": [],
                "website_url": "https://www.siv.archives-nationales.culture.gouv.fr/siv/IR/FRAN_IR_026167",  # noqa
            },
        )

    def test_index_entries(self):
        tree = eadreader.preprocess_ead(self.datapath("FRAN_IR_0261167_excerpt.xml"))
        reader = eadreader.EADXMLReader(tree, lambda x: x)
        index_entries = reader.fa_properties["index_entries"]
        expected = [
            {
                "authfilenumber": None,
                "label": "Jean-Michel",
                "normalized": "jean michel",
                "role": "index",
                "type": "persname",
            },
            {
                "authfilenumber": None,
                "label": "garonne (cours d'eau)",
                "normalized": "garonne cours d eau",
                "role": "index",
                "type": "geogname",
            },
            {
                "authfilenumber": None,
                "label": "poisson",
                "normalized": "poisson",
                "role": "index",
                "type": "subject",
            },
            {
                "authfilenumber": None,
                "label": "pisciculture",
                "normalized": "pisciculture",
                "role": "index",
                "type": "subject",
            },
            {
                "authfilenumber": None,
                "label": "aquaculture",
                "normalized": "aquaculture",
                "role": "index",
                "type": "subject",
            },
            {
                "authfilenumber": None,
                "label": "poisson",
                "normalized": "poisson",
                "role": "index",
                "type": "function",
            },
            {
                "authfilenumber": None,
                "label": "function",
                "normalized": "function",
                "role": "index",
                "type": "function",
            },
            {
                "authfilenumber": None,
                "label": "étude",
                "normalized": "etude",
                "role": "index",
                "type": "genreform",
            },
            {
                "authfilenumber": None,
                "label": "notaire",
                "normalized": "notaire",
                "role": "index",
                "type": "occupation",
            },
            {
                "authfilenumber": None,
                "label": "unicode control character",
                "normalized": "unicode control character",
                "role": "index",
                "type": "subject",
            },
        ]
        self.assertCountEqual(expected, index_entries)
        _, comp_properties = next(reader.walk())
        expected += [
            {
                "authfilenumber": None,
                "label": "jean-Michel",
                "normalized": "jean michel",
                "role": "index",
                "type": "persname",
            },
            {
                "authfilenumber": None,
                "label": "Jean-Paul",
                "normalized": "jean paul",
                "role": "index",
                "type": "persname",
            },
            {
                "authfilenumber": None,
                "label": "Garonne (cours d'eau)",
                "normalized": "garonne cours d eau",
                "role": "index",
                "type": "geogname",
            },
            {
                "authfilenumber": None,
                "label": "Poisson",
                "normalized": "poisson",
                "role": "index",
                "type": "subject",
            },
            {
                "authfilenumber": None,
                "label": "petits poissons",
                "normalized": "petits poissons",
                "role": "index",
                "type": "subject",
            },
            {
                "authfilenumber": None,
                "label": "m\xe9decin",
                "normalized": "medecin",
                "role": "index",
                "type": "function",
            },
            {
                "authfilenumber": None,
                "label": "plan",
                "normalized": "plan",
                "role": "index",
                "type": "genreform",
            },
            {
                "authfilenumber": None,
                "label": "avocat",
                "normalized": "avocat",
                "role": "index",
                "type": "occupation",
            },
        ]
        self.assertCountEqual(expected, comp_properties["index_entries"])

    def test_fa_origination(self):
        tree = eadreader.preprocess_ead(self.datapath("FRAN_IR_0261167_excerpt.xml"))
        reader = eadreader.EADXMLReader(tree, lambda x: x)
        self.assertEqual(
            reader.fa_properties["origination"],
            [
                {
                    "authfilenumber": "FRAN_NP_006122",
                    "label": "Direction de l'eau",
                    "normalized": "direction de l eau",
                    "role": "originator",
                    "type": "corpname",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
