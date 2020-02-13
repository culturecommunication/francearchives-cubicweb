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

from cubicweb.dataimport.stores import MetadataGenerator
from cubicweb.dataimport.massive_store import MassiveObjectStore, PGHelper


def clean_massive_store(store):
    """clean any temporary table left by a previous massive import"""
    store.logger.info("Start cleaning")
    # Get all the initialized etypes/rtypes
    if store._dbh.table_exists("cwmassive_initialized"):
        cu = store.sql("SELECT retype, type, uuid FROM cwmassive_initialized")
        entities = defaultdict(list)
        relations = defaultdict(list)
        for retype, _type, uuid in cu.fetchall():
            if _type == "rtype":
                relations[retype].append(uuid)
            else:  # _type = 'etype'
                entities[retype].append(uuid)
        # get back entity data from the temporary tables
        for etype, uuids in list(entities.items()):
            tablename = "cw_%s" % etype.lower()
            for uuid in uuids:
                tmp_tablename = "%s_%s" % (tablename, uuid)
                store._tmp_data_cleanup(tmp_tablename, etype, uuid)
        # get back relation data from the temporary tables
        for rtype, uuids in list(relations.items()):
            tablename = "%s_relation" % rtype.lower()
            for uuid in uuids:
                tmp_tablename = "%s_%s" % (tablename, uuid)
                store._tmp_data_cleanup(tmp_tablename, rtype, uuid)
    # delete the meta data table
    store.sql("DROP TABLE IF EXISTS cwmassive_initialized")
    store.commit()


class NoDropPGHelper(PGHelper):
    def drop_indexes(self, tablename):
        """Drop indexes and constraints, storing them in a table for later restore."""
        # Create a table to save the constraints, it allows reloading even after crash
        pass

    def drop_constraints(self, tablename):
        pass


def create_massive_store(cnx, nodrop=False, **kwargs):
    metagen = MetadataGenerator(cnx, meta_skipped=("owned_by", "created_by"))
    store = MassiveObjectStore(cnx, metagen=metagen, **kwargs)
    if nodrop:
        store._dbh = NoDropPGHelper(cnx)
    return store
