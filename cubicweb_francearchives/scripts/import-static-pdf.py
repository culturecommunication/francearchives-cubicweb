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


from glob import glob
from uuid import uuid4
import hashlib
import os.path as osp
import shutil

from six import text_type as unicode

from cubicweb import Binary

from cubicweb_francearchives import init_bfss


def main(cnx, directory):
    init_bfss(cnx.repo)
    appfilesdir = cnx.vreg.config['appfiles-dir']
    cnx.vreg.config['compute-sha1hex'] = False
    for filepath in glob(osp.join(directory, '*.pdf')):
        sha1 = unicode(hashlib.sha1(open(filepath).read()).hexdigest())
        basename = 'static_%s' % osp.basename(filepath)
        ufilepath = osp.join(appfilesdir, '%s_%s' % (sha1, basename))
        print('create file', ufilepath)
        cnx.create_entity('File', **{'title': unicode(basename),
                                     'data': Binary(str(ufilepath)),
                                     'data_format': u'application/pdf',
                                     'data_name': unicode(basename),
                                     'data_sha1hex': sha1,
                                     'uuid': unicode(uuid4().hex)})
        shutil.copy(filepath, ufilepath)
    cnx.commit()


if __name__ == '__main__' and 'cnx' in globals():
    main(cnx, __args__[0])  # noqa
