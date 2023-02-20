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

"""cubicweb-francearchives automatic tests


uncomment code below if you want to activate automatic test for your cube:

.. sourcecode:: python

    from cubicweb.devtools.testlib import AutomaticWebTest

    class AutomaticWebTest(AutomaticWebTest):
        '''provides `to_test_etypes` and/or `list_startup_views` implementation
        to limit test scope
        '''

        def to_test_etypes(self):
            '''only test views for entities of the returned types'''
            return set(('My', 'Cube', 'Entity', 'Types'))

        def list_startup_views(self):
            '''only test startup views of the returned identifiers'''
            return ('some', 'startup', 'views')
"""

from cubicweb.devtools.testlib import CubicWebTC

from cubicweb_francearchives.testutils import PostgresTextMixin

from pgfixtures import setup_module, teardown_module  # noqa


class FranceArchivesViewsTC(PostgresTextMixin, CubicWebTC):
    vid_validators = {
        "index": lambda: None,
    }

    @classmethod
    def init_config(cls, config):
        super(FranceArchivesViewsTC, cls).init_config(config)
        config.set_option("instance-type", "cms")

    def setup_database(self):
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                self.section = cnx.create_entity("Section", title="the-section", name="commit")
                cnx.commit()

    def test_indexview(self):
        with self.new_access("anon").web_request() as req:
            self.view("index", req=req)


if __name__ == "__main__":
    from logilab.common.testlib import unittest_main

    unittest_main()
