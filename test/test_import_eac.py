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
from itertools import count
from os.path import join, dirname
import unittest

from six import text_type
from six.moves import map

from cubicweb import devtools  # noqa
from cubicweb.dataimport.importer import SimpleImportLog


class EACXMLParserTC(unittest.TestCase):

    @classmethod
    def datapath(cls, *fname):
        """joins the object's datadir and `fname`"""
        return join(dirname(__file__), 'data', *fname)

    def file_extentities(self, fname):
        from cubicweb_francearchives.sobjects import EACCPFImporter
        fpath = self.datapath(fname)
        import_log = SimpleImportLog(fpath)
        # Use a predictable extid_generator.
        extid_generator = map(str, count()).next
        importer = EACCPFImporter(fpath, import_log, text_type,
                                  extid_generator=extid_generator)
        return importer.external_entities()

    def test_disabled_relations(self):
        for ext_entity in self.file_extentities('FRAD033_EAC_00001_simplified.xml'):
            self.assertNotIn(ext_entity.etype, ('EACResourceRelation',
                                                'ChronologicalRelation',
                                                'HierarchicalRelation',
                                                'AssociationRelation',
                                                'ExternalUrl'))


if __name__ == '__main__':
    unittest.main()
