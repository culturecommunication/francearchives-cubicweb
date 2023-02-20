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

from cubicweb_francearchives.testutils import EADImportMixin, PostgresTextMixin, OaiSickleMixin

from cubicweb.devtools.testlib import CubicWebTC
from cubicweb_francearchives.dataimport import oai
from cubicweb_francearchives.utils import merge_dicts
from cubicweb_francearchives.dataimport import (
    sqlutil,
    load_services_map,
    service_infos_from_service_code,
)
from cubicweb_francearchives.dataimport.importer import import_filepaths

from pgfixtures import setup_module, teardown_module  # noqa


class MixedImportTC(EADImportMixin, OaiSickleMixin, PostgresTextMixin, CubicWebTC):
    readerconfig = merge_dicts(
        {},
        EADImportMixin.readerconfig,
        {"reimport": True, "nodrop": False, "noes": True, "force_delete": True},
    )

    @classmethod
    def init_config(cls, config):
        super(MixedImportTC, cls).init_config(config)
        config.set_option(
            "consultation-base-url",
            "https://francearchives.fr",
        )
        config.set_option("ead-services-dir", "/tmp")
        config.set_option("instance-type", "consultation")

    def filepath(self):
        assert self.filename is not None
        return self.datapath("{}/{}".format(self.data_directory, self.filename))

    def create_repo(self, cnx, service_code, url):
        service = cnx.create_entity(
            "Service",
            name="AD {}".format(service_code),
            category="X",
            short_name="AD {}".format(service_code),
            code=service_code,
        )
        cnx.create_entity(
            "Service",
            category="?",
            name="Les Archives Nationales",
            short_name="Les AN",
            code="FRAN",
        )
        repo = cnx.create_entity("OAIRepository", name="some-repo", service=service, url=url)
        return repo

    def setup_database(self):
        super(MixedImportTC, self).setup_database()
        with self.admin_access.cnx() as cnx:
            cnx.create_entity("Service", name="Indre-et-Loire", code="FRAD037", category="foo")
            cnx.create_entity("Service", name="Marne", code="FRAD051", category="foo")
            cnx.create_entity("Service", name="Meuse", code="FRAD055", category="foo")
            cnx.commit()
            self.services_map = load_services_map(cnx)

    def test_reimport_oai_over_ead(self):
        """import an IR by oai over en existing ead-imported IR.
        Only one IR must be created.
        """
        with self.admin_access.cnx() as cnx:
            # import ead
            self.import_filepath(cnx, "FRAD037_1Q_2Q.xml")
            fa_ead = cnx.find("FindingAid").one()
            fa_ead_attrs = {"stable_id": fa_ead.stable_id, "name": fa_ead.name}
            # import oai
            self.assertEqual(fa_ead.dc_title(), "Domaines nationaux")
            self.filename = "FRAD037_1Q_2Q.xml"
            self.data_directory = "oai_ead"
            service_infos = service_infos_from_service_code("FRAD037", self.services_map)
            path = "file://{path}?verb=ListRecords&metadataPrefix=ead".format(path=self.filepath())
            oai.import_oai(cnx, path, service_infos)
            fa_oai = cnx.find("FindingAid").one()
            self.assertEqual(fa_oai.dc_title(), "Domaines nationaux oai")
            self.assertEqual(fa_oai.stable_id, fa_ead_attrs["stable_id"])
            self.assertEqual(fa_oai.name, fa_ead_attrs["name"])

    def test_reimport_ead_over_oai(self):
        """import an IR by ead over en existing oai-imported IR.
        Only one IR must be created.
        """
        with self.admin_access.cnx() as cnx:
            # import ead
            self.filename = "FRAD037_1Q_2Q.xml"
            self.data_directory = "oai_ead"
            service_infos = service_infos_from_service_code("FRAD037", self.services_map)
            path = "file://{path}?verb=ListRecords&metadataPrefix=ead".format(path=self.filepath())
            oai.import_oai(cnx, path, service_infos)
            fa_oai = cnx.find("FindingAid").one()
            fa_oai_attrs = {"stable_id": fa_oai.stable_id, "name": fa_oai.name}
            self.assertEqual(fa_oai.dc_title(), "Domaines nationaux oai")
            # import ead
            self.import_filepath(cnx, "FRAD037_1Q_2Q.xml")
            fa_ead = cnx.find("FindingAid").one()
            self.assertEqual(fa_ead.dc_title(), "Domaines nationaux")
            self.assertEqual(fa_ead.stable_id, fa_oai_attrs["stable_id"])
            self.assertEqual(fa_ead.name, fa_oai_attrs["name"])

    def test_mixed_reimport_from_file(self):
        """Test OAI DC and EAD import from file.

        Trying: import OAI_EAD and OAI_DC harvested files and a regular EAD XML file
        Expecting: three FindingAid are created
        """
        readerconfig = {
            "esonly": False,
            "index-name": "dummy",
            "appid": "data",
            "appfiles-dir": self.datapath(),
            "nodrop": False,
            "noes": True,
        }
        with self.admin_access.cnx() as cnx:
            # import oai_dc harvested file
            self.filename = "oai_dc_sample.xml"
            self.data_directory = "oai_dc"
            url = "file://{path}?verb=ListRecords&metadataPrefix=oai_dc".format(
                path=self.filepath()
            )
            service_infos = service_infos_from_service_code("FRAD055", self.services_map)
            oai.import_oai(cnx, url, service_infos)
            # import oai_ead harvested file
            self.filename = "oai_ead_sample.xml"
            self.data_directory = "oai_ead"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filepath())
            service_infos = service_infos_from_service_code("FRAD051", self.services_map)
            oai.import_oai(cnx, url, service_infos)
            rql = "Any FSPATH(D) WHERE X findingaid_support F, F data D"
            filenames = [result[0].read() for result in cnx.execute(rql)]
            for filename in filenames:
                sqlutil.delete_from_filename(cnx, filename, interactive=False, esonly=False)
            cnx.commit()
            self.assertFalse(cnx.find("FindingAid"))
            # add a regular EAD XML filepath
            filenames.append(self.get_or_create_imported_filepath("FRAN_IR_000224.xml"))
            self.assertEqual(4, len(filenames))
            for filepath in filenames:
                print(filepath)
                self.assertTrue(self.fileExists(filepath))
            import_filepaths(cnx, filenames, readerconfig)
            actual = [row[0] for row in cnx.execute("Any E WHERE X is FindingAid, X eadid E")]
            self.assertEqual(4, cnx.find("FindingAid").rowcount)
            actual = [row[0] for row in cnx.execute("Any E WHERE X is FindingAid, X eadid E")]
            expected = ["FRAN_IR_000224", "FRAD055_REC", "FRAD051_000000028_203M", "FRAD051_204M"]
            self.assertCountEqual(actual, expected)
