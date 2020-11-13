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
import logging
from collections import defaultdict
from contextlib import contextmanager
import os.path as osp

from cubicweb.server.serverctl import system_source_cnx

from cubicweb_francearchives.dataimport import es_bulk_index


LOGGER = logging.getLogger()


@contextmanager
def sudocnx(cnx, interactive=True):
    source = cnx.vreg.config.system_source_config
    if not interactive:
        source = source.copy()
        if source.get("superuser-login"):
            source["db-user"] = source["superuser-login"]
        if source.get("superuser-password"):
            source["db-password"] = source["superuser-password"]
    sudocnx = system_source_cnx(
        source, special_privs="ENABLE / DISABLE TRIGGERS", interactive=interactive
    )
    try:
        yield sudocnx
    finally:
        sudocnx.close()


def disable_triggers(su_cnx, tables):
    cursor = su_cnx.cursor()
    for table in tables:
        cursor.execute("alter table %s disable trigger all" % table)
    su_cnx.commit()


def enable_triggers(su_cnx, tables):
    cursor = su_cnx.cursor()
    for table in tables:
        cursor.execute("alter table %s enable trigger all" % table)
    su_cnx.commit()


def foreign_key_tables(schema, etypes):
    tables = {"entities", "cw_source_relation", "is_relation", "is_instance_of_relation"}
    for etype in etypes:
        eschema = schema.eschema(etype)
        for rschema, tschemas, role in eschema.relation_definitions():
            # exclude relations with no actual existence in the database
            if rschema.type == "identity" or rschema.rule:
                continue
            if rschema.inlined:
                tables.add("cw_{}".format(eschema.type.lower()))
            else:
                tables.add("{}_relation".format(rschema.type.lower()))
                if len(tschemas) == 1:
                    tables.add("cw_{}".format(tschemas[0].type.lower()))
    return tables


@contextmanager
def no_trigger(cnx, tables=None, interactive=True):
    if tables is None:
        tables = ("entities",)
    if not tables:
        # do not open superuser connection if tables is empty
        yield
    else:
        with sudocnx(cnx, interactive=interactive) as su_cnx:
            disable_triggers(su_cnx, tables)
            try:
                yield
            except Exception:
                cnx.exception("fail in body of no_trigger")
                cnx.rollback()
                raise
            finally:
                enable_triggers(su_cnx, tables)


def finding_aid_eids(cnx, filename, eids=None, stable_ids=None, is_filename=True):
    """Get entity IDs and stable IDs to remove.

    :param Connection cnx: CubicWeb database connection
    :param filename: filename of finding aid support or stable ID
    :type filename: bytes or str
    :param dict eids: entity IDs to be removed
    :param dict stable_ids: stable IDs to be removed
    :param bool is_filename: whether filename is filename or stable ID

    :returns: entity IDs and stable IDs to be removed
    :rtype: dict and dict
    """
    if eids is None:
        eids = defaultdict(set)
    if stable_ids is None:
        stable_ids = defaultdict(set)
    if is_filename:
        # NOTE: can't query file based on their path, use data_name / basename
        # instead, it should be good enough since there's no basename collision
        # in the database
        if isinstance(filename, bytes):
            filename = filename.decode("utf-8")
        rset = cnx.execute(
            """
        Any FA, FAH, D, F, S  WHERE F is File, F data_name %(e)s,
        FA findingaid_support F, FA did D, FA fa_header FAH,
        FA stable_id S
        """,
            {"e": osp.basename(filename)},
            build_descr=False,
        )
    else:
        rset = cnx.execute(
            """
        Any FA, FAH, D, F, S WHERE FA stable_id S, FA stable_id %(stableid)s,
        FA findingaid_support F?, FA did D, FA fa_header FAH
        """,
            {"stableid": filename},
            build_descr=False,
        )
    if not rset:
        return eids, stable_ids
    fa, fah, did, f, s = rset.rows[0]
    eids["cw_findingaid"].add(fa)
    eids["cw_faheader"].add(fah)
    eids["cw_did"].add(did)
    if f:
        eids["cw_file"].add(f)
    rset = cnx.execute(
        """
        Any F WHERE FA eid %(eid)s, FA ape_ead_file F
        """,
        {"eid": fa},
        build_descr=False,
    )
    if rset:
        eids["cw_file"] |= {eid for eid, in rset}

    rset = cnx.execute(
        """
        (Any F WHERE FA eid %(eid)s, FA fa_referenced_files F)
        UNION
        (Any FC WHERE FA eid %(eid)s, FAC finding_aid FA,
        FAC fa_referenced_files FC)
        """,
        {"eid": fa},
        build_descr=False,
    )
    if rset:
        # copy new entity IDs without overwriting existing entity IDs
        eids["cw_file"] |= {eid for eid, in rset}
    stable_ids["FindingAid"].add(s)
    for index_type in ("Geogname", "AgentName", "Subject"):
        rset = cnx.execute(
            "DISTINCT Any I WHERE FA eid %(fa)s, I index FA, I is {}".format(index_type), {"fa": fa}
        )
        if rset:
            eids["cw_%s" % index_type.lower()] |= {eid for eid, in rset}
        rset = cnx.execute(
            "DISTINCT Any I WHERE FAC is FAComponent, "
            "FAC finding_aid FA, FA eid %(fa)s, "
            "I index FAC, I is {}".format(index_type),
            {"fa": fa},
        )
        if rset:
            eids["cw_%s" % index_type.lower()] |= {eid for eid, in rset}

    rset = cnx.execute("Any X WHERE X is EsDocument, X entity FA, FA eid %(fa)s", {"fa": fa})
    if rset:
        eids["cw_esdocument"].add(rset[0][0])
    rset = cnx.execute(
        "Any FAC, D, S, ES WHERE FAC is FAComponent, "
        "FAC finding_aid FA, FA eid %(fa)s, FAC did D, "
        "FAC stable_id S, ES? entity FAC",
        {"fa": fa},
    )
    for fac, did, stable_id, esdoc in rset:
        eids["cw_facomponent"].add(fac)
        eids["cw_did"].add(did)
        if esdoc:
            eids["cw_esdocument"].add(esdoc)
        stable_ids["FAComponent"].add(stable_id)
    rset = cnx.execute(
        "DISTINCT Any DV WHERE FAC digitized_versions DV, "
        "FAC is FAComponent, FAC finding_aid FA, "
        "FA eid %(fa)s",
        {"fa": fa},
    )
    if rset:
        eids["cw_digitizedversion"] |= {eid for eid, in rset}
    return eids, stable_ids


def delete_from_es(cnx, stable_ids):
    """Delete FindingAid entities and FAComponent entities from
    both ElasticSearch indexes.

    :param Connection cnx: CubicWeb database connection
    :param dict stable_ids: stable IDs and related document types
    """
    indexers = (
        # cms_indexer
        cnx.vreg["es"].select("indexer", cnx),
        # portal_indexer
        cnx.vreg["es"].select("indexer", cnx, published=True),
    )
    if cnx.vreg.config["enable-kibana-indexes"]:
        indexers += (cnx.vreg["es"].select("kibana-ir-indexer", cnx),)
    for indexer in indexers:
        es = indexer.get_connection()
        es_docs = []
        for doc_type, ids in list(stable_ids.items()):
            for id in ids:
                es_docs.append(
                    {
                        "_op_type": "delete",
                        "_index": indexer.index_name,
                        "_type": "_doc",
                        "_id": id,
                    }
                )
        es_bulk_index(es, es_docs, raise_on_error=False)


def delete_from_filename(cnx, filename, **kwargs):
    """Delete finding aid.

    :param Connection cnx: CubicWeb database connection
    :param filename: filename of finding aid support or stable ID of finding aid
    :type filename: bytes or str
    """
    eids, stable_ids = finding_aid_eids(cnx, filename, is_filename=kwargs.get("is_filename", True))
    delete_finding_aid(cnx, eids, stable_ids, **kwargs)


def delete_from_filenames(cnx, filenames, **kwargs):
    """Delete multiple finding aids.

    :param Connection cnx: CubicWeb database connection
    :param list filenames: list of filenames of finding aid supports or stable IDs of finding aids
    """
    eids, stable_ids = defaultdict(set), defaultdict(set)
    for filename in filenames:
        finding_aid_eids(
            cnx, filename, eids, stable_ids, is_filename=kwargs.get("is_filename", True)
        )
    delete_finding_aid(cnx, eids, stable_ids, **kwargs)


def delete_finding_aid(cnx, eid_map, stable_ids, esonly=True, interactive=True, **kwargs):
    """Delete finding aid(s).

    :param Connection cnx: CubicWeb database connection
    :param dict eid_map: entity IDs to be removed
    :param dict stable_ids: stable IDs to be removed
    :param bool esonly: whether only Elasticsearch document of finding aid(s) should be removed
    :param bool interactive: toggle interactive on/off
    """
    try:
        delete_from_es(cnx, stable_ids)
    except Exception:
        cnx.exception(
            "failed to delete %s from elasticsearch, continuing anyway", list(stable_ids.keys())
        )
    if esonly:
        return
    # XXX without a commit() or rollback() we might get a lock on next commit call
    # but deciding to commit or rollback should not be the responsibility of
    # this function.
    # cnx.rollback()
    with no_trigger(cnx, interactive=interactive):
        cursor = cnx.cnxset.cu
        for etypetable in eid_map:
            eids = [(e,) for e in eid_map[etypetable]]
            LOGGER.debug("etypetable %s (%s eids)", etypetable, len(eids))
            cursor.execute("DROP TABLE IF EXISTS tmp_eid_to_remove")
            # XXX add uuid in table name ?
            cursor.execute("CREATE TABLE tmp_eid_to_remove (eid integer)")
            cursor.execute("CREATE INDEX tmp_eid_idx ON tmp_eid_to_remove(eid)")
            cursor.executemany("INSERT INTO tmp_eid_to_remove (eid) VALUES (%s)", eids)
            if etypetable in ("cw_facomponent", "cw_findingaid"):
                cursor.executemany(
                    "DELETE FROM fa_referenced_files_relation WHERE eid_from = %s", eids
                )
            if etypetable == "cw_facomponent":
                cursor.executemany(
                    "DELETE FROM digitized_versions_relation WHERE eid_from = %s", eids
                )
            if etypetable in ("cw_geogname", "cw_agentname", "cw_subject"):
                cursor.executemany("DELETE FROM index_relation WHERE eid_from = %s", eids)
            cursor.execute("SELECT delete_entities('%s', '%s')" % (etypetable, "tmp_eid_to_remove"))
        cnx.commit()


def ead_foreign_key_tables(schema):
    etypes = {
        "FindingAid",
        "FAComponent",
        "File",
        "Did",
        "FAHeader",
        "DigitizedVersion",
        "Subject",
        "Geogname",
        "AgentName",
        "AgentAuthority",
        "LocationAuthority",
        "SubjectAuthority",
        "Person",
        "EsDocument",
    }
    return foreign_key_tables(schema, etypes)
