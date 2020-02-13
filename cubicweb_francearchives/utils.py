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

"""small utility functions"""


import os.path as osp
import string
import urllib.parse
from collections import OrderedDict

from elasticsearch.exceptions import NotFoundError
from functools import reduce

from logilab.mtconverter import xml_escape, html_unescape
from logilab.database import get_db_helper
from logilab.common.textutils import unormalize

from cubicweb.uilib import remove_html_tags as cw_remove_html_tags

from cubicweb_elasticsearch.es import get_connection


def remove_html_tags(html):
    html = html.replace("<br>", " ").replace(r"<br\>", " ").replace(r"<br \>", " ")
    return cw_remove_html_tags(html)


def merge_dicts(*dicts):
    def merge2dicts(x, y):
        z = x.copy()
        z.update(y)
        return z

    return reduce(merge2dicts, dicts)


def format_entity_attributes(elem, result):
    if type(elem) == dict or type(elem) == OrderedDict:
        if len(list(elem.keys())) == 1:
            for label, values in elem.items():
                result += "{}".format(format_entity_attributes(values, ""))
        else:
            for label, values in elem.items():
                if values:
                    if label:
                        result += '<div class="ead-label">{label}</div><div>{value}</div>'.format(
                            label=label, value=format_entity_attributes(values, "")
                        )
                    else:
                        result += format_entity_attributes(values, "")
        return result
    elif type(elem) == list:
        for i, e in enumerate(elem):
            if i == 0:
                result += "{}".format(format_entity_attributes(e, ""))
            else:
                result += " {}".format(format_entity_attributes(e, ""))
        return result
    else:
        return "{}".format(elem)


def pick(infos, *keys):
    return {k: infos[k] for k in keys if k in infos}


def find_card(cwreq, wikiid):
    """tries to find best card for ``wikiid`` and current language.

    Specification is:

    - if ``<wikiid>-<lang>`` exists, pick it,
    - otherwise if lang is not fr and ``<wikiid>-fr`` exists, pick it,
    - otherwise if ``<wikiid>`` exists, pick it,
    - otherwise return None
    """
    # try to fetch all candidates in a single query
    rset = cwreq.execute(
        "Any X,XW,XT,XC,XCF WHERE X is Card, "
        "X wikiid XW, X title XT, X content XC, X content_format XCF, "
        "X wikiid ILIKE %(w)s",
        {"w": "{}%".format(wikiid)},
    )
    cards = {e.wikiid: e for e in rset.entities()}
    candidate_wikiids = ["{}-fr".format(wikiid), wikiid]
    if cwreq.lang != "fr":
        candidate_wikiids.insert(0, "{}-{}".format(wikiid, cwreq.lang))
    for wikiid in candidate_wikiids:
        # consider card as valid if it exists _and_ has some content
        if wikiid in cards and cards[wikiid].content:
            return cards[wikiid]
    return None


def es_setup_backup(config):
    es = get_connection(config)
    es.snapshot.create_repository(
        repository="francearchives-backups",
        body={"type": "fs", "settings": {"location": "backups", "compress": True}},
    )


def es_dump(config, snapshot_name, delete=False):
    es = get_connection(config)
    if delete:
        try:
            es.snapshot.delete(repository="francearchives-backups", snapshot=snapshot_name)
        except NotFoundError:
            pass
    es.snapshot.create(
        repository="francearchives-backups",
        snapshot=snapshot_name,
        body={
            "indices": [config["index-name"] + "_all", config["index-name"] + "_suggest",],
            "include_global_state": False,
        },
    )


def es_restore(config, snapshot_name, index_prefix, delete=False):
    es = get_connection(config)
    if delete:
        for ext in ("_all", "_suggest"):
            # we need to loop on possible extensions here
            # to be a bit robust: if one of the indices does not
            # exists, we do want to delete other indices
            try:
                es.indices.delete(index=config["index-name"] + ext)
            except NotFoundError:
                pass
    es.snapshot.restore(
        repository="francearchives-backups",
        snapshot=snapshot_name,
        body={
            "indices": [index_prefix + "_all", index_prefix + "_suggest",],
            "include_global_state": False,
            "rename_pattern": ".+_([^_]+)$",
            "rename_replacement": config["index-name"] + "_$1",
        },
    )


# utility functions used for materialized view management
def table_exists(sql, tablename, pg_schema="public"):
    """Return True if the given table already exists in the database."""
    # sql can be either cnx.system_sql (Connection.system_sql) or sql helper of cubicweb-ctl shell
    # (ServerMigrationHelper.sqlexec)
    # in first case it returns cursor in second case it returns cursor.fetchall result
    cu = sql(
        "SELECT 1 from information_schema.tables " "WHERE table_name=%(t)s AND table_schema=%(s)s",
        {"t": tablename, "s": pg_schema},
    )
    if hasattr(cu, "fetchone"):
        return bool(cu.fetchone())
    return bool(cu)


def setup_published_schema(
    sql,
    etypes=None,
    rtypes=None,
    user=None,
    sqlschema="published",
    dumpfiles=None,
    force_recreate=False,
):
    """Create (or replace) a SQL schema (named "published" by default) in
    which we find filtered copied of CMS entities postgresql tables
    (and the required relations) that are in the
    wfs_cmsobject_published WF state.

    This schema can be used by the "read-only" application (using the
    "db-namespace" config option).
    """
    no_table_exists = True
    # create tables which does not exist in the dedicated namespace (schema) for entities that have
    # a publication workflow and their relations
    # XXX use jinja2 instead
    create_tables = []
    for etype in etypes:
        tablename = "cw_" + etype.lower()
        if table_exists(sql, tablename, sqlschema):
            no_table_exists = False
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
            no_table_exists = False
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
                "{schema}.{rtype}_relation({col});".format(schema=sqlschema, rtype=rtype, col=col,)
            )
    schema_creation = ""
    if force_recreate or no_table_exists:
        # we should not recreate schema unless either force_recreate option is True or
        # all expected tables are missing
        schema_creation = """
drop schema if exists {schema} cascade;
create schema {schema} {authorization};
        """.format(
            schema=sqlschema, authorization="authorization %s" % user if user is not None else "",
        )
    template = """
{schema_creation}

{create_tables}

{indexes}
"""
    sqlcode = template.format(
        schema_creation=schema_creation,
        create_tables="\n".join(create_tables),
        indexes="\n".join(indexes),
    )
    if dumpfiles:
        with open(osp.join(dumpfiles, "setup.sql"), "w") as fobj:
            fobj.write(sqlcode)
    if sql:
        sql(sqlcode)


def init_repository(config, interactive=True, drop=False, vreg=None, init_config=None):
    """Initialise a repository database by creating tables ONLY (does NOT
    fill them)

    XXX This is a partial copy of cubicweb.server.init_repository()
    """
    from cubicweb.server.repository import Repository
    from cubicweb.server.sqlutils import sqlexec, sqlschema, sql_drop_all_user_tables
    from cubicweb.server.sqlutils import _SQL_DROP_ALL_USER_TABLES_FILTER_FUNCTION as drop_filter

    # configuration to avoid db schema loading and user'state checking
    # on connection
    config.creating = True
    config.consider_user_state = False
    config.cubicweb_appobject_path = set(("hooks", "entities"))
    config.cube_appobject_path = set(("hooks", "entities"))
    # only enable the system source at initialization time
    repo = Repository(config, vreg=vreg)
    if init_config is not None:
        # further config initialization once it has been bootstrapped
        init_config(config)
    schema = repo.schema
    sourcescfg = config.read_sources_file()
    source = sourcescfg["system"]
    driver = source["db-driver"]
    with repo.internal_cnx() as cnx:
        sqlcnx = cnx.cnxset.cnx
        sqlcursor = cnx.cnxset.cu
        execute = sqlcursor.execute
        if drop:
            helper = get_db_helper(driver)
            dropsql = sql_drop_all_user_tables(helper, sqlcursor)
            # We may fail dropping some tables because of table dependencies, in a first pass.
            # So, we try a second drop sequence to drop remaining tables if needed.
            # Note that 2 passes is an arbitrary choice as it seems enough for our usecases
            # (looping may induce infinite recursion when user have no rights for example).
            # Here we try to keep code simple and backend independent. That's why we don't try to
            # distinguish remaining tables (missing privileges, dependencies, ...).
            failed = sqlexec(
                dropsql, execute, cnx=sqlcnx, pbtitle="-> dropping tables (first pass)"
            )
            if failed:
                failed = sqlexec(
                    failed, execute, cnx=sqlcnx, pbtitle="-> dropping tables (second pass)"
                )
                remainings = list(filter(drop_filter, helper.list_tables(sqlcursor)))
                assert not remainings, "Remaining tables: %s" % ", ".join(remainings)
        handler = config.migration_handler(schema, interactive=False, repo=repo, cnx=cnx)
        # install additional driver specific sql files
        handler.cmd_install_custom_sql_scripts()
        for cube in reversed(config.cubes()):
            handler.cmd_install_custom_sql_scripts(cube)
        _title = "-> creating tables "
        print(_title, end=" ")
        # schema entities and relations tables
        # can't skip entities table even if system source doesn't support them,
        # they are used sometimes by generated sql. Keeping them empty is much
        # simpler than fixing this...
        schemasql = sqlschema(schema, driver)
        failed = sqlexec(schemasql, execute, pbtitle=_title)
        if failed:
            print("The following SQL statements failed. You should check your schema.")
            print(failed)
            raise Exception("execution of the sql schema failed, you should check your schema")
        sqlcursor.close()
        sqlcnx.commit()
    print("-> database tables for instance %s created." % config.appid)


def safe_cut(text, length, remove_html=False):
    """returns a string of length <length> based on <text>, removing any html
    tags from given text if cut is necessary or remove_html`is True."""
    if not text:
        return ""
    noenttext = html_unescape(text)
    text_nohtml = remove_html_tags(noenttext)
    # try to keep html tags if text is short enough
    if len(text_nohtml) <= length:
        return text_nohtml if remove_html else text
    # else if un-tagged text is too long, cut it
    return xml_escape(text_nohtml[:length] + "...")


def cut_words(text, length=120, end="..."):
    """returns a string of a maximum length <length> based on <text>
    without cutting the words.

    '...' is appended to the text it has been cut.
    """
    count = 0
    words = text.split()
    for i, word in enumerate(words):
        count += len(word) + 1  # count the upcommingspace
        if count > length:
            i = i if i else 1
            title = " ".join(words[:i])
            break
    else:
        title = text
    if len(text) > count:
        title += end
    return title


def title_for_link(cnx, title, readmore=True):
    """html: title used to title attribute in links"""
    if readmore:
        end = " - {}".format(cnx._("Read more"))
    title = title.replace('"', "'")
    return "{}{}".format(title, end)


def id_for_anchor(title):
    if title:
        title = "".join([unormalize(x[0].lower()) for x in title])
        title = title.translate({ord(c): "" for c in string.punctuation})
        title = title.lower().replace(" ", "-")
    return title


def is_absolute_url(url):
    if bool(urllib.parse.urlparse(url).netloc):
        return True
    if url.startswith("www."):
        return True
    return False


def is_external_link(href, base_url):
    if is_absolute_url(href) and not href.startswith(base_url):
        return True
    return False
