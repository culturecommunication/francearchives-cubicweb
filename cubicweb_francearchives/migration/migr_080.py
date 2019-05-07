# flake8: noqa
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
from __future__ import print_function
import os.path as osp
import re

from cubicweb_francearchives import CMS_OBJECTS

STATIC_RGX = re.compile('(/file/(static_\d+)/raw)')


def fix_illustration_urls(cnx, sql):
    """fix illustration_url vs. url attribution"""
    try:
        sql("UPDATE cw_digitizedversion "
            "SET cw_illustration_url=cw_url, cw_url='' "
            "WHERE cw_url ILIKE '%.JPG'")
    except Exception as exc:
        import traceback; traceback.print_exc()
        cnx.rollback()
    else:
        cnx.commit()


def cms_file_properties(cnx):
    q = ('Any F,FDN,FH WHERE F data_name FDN, F data_sha1hex FH, '
         'NOT EXISTS(X findingaid_support F)')
    return {osp.splitext(f.data_name)[0]: f for f in cnx.execute(q).entities()}


def rewrite_cms_content_urls(cnx):
    """fix static_file links and s/preprod.francearchives/francearchives.fr"""
    file_props = cms_file_properties(cnx)

    def oldurl2newurl(match):
        data_name = match.group(2)
        if data_name in file_props:
            props = file_props[data_name]
            return '/file/%s/%s' % (props.data_sha1hex,
                                    props.data_name)
        return match.group(0)  # data_name not found, leave it unchanged
    try:
        cu = cnx.cnxset.cu
        for etype in CMS_OBJECTS:
            # those types actually don't have content
            if etype in {'Circular', 'Map'}:
                continue
            sqldata = []
            # cu.execute('DROP TABLE IF EXISTS backup_cw_{etype}'.format(etype=etype))
            cu.execute('CREATE TABLE backup_cw_{etype} AS SELECT * from cw_{etype}'.format(
                etype=etype))
            for eid, content in cnx.execute('Any X,C WHERE X is {}, X content C, '
                                            'NOT X content NULL'.format(etype)):
                orig_content = content
                content = content.replace('preprod.francearchives.fr',
                                          'francearchives.fr')
                content = STATIC_RGX.sub(oldurl2newurl, content)
                if content != orig_content:
                    sqldata.append((content, eid))
            if sqldata:
                cu.executemany('UPDATE cw_{} SET cw_content=%s WHERE cw_eid=%s'.format(etype),
                               sqldata)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        cnx.rollback()
    else:
        cnx.commit()

