# -*- coding: utf-8 -*-
#
# flake8: noqa
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2020
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


# standard library imports
# third party imports
# CubicWeb specific imports

# library specific imports

SQL_UPDATE = "UPDATE cw_%s SET cw_%s=%%(path)s WHERE cw_eid=%%(eid)s;"


def update_bfss_path(sql_cursor, etype_name, attr, eid, path):
    """update a bfss path"""
    query = SQL_UPDATE % (etype_name, attr)
    sql_cursor.execute(query, {"eid": eid, "path": path})


def update_hero_s3key(cnx):
    """Replace the data path of hero images"""
    sqlcnx = repo.system_source.get_connection()
    sql_cursor = sqlcnx.cursor()
    with cnx.allow_all_hooks_but("es", "sync", "varnish"):
        rset = rql(
            """Any F, FSPATH(D), C
               WHERE I is CssImage, I cssid LIKE "hero-%%",
               I image_file F, F data D, I cssid C
            """
        )

        for entity, old_filepath, name in rset.iter_rows_with_entities():
            old_filepath = old_filepath.getvalue().decode("utf8")
            s3key = f"{entity.data_hash}_{entity.data_name}"
            if old_filepath == s3key:
                print(f"{name}: the new key {s3key} is already set\n")
                continue
            print(f"{name}: updating from {old_filepath} to {s3key}\n")
            update_bfss_path(sql_cursor, "File", "data", entity.eid, s3key)
    sqlcnx.commit()
    sqlcnx.close()


with cnx.allow_all_hooks_but("es", "sync", "varnish"):
    update_hero_s3key(cnx)
