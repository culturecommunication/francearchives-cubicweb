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

from itertools import count
from os.path import basename
from time import time
import logging

from cubicweb.dataimport.importer import SimpleImportLog
from cubicweb.web.views.cwsources import REVERSE_SEVERITIES

from cubes.eac.sobjects import init_extid2eid_index

from cubicweb_francearchives.dataimport import log_in_db


# XXX once 3.24 is released: from cubicweb.dataimport.stores import NullStore
class NullStore(object):
    """Store that do nothing, handy to measure time taken be above steps
    """

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
        print('[{severity}] {path}:{line}: {msg}'.format(
            severity=REVERSE_SEVERITIES[severity],
            path=self.filename, line=line or 0,
            msg=msg))


def _store(cnx):
    if cnx.repo.system_source.dbdriver == 'postgres':
        from cubicweb.dataimport.stores import MetadataGenerator
        from cubicweb.dataimport.massive_store import MassiveObjectStore
        metagen = MetadataGenerator(cnx, meta_skipped=('owned_by', 'created_by'))
        return MassiveObjectStore(cnx, metagen=metagen, eids_seq_range=1000)
    else:
        from cubicweb.dataimport.stores import NoHookRQLObjectStore
        return NoHookRQLObjectStore(cnx)


def eac_import_file(service, store, fpath, extid2eid):
    import_log = MyImportLog(basename(fpath), threshold=logging.ERROR)
    with open(fpath) as stream:
        try:
            created, updated, record_eid, not_visited = service.import_eac_stream(
                stream, import_log, extid2eid=extid2eid, store=store)
            return created, updated
        except Exception:
            import traceback
            traceback.print_exc()
            return 0, 0


@log_in_db
def eac_import_files(cnx, fpaths):
    start_time = time()
    imported = created = updated = 0
    store = _store(cnx)
    service = cnx.vreg['services'].select('eac.import', cnx)
    extid2eid = init_extid2eid_index(cnx, cnx.repo.system_source)
    for fpath in fpaths:
        _created, _updated = eac_import_file(service, store, fpath, extid2eid)
        if _created or _updated:
            imported += 1
            created += len(_created)
            updated += len(_updated)
        store.flush()
        store.commit()
    store.finish()

    output_str = '\nImported {imported}/{total} files ({created} entities + ' \
                 '{updated} updates) in {time:.1f} seconds using {store}'
    print(output_str.format(
        imported=imported,
        created=created,
        updated=updated,
        total=len(fpaths),
        time=time() - start_time,
        store=store.__class__.__name__))


if __name__ == '__main__':
    eac_import_files(cnx, __args__)  # noqa
