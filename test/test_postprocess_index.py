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

from cubicweb.devtools.testlib import CubicWebTC

from cubicweb_francearchives.testutils import PostgresTextMixin

from pgfixtures import setup_module, teardown_module  # noqa


class PostprocessTests(PostgresTextMixin, CubicWebTC):

    def test_normalize_entry(self):
        with self.admin_access.cnx() as cnx:
            def norm(label):
                cu = cnx.system_sql('SELECT normalize_entry(%(l)s)', {'l': label})
                return cu.fetchone()[0]

            self.assertEqual(norm('Charles de Gaulle'), 'charles de gaulle')
            self.assertEqual(norm('Charles   de Gaulle'), 'charles de gaulle')
            self.assertEqual(norm('Charles, Gaulle (de)'), 'charles de gaulle')
            self.assertEqual(norm('Gaulle de, Charles'), 'charles de gaulle')
            self.assertEqual(norm('Charles (de)   Gaulle'), 'charles de gaulle')
            self.assertEqual(norm('Charles de Gaulle (1890-1970)'), 'charles de gaulle')
            self.assertEqual(norm('Charles de Gaulle (1890 - 1970)'), 'charles de gaulle')
            self.assertEqual(norm('Charles de Gaulle (1890 - 1970)'), 'charles de gaulle')
            self.assertEqual(norm('Liszt, Franz (1811-1886)'), 'franz liszt')
            self.assertEqual(norm('Liszt (Franz)'), 'franz liszt')
            self.assertEqual(norm(u'debré, jean-louis (1944-....)'), 'debre jeanlouis')
            self.assertEqual(norm(u'DEBRE, Jean-Louis'), 'debre jeanlouis')
            self.assertEqual(norm(u'Debré, Jean-Louis'), 'debre jeanlouis')


if __name__ == '__main__':
    unittest.main()
