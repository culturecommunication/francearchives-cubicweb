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

"""Create a cwfile, link it to the specified entity (<entity_eid> param) by
`referenced_file` relation and print a html link to add in the entity content
attribute.

Use the script to import big files (up to 250 MB)

USAGE: cubicweb-ctl shell <instance>  upload_files.py -- <directory> <entity_eid>

"""
import math

import sys

from glob import glob

from os.path import isdir, exists
import os.path as osp

import mimetypes
from uuid import uuid4
import shutil

from cubicweb import Binary
from cubicweb_francearchives import init_bfss
from cubicweb_francearchives.dataimport import usha1


def convert_size(cnx, size_bytes):
    if size_bytes == 0:
        return "0"
    _ = cnx._
    size_name = ("", _("KB"), _("MB"), _("GB"), _("TB"))
    i = int(math.floor(math.log(size_bytes, 1024)))
    s = round(size_bytes / math.pow(1024, i), 2)
    return "{} {}".format(s, size_name[i])


def run(cnx, directory, entity_eid=None):
    """
    create Files stored in /srv/nfs/files_to_upload/176450318
    """
    if not exists(directory) or not isdir(directory):
        print("Directory {} does not exists".format(directory))
        sys.exit()
    entity = None
    if entity_eid:
        entity = cnx.execute("Any X WHERE X eid %(e)s", {"e": entity_eid})
        if not entity:
            print("Entity with eid {} does not exists".format(entity_eid))
            sys.exit()
        entity = entity.one()
    init_bfss(cnx.repo)
    appfilesdir = cnx.vreg.config["appfiles-dir"]
    print('Create files from "{}":'.format(directory))
    for i, filepath in enumerate(glob(osp.join(directory, "*.pdf"))):
        stream = open(filepath, "rb").read()
        sha1 = usha1(stream)
        basename = osp.basename(filepath)
        ufilepath = osp.join(appfilesdir, "{}_{}".format(sha1, basename))
        fobj = cnx.create_entity(
            "File",
            **{
                "title": str(basename),
                "data": Binary(stream),
                "data_format": str(mimetypes.guess_type(filepath)[0]),
                "data_name": str(basename),
                "data_hash": sha1,
                "uuid": str(uuid4().hex),
            }
        )
        link = "../../file/{}/{}".format(
            fobj.data_hash, fobj.cw_adapt_to("IDownloadable").download_file_name()
        )
        size = convert_size(cnx, osp.getsize(filepath))
        print(
            '\n   {i}: created in "{path}", eid {eid}'.format(eid=fobj.eid, path=ufilepath, i=i + 1)
        )
        fname, fext = osp.splitext(basename)
        title = "{fname}. Nouvel onglet ({ext}, {size}) - Nouvelle fenêtre".format(
            size=size, fname=fname, ext=fext.upper()[1:] if fext else ""
        )
        print(
            '    link:  <li><a href="{link}"  title="{title}" rel="nofollow noopener noreferrer" target="_blank">{name}</a></li>'.format(  # noqa
                link=link, title=title, name=fname
            )
        )
        if entity:
            referenced_files = [e.eid for e in entity.referenced_files]
            if fobj.eid not in referenced_files:
                cnx.execute(
                    """SET X referenced_files
                               F WHERE X eid %(e)s, F eid %(f)s""",
                    {"e": entity_eid, "f": fobj.eid},
                )
        cnx.commit()
        shutil.copy(filepath, ufilepath)


if __name__ == "__main__":
    directory = __args__[0]  # noqa
    eid = None  # noqa
    if len(__args__) > 1:  # noqa
        eid = __args__[1]  # noqa
    run(cnx, directory, entity_eid=eid)  # noqa
