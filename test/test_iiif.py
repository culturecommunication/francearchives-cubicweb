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
from unittest.mock import MagicMock, patch

from cubicweb.devtools.testlib import CubicWebTC

from cubicweb_francearchives.testutils import (
    PostgresTextMixin,
    EADImportMixin,
)

from pgfixtures import setup_module, teardown_module  # noqa


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
                name="FRCND",
                short_name="FRCND",
                code="FRCND",
            )
            cnx.commit()

    def test_no_iiif_extprt(self):
        """Ligeo service without manifests"""
        with self.admin_access.cnx() as cnx:
            cnx.create_entity(
                "Service", code="FRAN", category="L", name="Archives nationales", iiif_extptr=True
            )
            cnx.commit()
            filepath = "ir_data/FRAN_IR_053754.xml"
            self.import_filepath(cnx, filepath)
            for fc in cnx.execute("Any X WHERE X is FAComponent").entities():
                if fc.digitized_urls and fc.did[0].extptr:
                    pass
            fc_rql = "Any X WHERE X is FAComponent, X did D, D unittitle %(s)s"
            fc = cnx.execute(fc_rql, {"s": "Portraits de dames"}).one()
            # no manifest as extptr is not an ark
            extptr = "https://www.siv.archives-nationales.culture.gouv.fr/siv/rechercheconsultation/consultation/ir/consultationIR.action?udId=c-4c79w78y4-1al5dxbf1q4be&irId=FRAN_IR_053754"  # noqa
            self.assertEqual(extptr, fc.did[0].extptr)
            self.assertTrue(fc.did[0].extptr)
            self.assertTrue(fc.digitized_urls)
            self.assertIsNone(fc.iiif_manifest)
            # no manifest as there is no digitized_urls
            for fc in cnx.execute(fc_rql, {"s": "Mou - My"}).entities():
                self.assertTrue(fc.did[0].extptr)
                self.assertFalse(fc.digitized_urls)
                self.assertIsNone(fc.iiif_manifest)

    @patch("cubicweb_francearchives.entities.ead.requests")
    def test_iiif_extprt(self, mock_requests):
        """Ligeo service with manifests"""
        with self.admin_access.cnx() as cnx:
            cnx.create_entity(
                "Service", code="FRAD034", category="L", name="Hérault", iiif_extptr=True
            )
            cnx.commit()
            self.import_filepath(cnx, "ir_data/FRAD034_194EDT.xml")
            fc_rql = "Any X WHERE X is FAComponent, X did D, D unitid %(unitid)s"
            fc = cnx.execute(fc_rql, {"unitid": "194 EDT 25"}).one()
            extptr = "https://archives-pierresvives.herault.fr/ark:/37279/vtacd9a36865ad5e5d3"
            self.assertEqual(extptr, fc.did[0].extptr)
            self.assertTrue(fc.did[0].extptr)
            self.assertTrue(fc.digitized_urls)

            # mock head request in iiif_manifest
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {"Content-Type": "application/json"}
            mock_requests.head.return_value = mock_response
            self.assertEqual(fc.iiif_manifest, f"{extptr}/manifest")

            fc_rql = "Any X WHERE X is FAComponent, X did D, D unitid %(unitid)s"
            fc = cnx.execute(fc_rql, {"unitid": "194 EDT 3"}).one()
            # no manifest as there is no digitized_urls
            extptr = "https://archives-pierresvives.herault.fr/ark:/37279/vta87ef415b69ff7467"
            self.assertEqual(extptr, fc.did[0].extptr)
            self.assertTrue(fc.did[0].extptr)
            self.assertFalse(fc.digitized_urls)
            self.assertIsNone(fc.iiif_manifest)


if __name__ == "__main__":
    unittest.main()
