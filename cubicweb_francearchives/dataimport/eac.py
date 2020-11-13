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


from collections import defaultdict

from itertools import count
from os.path import basename
from time import time
import logging

from cubicweb.dataimport.importer import SimpleImportLog
from cubicweb.web.views.cwsources import REVERSE_SEVERITIES

from cubicweb_eac.dataimport import ETYPES_ORDER_HINT

from cubicweb_eac.sobjects import init_extid2eid_index as eac_init_extid2eid_index
from cubicweb_skos.dataimport import dump_relations

from cubicweb_francearchives.dataimport import log_in_db
from cubicweb_francearchives.dataimport.stores import create_massive_store

from cubicweb_francearchives.dataimport import sqlutil, to_unicode


# XXX once 3.24 is released: from cubicweb.dataimport.stores import NullStore
class NullStore(object):
    """Store that do nothing, handy to measure time taken be above steps"""

    def __init__(self):
        self._eid_gen = count()

    def prepare_insert_entity(self, *args, **kwargs):
        return next(self._eid_gen)

    def prepare_update_entity(self, etype, eid, **kwargs):
        pass

    def prepare_insert_relation(self, eid_from, rtype, eid_to, **kwargs):
        pass

    def flush(self):
        pass

    def commit(self):
        pass

    def finish(self):
        pass


class MyImportLog(SimpleImportLog):
    def __init__(self, filename, threshold=logging.WARNING):
        super(MyImportLog, self).__init__(filename)
        self.threshold = threshold

    def _log(self, severity, msg, path, line):
        if severity < self.threshold:
            return
        print(
            "[{severity}] {path}:{line}: {msg}".format(
                severity=REVERSE_SEVERITIES[severity], path=self.filename, line=line or 0, msg=msg
            )
        )


def eac_import_file(service, store, fpath, extid2eid, log):
    fname = basename(fpath)
    import_log = MyImportLog(fname, threshold=logging.ERROR)
    with open(fpath) as stream:
        try:
            created, updated, record, not_visited = service.import_eac_stream(
                stream, import_log, extid2eid=extid2eid, store=store, fpath=fpath
            )
        except Exception as exception:
            service._cw.rollback()
            if exception:
                log.error("{} : {}".format(fname, to_unicode(exception)))
            import traceback

            log.error(traceback.format_exc())
            return 0, 0, 0, 0
        return created, updated, record, not_visited


def eac_foreign_key_tables(schema):
    tables = set(ETYPES_ORDER_HINT)
    return sqlutil.foreign_key_tables(schema, tables)


def postprocess_import_eac(cnx, created_authrecs, sameas_authorityrecords, log):
    updated_authrecs = postprocess_authorities(cnx, log)
    updated_authrecs.update(created_authrecs)
    postprocess_same_as(cnx, sameas_authorityrecords, updated_authrecs)


def postprocess_authorities(cnx, log):
    """Replace ExternalUri with the same cwuri as AuthorityRecord record_id
    by the corresponding AuthorityRecord
    """
    rset = cnx.execute(
        """
        Any E, A, R WHERE A record_id R, E cwuri R, A is AuthorityRecord
    """
    )
    updated_authrecs = set()
    msg = "Transform {} ExternalUris into AuthorityRecords".format(rset.rowcount)
    log.info(msg)
    print(msg)
    to_remove = []
    for row in rset:
        exturi_eid, authrec_eid, record_id = row
        relations = dump_relations(cnx, exturi_eid, "ExternalUri")
        # remember the external uri's relations and store them in an operation
        for subject_eid, rtype, object_eid in relations:
            if rtype in ("same_as",):
                continue
            if subject_eid is None:
                subject_eid = authrec_eid
            if object_eid is None:
                object_eid = authrec_eid
            cnx.execute(
                "SET X %s Y WHERE X eid %%(x)s, Y eid %%(y)s" % rtype,
                {"x": subject_eid, "y": object_eid},
            )
        updated_authrecs.add((authrec_eid, record_id))
        to_remove.append((exturi_eid,))
    cursor = cnx.cnxset.cu
    cursor.execute("DROP TABLE IF EXISTS exturi_to_remove")
    cursor.execute("CREATE TABLE exturi_to_remove (eid integer)")
    cursor.executemany("INSERT INTO exturi_to_remove (eid) VALUES (%s)", to_remove)
    cursor.execute("SELECT delete_entities('cw_externaluri', 'exturi_to_remove')")
    cursor.execute("DROP TABLE exturi_to_remove")
    cnx.commit()
    return updated_authrecs


def postprocess_same_as(cnx, sameas_authorityrecords, authrecords):
    for (authrec_eid, record_id) in authrecords:
        for autheid in sameas_authorityrecords.get(record_id, []):
            query = """
                INSERT INTO same_as_relation (eid_from, eid_to)
                VALUES (%(auth)s, %(auth_rec)s)
                ON CONFLICT (eid_from, eid_to) DO NOTHING
            """
            cnx.system_sql(query, {"auth": int(autheid), "auth_rec": authrec_eid})
    cnx.commit()


def init_extid2eid_index(cnx, source):
    extid2eid = eac_init_extid2eid_index(cnx, source)
    for code, service_eid in cnx.execute("Any C, S WHERE S is Service, S code C, NOT S code NULL"):
        extid2eid["service-{}".format(code)] = service_eid
    return extid2eid


@log_in_db
def eac_import_files(cnx, fpaths, store=None, log=None):
    if not log:
        log = logging.getLogger("import_eac")
    start_time = time()
    imported = created = updated = 0
    if store is None:
        store = create_massive_store(cnx, nodrop=True)
    service = cnx.vreg["services"].select("eac.import", cnx)
    extid2eid = init_extid2eid_index(cnx, cnx.repo.system_source)
    foreign_keys = eac_foreign_key_tables(cnx.vreg.schema)
    sameas_authorityrecords = defaultdict(set)
    query = """
    DISTINCT Any R, A WITH R, A BEING (
    (
        DISTINCT Any R, A WHERE A same_as Y, Y is AuthorityRecord, Y record_id R
    ) UNION
    (   DISTINCT Any R, A WHERE I authority A,
        I authfilenumber R, NOT I authfilenumber NULL)
    )"""
    for record_id, autheid in store.rql(query):
        sameas_authorityrecords[record_id].add(autheid)
    created_authrecs = set()
    with sqlutil.no_trigger(cnx, foreign_keys, interactive=False):
        for fpath in fpaths:
            log.info("Process %r" % fpath)
            print("Process %r" % fpath)
            _created, _updated, record, not_visited = eac_import_file(
                service, store, fpath, extid2eid, log
            )
            if _created or _updated:
                imported += 1
                created += len(_created)
                updated += len(_updated)
                store.flush()
                store.commit()
                created_authrecs.add((record["eid"], record["record_id"]))
        if imported:
            store.finish()
    if imported:
        postprocess_import_eac(cnx, created_authrecs, sameas_authorityrecords, log)
    output_str = (
        "\nImported {imported}/{total} files ({created} entities + "
        "{updated} updates) in {time:.1f} seconds using {store}"
    )
    print(
        output_str.format(
            imported=imported,
            created=created,
            updated=updated,
            total=len(fpaths),
            time=time() - start_time,
            store=store.__class__.__name__,
        )
    )


if __name__ == "__main__":
    eac_import_files(cnx, __args__)  # noqa
