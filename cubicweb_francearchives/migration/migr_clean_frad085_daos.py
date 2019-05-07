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

from cubicweb_francearchives.dataimport import ead, sqlutil

from cubicweb_francearchives.dataimport.stores import NoDropPGHelper


class DaoReader(ead.Reader):
    """custom reader that skips all creation queries except for
    DigitizedVersions
    """
    def __init__(self, config, store):
        super(DaoReader, self).__init__(config, store)
        # add_rel is defined as an attribute, we want a standard method here
        del self.add_rel

    def add_rel(self, eid_from, rtype, eid_to):
        if rtype == 'digitized_versions':
            self.store.prepare_insert_relation(eid_from, rtype, eid_to)

    def create_entity(self, etype, attrs):
        if etype == 'DigitizedVersion':
            eid = self.store.prepare_insert_entity(etype, **attrs)
        elif 'stable_id' in attrs:
            eid = self.stable_id_to_eid(attrs['stable_id'])
        elif etype == 'EsDocument':
            self.store.sql(
                'UPDATE cw_esdocument SET cw_doc = %(doc)s WHERE cw_entity = %(entity)s',
                attrs)
            eid = None
        else:
            eid = None
        attrs['eid'] = eid
        return attrs

    def create_index(self, infos, target):
        # override create_index and make it a noop
        pass

    def push_indices(self):
        # override push_indices and make it a noop
        pass


def files_to_reimport(cnx):
    query = ('DISTINCT Any F, FS, FSPATH(FID) '
             'WHERE F findingaid_support FI, FI data FID, '
             'FI data_format "application/xml", F stable_id FS, '
             'C finding_aid F, F eadid LIKE "FRAD085%"')
    rset = cnx.execute(query)
    for eid, stable_id, fspath in rset:
        fspath = fspath.getvalue()
        yield (eid, stable_id, fspath)


def reimport_daos(cnx):
    importconfig = ead.readerconfig(cnx.vreg.config,
                                    cnx.vreg.config.appid,
                                    nodrop=True,
                                    esonly=False)
    importconfig['readercls'] = DaoReader
    importconfig['update_imported'] = True
    filepaths = []
    fa_eids = []
    print('analyzing database to extract which files should be reimported...')
    for fa_eid, _, fspath in files_to_reimport(cnx):
        filepaths.append(fspath)
        fa_eids.append(fa_eid)
    print('\t=> {} files must be reimported'.format(len(filepaths)))
    if (len(filepaths)) == 0:
        return
    with sqlutil.no_trigger(cnx, tables=('entities',
                                         'created_by_relation',
                                         'owned_by_relation',
                                         'cw_source_relation',
                                         'is_relation',
                                         'is_instance_of_relation',
                                         'cw_digitizedversion',
                                         'digitized_versions_relation'),
                            interactive=False):
        print('deleting old DAO references, this will take a few minutes')
        cursor = cnx.cnxset.cu
        cursor.execute('DROP TABLE IF EXISTS dao_to_remove')
        cursor.execute('CREATE TABLE dao_to_remove (eid integer)')
        cursor.execute('CREATE INDEX dao_to_remove_idx ON dao_to_remove(eid)')
        cursor.execute('INSERT INTO dao_to_remove '
                       'SELECT DISTINCT dvr.eid_to '
                       'FROM cw_facomponent fc '
                       '     JOIN digitized_versions_relation dvr ON (fc.cw_eid=dvr.eid_from) '
                       'WHERE fc.cw_finding_aid IN (%s)' % (
                           ','.join(str(eid) for eid in fa_eids)))
        cursor.execute(
            "SELECT delete_entities('cw_digitizedversion', 'dao_to_remove')"
        )
        cursor.execute(
            'DELETE FROM digitized_versions_relation dvr '
            'USING dao_to_remove dtr '
            'WHERE dvr.eid_to=dtr.eid'
        )
        cnx.commit()
        print('\t=> entities deleted, will now reimport corresponding files')
        ead.import_filepaths(cnx, filepaths, importconfig)


if __name__ == '__main__':
    reimport_daos(cnx)
