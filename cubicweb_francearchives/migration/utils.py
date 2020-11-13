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

""" migration helpers"""

from cubicweb_francearchives.utils import table_exists


def alter_published_table(cnx, table, column, attrtype):
    cnx.system_sql(
        str("ALTER TABLE published.cw_%s ADD  IF NOT EXISTS cw_%s %s" % (table, column, attrtype)),
        rollback_on_failure=False,
    )


def drop_column_from_published_table(cnx, table, column):
    cnx.system_sql(
        str("ALTER TABLE published.cw_%s DROP COLUMN cw_%s" % (table, column)),
        rollback_on_failure=False,
    )


def update_etypes_in_published_schema(
    sql, etypes=None, rtypes=(), user=None, sqlschema="published", dumpfiles=None, verbose=True
):
    """Add or update etype related table in schema (named "published" by default) in
    which we find filtered copied of CMS entities postgresql tables
    (and the required relations) that are in the
    wfs_cmsobject_published WF state.

    This schema can be used by the "read-only" application (using the
    "db-namespace" config option).
    """
    # create tables which does not exist in the dedicated namespace (schema) for entities that have
    # a publication workflow and their relations
    # XXX use jinja2 instead
    create_tables = []
    for etype in etypes:
        tablename = "cw_" + etype.lower()
        if table_exists(sql, tablename, sqlschema):
            continue
        create_tables.append(
            "create table if not exists {schema}.{table} as "
            "  select * from {table} where null;".format(table=tablename, schema=sqlschema)
        )
        create_tables.append(
            "alter table {schema}.{table} "
            "  add primary key (cw_eid);".format(table="cw_" + etype.lower(), schema=sqlschema)
        )

    # XXX should we introspect the cw schema to get these rtypes?
    indexes = []
    for rtype in rtypes:
        tablename = rtype + "_relation"
        if table_exists(sql, tablename, sqlschema):
            continue
        create_tables.append(
            "create table if not exists {schema}.{table} as "
            "  select * from {table} where null;".format(table=tablename, schema=sqlschema)
        )
        create_tables.append(
            "alter table {schema}.{table} "
            "  add primary key (eid_from, eid_to);".format(
                table=rtype + "_relation", schema=sqlschema
            )
        )
        # create indexes on those relation tables
        for col in ("eid_from", "eid_to"):
            indexes.append(
                "create index {rtype}_{col}_idx on "
                "{schema}.{rtype}_relation({col});".format(
                    schema=sqlschema,
                    rtype=rtype,
                    col=col,
                )
            )
    template = """
{schema_creation}

{create_tables}

{indexes}
"""
    sqlcode = template.format(
        schema_creation="",
        create_tables="\n".join(create_tables),
        indexes="\n".join(indexes),
    )
    if dumpfiles:
        with open(osp.join(dumpfiles, "setup.sql"), "w") as fobj:
            fobj.write(sqlcode)
    if not sqlcode.strip():
        print("-> no sqlcode to execute")
        return
    if sql:
        if verbose:
            print(sqlcode)
        sql(sqlcode)
