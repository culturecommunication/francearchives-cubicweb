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
"""cubicweb-franceachives unit tests for security"""

from cubicweb.devtools.testlib import CubicWebTC

from cubicweb_francearchives.testutils import PostgresTextMixin
from pgfixtures import setup_module, teardown_module  # noqa


class IndexSchemaTC(PostgresTextMixin, CubicWebTC):
    def test_delete_index_target(self):
        """Remove the Index taget """
        with self.admin_access.repo_cnx() as cnx:
            ce = cnx.create_entity
            agent = ce("AgentAuthority", label="Jean Jean")
            ce("Person", name="Jean", forenames="Jean", publisher="nomina", authority=agent)
            externref = ce(
                "ExternRef",
                reftype="Virtual_exhibit",
                url="http://toto",
                title="toto",
                related_authority=agent,
            )
            cnx.commit()
            cnx.execute("DELETE ExternRef X")
            cnx.commit()
            self.assertTrue(cnx.find("AgentAuthority", eid=agent.eid))
            self.assertFalse(cnx.find("ExternRef", eid=externref.eid))

    def test_delete_index_authority(self):
        """Remove  Index authority"""
        with self.admin_access.repo_cnx() as cnx:
            ce = cnx.create_entity
            agent = ce("AgentAuthority", label="Jean Jean")
            ce("Person", name="Jean", forenames="Jean", publisher="nomina", authority=agent)
            externref = ce(
                "ExternRef",
                reftype="Virtual_exhibit",
                url="http://toto",
                title="toto",
                related_authority=agent,
            )
            cnx.commit()
            cnx.execute("DELETE AgentAuthority X")
            cnx.commit()
            self.assertFalse(cnx.find("AgentAuthority", eid=agent.eid))
            self.assertTrue(cnx.find("ExternRef", eid=externref.eid))


if __name__ == "__main__":
    import unittest

    unittest.main()
