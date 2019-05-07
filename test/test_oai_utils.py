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


""":synopsis: OAI utils test cases."""


# standard library imports
from __future__ import unicode_literals

import os
import glob
import unittest

# third party imports
# library specific imports
from cubicweb_francearchives.dataimport import oai_utils


class TestOAIPMHWriter(unittest.TestCase):
    """OAIPMHWriter test cases.

    :cvar str EAD_SERVICES_DIR: location of backup files
    :cvar dict SERVICE_INFOS: service information
    """

    EAD_SERVICES_DIR = "/tmp"
    PATH = os.path.join(EAD_SERVICES_DIR, "{code}/oaipmh")
    SERVICE_INFOS = {"code": "FRAD123"}

    def tearDown(self):
        """Tear down test cases."""
        super(TestOAIPMHWriter, self).tearDown()
        path = self.PATH.format(**self.SERVICE_INFOS)
        if os.path.exists(path):
            for filename in glob.glob(os.path.join(path, "*")):
                os.remove(filename)
            os.removedirs(path)

    def test_create_directory_existing(self):
        """Test XML backup files directory creation.

        Trying: already existing directory
        Expecting: existing directory with the same files
        """
        path = self.PATH.format(**self.SERVICE_INFOS)
        file_path = os.path.join(path, "foo")
        os.makedirs(path)
        open(file_path, "w+").close()
        oai_writer = oai_utils.OAIPMHWriter(
            self.EAD_SERVICES_DIR, self.SERVICE_INFOS
        )
        oai_writer.makedir(subdirectories=["oaipmh"])
        self.assertTrue(os.path.exists(path))
        self.assertTrue(os.path.exists(file_path))

    def test_create_directory_new(self):
        """Test backup XML file directory creation.

        Trying: new path
        Expecting: new directory
        """
        path = self.PATH.format(**self.SERVICE_INFOS)
        oai_writer = oai_utils.OAIPMHWriter(
            self.EAD_SERVICES_DIR, self.SERVICE_INFOS
        )
        oai_writer.makedir(subdirectories=["oaipmh"])
        self.assertTrue(os.path.exists(path))

    def test_get_file_path(self):
        """Test getting file path.

        Trying: fout-digit EAD ID
        Expecting: file path is {path}/{eadid}.xml
        """
        path = self.PATH.format(**self.SERVICE_INFOS)
        eadid = "1234"
        file_path = os.path.join(path, "{eadid}.xml".format(eadid=eadid))
        oai_writer = oai_utils.OAIPMHWriter(
            self.EAD_SERVICES_DIR, self.SERVICE_INFOS
        )
        self.assertEqual(file_path, oai_writer.get_file_path(path, eadid))

    def test_get_file_contents(self):
        """Test getting file contents.

        Trying: calling get_file_contents method
        Expecting: raises NotImplementedError
        """
        oai_writer = oai_utils.OAIPMHWriter(
            self.EAD_SERVICES_DIR, self.SERVICE_INFOS
        )
        with self.assertRaises(NotImplementedError):
            oai_writer.get_file_contents()

    def test_dump_new_file(self):
        """Test dumping file contents.

        Trying: new file
        Expecting: new file
        """
        path = self.PATH.format(**self.SERVICE_INFOS)
        file_path = os.path.join(path, "foo")
        os.makedirs(path)
        oai_writer = oai_utils.OAIPMHWriter(
            self.EAD_SERVICES_DIR, self.SERVICE_INFOS
        )
        oai_writer.dump(file_path, "bar")
        with open(file_path) as fp:
            self.assertEqual("bar", fp.read())

    def test_dump_existing_file(self):
        """Test dumping file contents.

        Trying: existing file
        Expecting: new file
        """
        path = self.PATH.format(**self.SERVICE_INFOS)
        file_path = os.path.join(path, "foo")
        os.makedirs(path)
        with open(file_path, "w+") as fp:
            fp.write("bar")
        oai_writer = oai_utils.OAIPMHWriter(
            self.EAD_SERVICES_DIR, self.SERVICE_INFOS
        )
        oai_writer.dump(file_path, "baz")
        with open(file_path) as fp:
            self.assertEqual("baz", fp.read())
