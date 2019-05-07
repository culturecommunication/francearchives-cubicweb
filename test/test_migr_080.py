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

from cubicweb import Binary
from cubicweb.devtools.testlib import CubicWebTC

from cubicweb_francearchives.migration import migr_080


class Migration080Tests(CubicWebTC):

    def setUp(self):
        super(Migration080Tests, self).setUp()
        self.config.global_set_option('compute-sha1hex', True)

    def test_rewrite_cms_content(self):
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but('tidyhtml'):
                cnx.create_entity('BaseContent', title=u'bc1', content=u'hello')
                cnx.create_entity('BaseContent', title=u'bc2',
                                  content=u'<a href="https://preprod.francearchives.fr/file/static_11/raw">the file</a>')  # noqa
                f = cnx.create_entity('File', data=Binary(),
                                      data_name=u'static_11.pdf',
                                      data_format=u'application/pdf')
                cnx.create_entity('BaseContent', title=u'bc3',
                                  content=u'<a href="https://preprod.francearchives.fr/file/static_12/raw">the unknown file</a>')  # noqa
                migr_080.rewrite_cms_content_urls(cnx)
                self.assertEqual(cnx.find('BaseContent', title=u'bc1').one().content,
                                 u'hello')
                self.assertEqual(cnx.find('BaseContent', title=u'bc2').one().content,
                                 u'<a href="https://francearchives.fr/file/{}/static_11.pdf">the file</a>'.format(f.data_sha1hex))  # noqa
                # only hostname should have changed in bc3 because file is unknown
                self.assertEqual(cnx.find('BaseContent', title=u'bc3').one().content,
                                 u'<a href="https://francearchives.fr/file/static_12/raw">the unknown file</a>')  # noqa


if __name__ == '__main__':
    unittest.main()
