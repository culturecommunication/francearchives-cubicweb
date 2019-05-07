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

from cubicweb_francearchives.migration import migr_113


class Migration113Tests(CubicWebTC):

    def setUp(self):
        super(Migration113Tests, self).setUp()
        self.config.global_set_option('compute-sha1hex', True)

    def test_rewrite_cms_content(self):
        with self.admin_access.cnx() as cnx:
            search_form_url = (u'http://archives.lille.fr/search?'
                               u'preset=6&'
                               u'query=&'
                               u'quot;%(term)s&'
                               u'quot&'
                               u'search-query=&'
                               u'view=classification&'
                               u'search-query=1')
            cnx.create_entity(
                'Service', category=u's1',
                short_name=u'DA Hautes-Alpes', code=u'FRAD005',
                search_form_url=search_form_url
            ).eid
            migr_113.fix_search_form_url(cnx)
            search_form_url = ('http://archives.lille.fr/search?'
                               'preset=6&'
                               'query=&'
                               'quot;%(eadid)s&'
                               'quot&'
                               'search-query=&'
                               'view=classification&'
                               'search-query=1')
            self.assertEqual(cnx.find('Service', code=u'FRAD005').one().search_form_url,
                             search_form_url)


if __name__ == '__main__':
    unittest.main()
