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

""":synopsis: OAI-PMH utils."""


# standard library imports
from __future__ import unicode_literals

import os
import os.path

# library specific imports
from cubicweb_francearchives import utils


class OAIPMHWriter(object):
    """OAI-PMH writer."""

    def __init__(self, ead_services_dir, service_infos):
        """Initialize OAI-PMH writer.

        :param str ead_services_dir: location of backup files
        :param dict service_infos: service information
        """
        self.ead_services_dir = ead_services_dir
        self.service_infos = service_infos

    def makedir(self, subdirectories=[]):
        """Create directory(ies).

        :param list subdirectories: list of subdirectories

        :returns: directory
        :rtype: str
        """
        directory = os.path.join(
            self.ead_services_dir, self.service_infos["code"], *subdirectories
        )
        if not os.path.exists(directory):
            os.makedirs(directory)
        return directory

    def get_file_path(self, directory, eadid):
        """Get file path.

        :param str eadid: EAD ID

        :returns: file path
        :rtype: str
        """
        eadid = utils.clean_up(eadid)
        filename = eadid + ".xml"
        file_path = os.path.join(directory, filename)
        return file_path

    def get_file_contents(self, *args):
        """Get file contents."""
        raise NotImplementedError

    def dump(self, file_path, file_contents):
        """Dump file contents.

        :param str file_path: filepath
        :param str file_contents: file contents
        """
        with open(file_path, "w") as fp:
            fp.write(file_contents)
