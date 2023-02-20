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


import re
import os.path as osp
import string
import urllib.parse
from collections import OrderedDict

from elasticsearch.exceptions import NotFoundError
from elasticsearch_dsl import Search, query as dsl_query
from functools import reduce

from logilab.mtconverter import xml_escape, html_unescape
from logilab.database import get_db_helper
from logilab.common.textutils import unormalize

from cubicweb.uilib import remove_html_tags as cw_remove_html_tags

from cubicweb_francearchives import GLOSSARY_CACHE, INDEX_ETYPE_2_URLSEGMENT

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
                        result += '<div class="eac-label">{label}</div>{value}'.format(
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
            "indices": [
                config["index-name"] + "_all",
                config["index-name"] + "_suggest",
            ],
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
            "indices": [
                index_prefix + "_all",
                index_prefix + "_suggest",
            ],
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
                "{schema}.{rtype}_relation({col});".format(
                    schema=sqlschema,
                    rtype=rtype,
                    col=col,
                )
            )
    schema_creation = ""
    if force_recreate or no_table_exists:
        # we should not recreate schema unless either force_recreate option is True or
        # all expected tables are missing
        schema_creation = """
drop schema if exists {schema} cascade;
create schema {schema} {authorization};
        """.format(
            schema=sqlschema,
            authorization="authorization %s" % user if user is not None else "",
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


def normalize_term(term):
    return term.lower()


def populate_terms_cache(req):
    """ """
    glossary = dict(
        (term, (eid, desc))
        for eid, term, desc in req.execute(
            """(Any T, TT, D WHERE T is GlossaryTerm, T short_description D, T term TT)
               UNION
               (Any T, TT, D WHERE T is GlossaryTerm, T short_description D, T term_plural TT
                , NOT T term_plural NULL)
            """
        ).rows
    )
    if not glossary:
        return
    keys = list(glossary.keys())
    keys.sort(key=len, reverse=True)
    for term in keys:
        if not term.strip():
            continue
        eid, desc = glossary[term]
        html = """<a data-bs-content="{content}" data-bs-toggle="popover" class="glossary-term" data-bs-placement="auto" data-bs-trigger="hover focus" data-bs-html="true" href="{url}" target="_blank">{{term}}\n<i class="fa fa-question"></i>\n</a>""".format(  # noqa
            content=xml_escape(desc), url=req.build_url("glossaire#{eid}".format(eid=eid))
        )
        # this don't handle accents. add it from unidecode import unidecode?
        GLOSSARY_CACHE.append((normalize_term(term), html))


def reveal_glossary(req, text, cached=False):
    def replace_term(matchobj):
        term = matchobj.group(0)
        if term:
            return glossary[normalize_term(term)].format(term=term)
        return term

    if GLOSSARY_CACHE or not cached:
        populate_terms_cache(req)
    if not GLOSSARY_CACHE:
        return text
    glossary = OrderedDict(GLOSSARY_CACHE)
    substrs = (r"\b{}\b".format(t) for t in glossary.keys())
    regexp = re.compile("|".join(substrs), re.I | re.U | re.M)
    return regexp.sub(replace_term, text)


def build_faq_url(req, faq_category):
    return req.build_url("faq#{}".format(faq_category))


def number_of_archives(req):
    es = get_connection(req.vreg.config)
    if not es:
        req.error("no elastisearch connection available")
        return 0
    index_name = req.vreg.config["index-name"]
    search = Search(index="{}_all".format(index_name))
    must = [{"term": {"escategory": "archives"}}]
    search.query = dsl_query.Bool(must=must)
    return search.count()


def number_of_qualified_authorities(req, auth_etype):
    es = get_connection(req.vreg.config)
    if not es:
        req.error("no elastisearch connection available")
        return 0
    index_name = f"{req.vreg.config['index-name']}_suggest"
    search = Search(index=index_name)
    must = [
        {"match": {"cw_etype": auth_etype}},
        {"range": {"count": {"gte": 1}}},
        {"match": {"quality": True}},
    ]
    search.query = dsl_query.Bool(must=must)
    return search.count()


def get_hp_articles(req, hp_context):
    """Select articles for Home Page

    We convert year and dates to string rather than in dates because of
    problems with ExternRef B.C year conversions to dates

    """
    entities = []
    sql_query = """
    SELECT T1.C0, T1.C1, T1.C2, T1.C4, T1.C5, T1.C6 FROM
    (SELECT DISTINCT _T0.C0 AS C0, _T0.C1 AS C1, _T0.C2 AS C2, _T0.C3 AS C3, _T0.C4 AS C4,
     _T0.C5 AS C5, _T0.C6 AS C6
      FROM (
       (SELECT bc.cw_eid AS C0,
               TRANSLATE_ENTITY(bc.cw_eid, 'title', %(lang)s) AS C1,
               TRANSLATE_ENTITY(bc.cw_eid, 'header', %(lang)s) AS C2,
               bc.cw_on_homepage_order AS C3,
               bc.cw_content_type AS C4,
               null AS C5, null AS C6
        FROM cw_BaseContent AS bc
        WHERE bc.cw_on_homepage=%(hp_context)s AND NOT (bc.cw_on_homepage_order IS NULL)
      UNION ALL
       SELECT nc.cw_eid AS C0, nc.cw_title AS C1, nc.cw_header AS C2, nc.cw_on_homepage_order AS C3,
              'NewsContent'  AS C4,
              to_char(cw_start_date, 'YYYYMMDD') AS C5, to_char(cw_stop_date, 'YYYYMMDD') AS C6
       FROM cw_NewsContent AS nc
        WHERE nc.cw_on_homepage=%(hp_context)s AND NOT (nc.cw_on_homepage_order IS NULL)
     UNION ALL
       SELECT er.cw_eid AS C0, er.cw_title AS C1, er.cw_header AS C2, er.cw_on_homepage_order AS C3,
              cw_reftype  AS C4,
              to_char(cw_start_year, '9999') AS C5, to_char(cw_stop_year, '9999') AS C6
       FROM cw_ExternRef AS er
        WHERE er.cw_on_homepage=%(hp_context)s AND NOT (er.cw_on_homepage_order IS NULL)
       UNION ALL
       SELECT ci.cw_eid AS C0,
              TRANSLATE_ENTITY(ci.cw_eid, 'title', %(lang)s) AS C1,
              TRANSLATE_ENTITY(ci.cw_eid, 'header', %(lang)s) AS C2,
              ci.cw_on_homepage_order AS C3,
              'CommemorationItem'  AS C4,
              null AS C5, null AS C6
       FROM cw_CommemorationItem AS ci
       WHERE ci.cw_on_homepage=%(hp_context)s AND NOT (ci.cw_on_homepage_order IS NULL))
     UNION ALL
      (SELECT sec.cw_eid AS C0,
              TRANSLATE_ENTITY(sec.cw_eid, 'title', %(lang)s) AS C1,
              TRANSLATE_ENTITY(sec.cw_eid, 'header', %(lang)s) AS C2,
              sec.cw_on_homepage_order AS C3,
              'Section'  AS C4,
              null AS C5, null AS C6
       FROM cw_Section AS sec
       WHERE sec.cw_on_homepage=%(hp_context)s AND NOT (sec.cw_on_homepage_order IS NULL))
      )
     AS _T0 ORDER BY 4)
    AS T1 """
    rset = req.cnx.system_sql(sql_query, {"hp_context": hp_context, "lang": req.lang}).fetchall()
    for eid, title, header, etype, start_date, stop_date in rset:
        entity = req.entity_from_eid(eid)
        image = entity.image
        default_picto_srcs = (
            [
                image.image_file[0].download_url(),
                req.uiprops["DOCUMENT_IMG"],
            ]
            if image
            else []
        )
        entities.append(
            {
                "url": entity.absolute_url(),
                "title": title,
                "plain_title": remove_html_tags(title),
                "header": header,
                "dates": entity.dates if start_date or stop_date else None,
                "link_title": title_for_link(req, title),
                "image": image,
                "etype": req._(etype),
                "default_picto_srcs": ";".join(default_picto_srcs),
            }
        )
    return entities


def get_autorities_by_label_es(req, label, auth_etype=None, normalize=True):
    es = get_connection(req.vreg.config)
    if not es:
        req.error("no elastisearch connection available")
        return 0
    index_name = f"{req.vreg.config['index-name']}_suggest"
    search = Search(index=index_name)
    must = [{"match": {"text.raw": label}}]
    if auth_etype:
        must.append({"match": {"cw_etype": auth_etype}})
    search.query = dsl_query.Bool(must=must)
    try:
        response = search.execute()
    except NotFoundError:
        return []
    results = []
    if response and response.hits.total:
        for result in response:
            results.append(
                {
                    "eid": result.eid,
                    "url": req.build_url(result.urlpath),
                    "label": result.text,
                    "etype": result.cw_etype,
                    "count": result.count,
                }
            )
    return results


def get_autorities_by_label(req, label, auth_etypes=None, normalize=True):
    return get_autorities_by(req, "cw_label", label, auth_etypes=auth_etypes, normalize=normalize)


def get_autorities_by_eid(req, eid):
    return get_autorities_by(req, "cw_eid", eid)


def get_autorities_by(req, where_attr, where_value, auth_etypes=None, normalize=True):
    queries = []
    for (
        etype,
        authtable,
        indextable,
    ) in (
        ("LocationAuthority", "cw_locationauthority", "cw_geogname"),
        ("SubjectAuthority", "cw_subjectauthority", "cw_subject"),
        ("AgentAuthority", "cw_agentauthority", "cw_agentname"),
    ):
        if auth_etypes and etype not in auth_etypes:
            continue
        queries.append(
            f"""
        (SELECT
           at.cw_eid,
           at.cw_label,
           COUNT(DISTINCT rel_index.eid_to),
           COUNT(DISTINCT rel_group.eid_to),
           '{etype}' as etype
        FROM {authtable} AS at
           LEFT OUTER JOIN {indextable} AS it ON (it.cw_authority=at.cw_eid)
           LEFT OUTER JOIN related_authority_relation AS rel_auth
                      ON (rel_auth.eid_to=at.cw_eid)
           LEFT OUTER JOIN index_relation AS rel_index
                     ON (rel_index.eid_from=it.cw_eid)
           LEFT OUTER JOIN grouped_with_relation AS rel_group
                              ON (rel_group.eid_from=at.cw_eid)
           WHERE at.{where_attr}=%(value)s
        GROUP BY  at.cw_eid,at.cw_label)"""
        )
    rset = req.cnx.system_sql(" UNION ".join(queries), {"value": where_value}).fetchall()
    if not rset:
        return []
    results = []
    for i, (autheid, label, count, grouped, etype) in enumerate(rset):
        results.append(
            {
                "eid": autheid,
                "url": req.build_url(f"{INDEX_ETYPE_2_URLSEGMENT[etype]}/{autheid}"),
                "label": label,
                "type": etype,
                "count": count,
            }
        )
    return results


def _build_transmap(substitute):
    transmap = {}
    for i in range(2**16 - 1):
        newc = unormalize(chr(i), substitute=substitute)
        if len(newc) == 1:
            transmap[i] = ord(newc)
        else:
            transmap[i] = newc
    return transmap


TRANSMAP = _build_transmap(substitute="_")

ES_TRANSMAP = _build_transmap(substitute="#")


NO_PUNCT_MAP = dict.fromkeys((ord(c) for c in string.punctuation), " ")


def register_blacklisted_authorities(cnx, label):
    if label:
        cnx.system_sql(
            """INSERT INTO blacklisted_authorities (label) VALUES
            (%(label)s) ON CONFLICT (label) DO NOTHING""",
            {"label": label},
        )


def es_start_letter(label):
    if label is None:
        return ""
    label = label.strip()
    letter = label[0] if len(label) > 0 else ""
    if letter.isdigit():
        return "0"
    if letter in string.punctuation:
        return "!"
    letter = letter.strip().translate(ES_TRANSMAP).lower()
    return letter


def delete_from_es_by_eid(cnx, eids, indexes):
    for index_name in indexes:
        es = get_connection(
            {
                "elasticsearch-locations": cnx.vreg.config["elasticsearch-locations"],
                "index-name": index_name,
                "elasticsearch-verify-certs": cnx.vreg.config["elasticsearch-verify-certs"],
                "elasticsearch-ssl-show-warn": cnx.vreg.config["elasticsearch-ssl-show-warn"],
            }
        )
        if not es:
            return
        for eid in eids:
            es.delete_by_query(
                index_name,
                doc_type="_doc",
                body={"query": {"match": {"eid": eid}}},
            )
