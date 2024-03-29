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


import subprocess as S
import os.path as osp
import logging

from cubicweb_francearchives.dataimport import default_service_name
from cubicweb_francearchives.storage import S3BfssStorageMixIn


def pdf_infos(filepath):
    with S3BfssStorageMixIn().storage_handle_tmpfile_from_file(filepath) as fpath:
        pipe = S.Popen(["/usr/bin/pdftotext", fpath, "-"], stdout=S.PIPE)
        basepath = osp.basename(filepath)
        try:
            text = pipe.stdout.read().decode("utf-8")
        except Exception:
            logging.exception("failed to extract text from %s", filepath)
            text = ""
    return {
        "publisher": default_service_name(basepath),
        "title": basepath,
        "text": text,
    }


if __name__ == "__main__":
    import sys

    infos = pdf_infos(sys.argv[1])
    print("publisher", infos["publisher"])
    print("title", infos["title"])
    print("text", len(infos["text"]), infos["text"][:200])
