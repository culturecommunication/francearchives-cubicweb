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
import os
import os.path as osp
from pwd import getpwnam


def chown(filepath):
    www_data_infos = getpwnam('www-data')
    try:
        os.chown(filepath, www_data_infos.pw_uid, www_data_infos.pw_gid)
    except OSError:
        print('failed to chown', repr(filepath))


def fix_files_with_no_bfss(cnx):
    """dump to filesystem files created without bfss properly initialized"""
    cursor = cnx.cnxset.cu
    cursor.execute('SELECT cw_eid, cw_data_name, cw_data_format, cw_data_sha1hex, cw_data '
                   'FROM cw_file WHERE length(cw_data) > 200')

    output_dir = cnx.vreg.config['appfiles-dir']
    for eid, basename, fmt, sha1, data in cursor.fetchall():
        print('processing', repr(basename))
        output_filepath = osp.join(output_dir, '{}_{}'.format(sha1, basename))
        with open(output_filepath, 'w') as out:
            out.write(str(data))
        chown(output_filepath)
        cursor.execute('UPDATE cw_file SET cw_data=%(data)s WHERE cw_eid=%(eid)s',
                       {'data': output_filepath, 'eid': eid})

    cnx.commit()

if __name__ == '__main__':
    fix_files_with_no_bfss(cnx)
