# -*- coding: utf-8 -*-
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


# standard library imports

# third party imports
# CubicWeb specific imports
from cubicweb.devtools.testlib import CubicWebTC

# library specific imports
from pgfixtures import setup_module, teardown_module  # noqa

from cubicweb_francearchives.utils import merge_dicts
from cubicweb_francearchives.utils import (
    register_blacklisted_authorities,
)
from cubicweb_francearchives.testutils import EADImportMixin, PostgresTextMixin
from cubicweb_francearchives.dataimport.sqlutil import delete_from_filename


def get_blacklisted_authorities(cnx):
    query = """SELECT label FROM blacklisted_authorities ORDER BY label"""
    return cnx.system_sql(query).fetchall()


class BlacklistedAuthoritiesTC(EADImportMixin, PostgresTextMixin, CubicWebTC):
    readerconfig = merge_dicts(
        {}, EADImportMixin.readerconfig, {"reimport": True, "nodrop": False, "force_delete": True}
    )

    def test_update_location_label(self):
        """
        Trying: import an IR, check created authorities. Blacklist authorities with
        exactly the same labels, with different labels (lowercase and
        accents). Delete and reimport IR.

        Expecting: Subject Authority with exactly the same label as a
        blacklisted auhority does not index IR. Locations still index the IR and
        subjects with a different label (case, accents) still index the IR.

        """
        fc_rql = "Any X WHERE X is FAComponent, X did D, D unitid %(u)s"
        with self.admin_access.cnx() as cnx:
            filepath = "FRAD095_00374.xml"
            self.import_filepath(cnx, filepath)
            fc = cnx.execute(fc_rql, {"u": "3Q7 753 - 773"}).one()
            subjects = [(i.label, i.type) for i in fc.subject_indexes().entities()]
            self.assertEqual(len(subjects), 3)
            self.assertIn(("TABLE ALPHABETIQUE", "genreform"), subjects)
            self.assertIn(("SUCCESSION", "subject"), subjects)
            self.assertIn(("ENREGISTREMENT", "subject"), subjects)
            locations = [(i.label, i.type) for i in fc.geo_indexes().entities()]
            self.assertEqual(len(locations), 36)
            self.assertIn(("Marines (Val-d'Oise ; canton)", "geogname"), locations)
            self.assertIn(("Santeuil (Val-d'Oise)", "geogname"), locations)
            self.assertIn(("Vallangoujard (Val-d'Oise)", "geogname"), locations)
            blacklisted = sorted(
                (
                    "Enregistrement",
                    "TABLE ALPHABETIQUE",
                    "SUCCÉSSION",
                    "Marines (Val-d'Oise ; canton)",
                    "Vallangoujard (Val-d'Oise)",
                )
            )
            for label in blacklisted:
                register_blacklisted_authorities(cnx, label)
            got = [e for e, in get_blacklisted_authorities(cnx)]
            self.assertEqual(got, blacklisted)
            # reimport filepath
            # delete the imported IR and reimport the filepath
            delete_from_filename(cnx, filepath, interactive=False, esonly=False)
            cnx.commit()
            self.assertFalse(cnx.execute(fc_rql, {"u": "3Q7 753 - 773"}))
            self.import_filepath(cnx, filepath)
            fc = cnx.execute(fc_rql, {"u": "3Q7 753 - 773"}).one()
            subjects = [(i.label, i.type) for i in fc.subject_indexes().entities()]
            self.assertEqual(len(subjects), 2)
            self.assertNotIn(("TABLE ALPHABETIQUE", "genreform"), subjects)
            self.assertIn(("SUCCESSION", "subject"), subjects)
            self.assertIn(("ENREGISTREMENT", "subject"), subjects)
            locations = [(i.label, i.type) for i in fc.geo_indexes().entities()]
            self.assertEqual(len(locations), 36)
            self.assertIn(("Marines (Val-d'Oise ; canton)", "geogname"), locations)
            self.assertIn(("Santeuil (Val-d'Oise)", "geogname"), locations)
            self.assertIn(("Vallangoujard (Val-d'Oise)", "geogname"), locations)
