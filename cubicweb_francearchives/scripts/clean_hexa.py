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
import string
import os
import os.path as osp
from glob import glob

# -*- coding: utf-8 -*-
from lxml import etree

TRANS = (
    ("&rsquo;", "'"),
    ("&hellip;", "&#8230;"),
    ("&mdash;", "&#8212;"),
    ("&nbsp;", "&#160;"),
    ("&laquo;", "&lt;"),
    ("&raquo;", "&gt;"),
    ("&deg;", "&#176;"),
    ("&ndash;", "&#8211;"),
    (" & ", " &#38; "),
)


def clean_files(directory):
    new_directory = "NEW_{}".format(directory)
    if not osp.isdir(new_directory):
        os.mkdir(new_directory)
    for filepath in glob(osp.join(directory, "*.xml")):
        f = open(filepath)
        stream = f.read()
        for char in stream:
            if char not in string.ascii_letters:
                try:
                    num = ord(char)
                    if 31 >= num >= 13:
                        stream = stream.replace(char, "")
                except Exception:
                    pass
        for t, r in TRANS:
            stream = stream.replace(t, r)
        f.close()
        new_filepath = "{}/{}".format(new_directory, osp.basename(filepath))
        with open(new_filepath, "w") as f:
            f.write(stream)
        with open(new_filepath, "r") as nf:
            try:
                etree.parse(nf)
            except Exception as e:
                print("processing {}".format(filepath), e)


if __name__ == "__main__":
    import sys

    clean_files(sys.argv[1])
