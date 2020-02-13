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
"""cubicweb-francearcihves tests for postgres utils"""

from cubicweb.devtools import testlib  # noqa
from cubicweb.devtools import PostgresApptestConfiguration
from cubicweb_francearchives.dataimport import normalize_entry
from cubicweb_francearchives.testutils import PostgresTextMixin

from pgfixtures import setup_module, teardown_module  # noqa


class SQLUtilsBaseTC(PostgresTextMixin, testlib.CubicWebTC):
    configcls = PostgresApptestConfiguration

    def test_normalize_entry_iso(self):
        """labels whose normalization is the same in Python and PostgreSQL"""
        with self.admin_access.cnx() as cnx:
            query = "SELECT NORMALIZE_ENTRY(%(label)s)"
            for label, expected in (
                ("Charles de Gaulle", "charles de gaulle"),
                ("Charles   de Gaulle", "charles de gaulle"),
                ("Charles, Gaulle (de)", "charles de gaulle"),
                ("Gaulle de, Charles", "charles de gaulle"),
                ("Charles (de)   Gaulle", "charles de gaulle"),
                ("Charles de Gaulle (1890-1970)", "charles de gaulle"),
                ("Charles de Gaulle (1890 - 1970)", "charles de gaulle"),
                ("Charles de Gaulle (1890 - 1970)", "charles de gaulle"),
                ("Liszt, Franz (1811-1886)", "franz liszt"),
                ("Liszt (Franz)", "franz liszt"),
                ("debré, jean-louis (1944-....)", "debre jeanlouis"),
                ("DEBRE, Jean-Louis", "debre jeanlouis"),
                ("Debré, Jean-Louis", "debre jeanlouis"),
                ("Tavel... (de)", "de tavel"),
                ("Bonaparte, Élisa (1777-1820)", "bonaparte elisa"),
                ("Deboraüde ?", "deboraude"),
                ("Tavel… (de)", "de tavel."),
                (
                    "Blein (Ange François Alexandre) , général",
                    "alexandre ange blein francois general",
                ),
                (
                    "Route nationale (n° 120) -- Cantal (France)",
                    "120 cantal france n_ nationale route",
                ),
                (
                    (
                        """Comité d'attribution des fonds recueillis à l'occasion """
                        """de la journée nationale des orphelins de guerre (France)"""
                    ),
                    (
                        "a_ comite_ dattribution de de des des fonds france "
                        "guerre journe_e la loccasion nationale orphelins recueillis"
                    ),
                ),
            ):
                got = cnx.system_sql(query, {"label": label}).fetchall()[0][0]
                self.assertEqual(expected, got)
                self.assertEqual(expected, normalize_entry(label))

    def test_normalize_entry_not_iso(self):
        """labels whose normalization is not the same in Python and PostgreSQL"""
        with self.admin_access.cnx() as cnx:
            query = "SELECT NORMALIZE_ENTRY(%(label)s)"
            for label, expected in (
                # This is a sorting issue between "'" and "e" which is probably not
                # a big deal
                (
                    "Gauthier de rougemont, chef d’escadron",
                    [
                        "chef de d'escadron gauthier rougemont",
                        "chef d'escadron de gauthier rougemont",
                    ],
                ),
            ):
                got = cnx.system_sql(query, {"label": label}).fetchall()[0][0]
                self.assertIn(got, expected)
