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

from cubicweb_francearchives.migration import migr_update_fa_content
from cubicweb_francearchives.testutils import PostgresTextMixin
from test_import_ead import EADImportMixin

from pgfixtures import setup_module, teardown_module  # noqa


class UpdateImportTests(EADImportMixin, PostgresTextMixin, CubicWebTC):

    def test_update_fa_additional_resources(self):
        """https://extranet.logilab.fr/ticket/44252128"""
        fc_rql = 'Any X WHERE X is FAComponent, X did D, D unitid %(u)s'
        with self.admin_access.cnx() as cnx:
            fpath = 'FRAD067_1_FRAD067_EDF1_archives_paroissiales.xml'
            fspath = self.datapath(fpath)
            self.import_filepath(cnx, fspath)
            fc = cnx.execute(fc_rql, {'u': u'2 G'}).one()
            url = 'http://archives.bas-rhin.fr/media/96780/2G0Tabledesparoissesdef.pdf'
            relatedmaterial = (u'<a href="{url}" rel="nofollow noopener noreferrer" '
                               'target="_blank">{url}</a>'.format(url=url))
            self.assertIn(relatedmaterial,
                          fc.additional_resources)
            fc.cw_set(additional_resources=None)
            fc = cnx.find('FAComponent', eid=fc.eid).one()
            self.assertIsNone(fc.additional_resources)
        with self.admin_access.cnx() as cnx:
            migr_update_fa_content.reimport_content(cnx)
            fc = cnx.execute(fc_rql, {'u': u'2 G'}).one()
            self.assertIn(relatedmaterial, fc.additional_resources)


if __name__ == '__main__':
    unittest.main()
