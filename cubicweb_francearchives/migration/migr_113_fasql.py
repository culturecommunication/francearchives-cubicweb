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

import itertools

from cubicweb.dataimport.massive_store import PGHelper
from cubicweb_frarchives_edition.mviews import build_indexes


def copy_tables(cnx):
    """save a copy of published.cw_facomponent and published.cw_findingaid"""
    sql = cnx.system_sql
    print('making a copy of published.cw_findingaid')
    sql('DROP TABLE IF EXISTS published.cw_findingaid_copy')
    sql('CREATE TABLE published.cw_findingaid_copy as SELECT * FROM published.cw_findingaid')
    sql('DROP TABLE IF EXISTS published.cw_facomponent_copy')
    print('making a copy of published.cw_facomponent')
    sql('CREATE TABLE published.cw_facomponent_copy as SELECT * FROM published.cw_facomponent')
    cnx.commit()


def restore_copied_tables(cnx):
    """restore copied published.cw_facomponent and published.cw_findingaid tables"""
    sql = cnx.system_sql
    sql('DROP TABLE published.cw_findingaid')
    sql('ALTER TABLE published.cw_findingaid_copy RENAME TO cw_findingaid')
    print('rename copied table')
    sql('DROP TABLE published.cw_facomponent')
    sql('ALTER TABLE published.cw_facomponent_copy RENAME TO cw_facomponent')
    # rebuild indexes
    for etype in ('FAComponent', 'FindingAid'):
        cnx.system_sql('\n'.join(build_indexes(cnx, etype)))
    cnx.commit()


def set_additional_resource_format(cnx):
    sql = cnx.system_sql
    lasteid = 0
    total = sql('SELECT COUNT(cw_eid) from public.cw_facomponent').fetchone()[0]
    chunksize = 10000
    for i in itertools.count(1):
        print('set_additional_resource_format', '{}/{}'.format(i * chunksize, total))
        try:
            crs = sql(
                "UPDATE public.cw_facomponent fac SET cw_additional_resources_format='text/html' "
                "FROM ("
                "  SELECT t.cw_eid FROM public.cw_facomponent t"
                "  WHERE t.cw_eid > %(l)s AND T.cw_additional_resources_format IS NULL"
                "  ORDER BY t.cw_eid LIMIT {}"
                ") tt "
                "WHERE tt.cw_eid = fac.cw_eid RETURNING fac.cw_eid".format(chunksize),
                {'l': lasteid}
            )
            rset = crs.fetchall()
            if not rset:
                break
            lasteid = max(a for a, in rset)
        except Exception:
            cnx.rollback()
            raise
        else:
            cnx.commit()


def update_published(cnx, fastate_eid):
    # truncate actual published.cw_facomponent and ublished.cw_findingaid
    truncated = False
    sql = cnx.system_sql
    print('truncate published.cw_findingaid and published.cw_facomponent')
    sql('TRUNCATE published.cw_findingaid, published.cw_facomponent')
    truncated = True
    # remove indexes
    dbhelper = PGHelper(cnx)
    dbhelper.pg_schema = 'published'
    sql("set search_path='published'")
    print('removing:')
    for tablename in ('cw_findingaid', 'cw_facomponent'):
        for name in dbhelper. _constraint_names(tablename):
            print('    constraint', tablename, name)
            sql('ALTER TABLE published.%s DROP CONSTRAINT %s' % (tablename, name))
        for name in dbhelper._index_names(tablename):
            print('    index', tablename, name)
            sql('DROP INDEX %s' % name)
    # triggers or public keys don't exsit on published
    # populate published.cw_facomponent and published.cw_findingaid for
    # public.cw_facomponent and public.cw_findingaid
    print('add default value on both published.cw_findingaid/cw_findingaid '
          'cw_additional_resources_format')
    sql("ALTER TABLE public.cw_findingaid ALTER COLUMN cw_additional_resources_format "
        "SET DEFAULT 'text/html'")
    sql("ALTER TABLE published.cw_findingaid ALTER COLUMN cw_additional_resources_format "
        "SET DEFAULT 'text/html'")
    print('SET cw_additional_resources_format=text/html on public.cw_findingaid')
    sql("UPDATE public.cw_findingaid SET cw_additional_resources_format='text/html'")
    print('populate findingaid into published schema')
    sql('INSERT INTO published.cw_findingaid '
        'SELECT fa.* FROM public.cw_findingaid fa '
        '     JOIN public.in_state_relation isr '
        '                  ON (fa.cw_eid=isr.eid_from) '
        'WHERE isr.eid_to=%(state_eid)s', {'state_eid': fastate_eid})

    # add default value on cw_additional_resources_format
    print('add default value on both published.cw_facomponent/cw_facomponent '
          'cw_additional_resources_format')
    sql("ALTER TABLE public.cw_facomponent ALTER COLUMN cw_additional_resources_format "
        "SET DEFAULT 'text/html'")
    sql("ALTER TABLE published.cw_facomponent ALTER COLUMN cw_additional_resources_format "
        "SET DEFAULT 'text/html'")
    print('SET cw_additional_resources_format=text/html on public.cw_facomponent')
    set_additional_resource_format(cnx)
    print('copy facomponent into published schema')
    # update published.cw_facomponent
    sql('INSERT INTO published.cw_facomponent '
        'SELECT fac.* from public.cw_facomponent  as fac '
        'JOIN public.cw_findingaid fa on fa.cw_eid = fac.cw_finding_aid '
        'JOIN public.in_state_relation isr on isr.eid_from = fa.cw_eid '
        'WHERE isr.eid_to = %(state_eid)s',
        {'state_eid': fastate_eid})
    # rebuild indexes
    print('rebuild indexes')
    for etype in ('FAComponent', 'FindingAid'):
        sql('\n'.join(build_indexes(cnx, etype, sqlschema='published')))
    return truncated


def run(cnx):
    copy_tables(cnx)
    truncated = False
    try:
        fastate_eid = cnx.execute(
            'Any S WHERE S is State, S state_of WF, X default_workflow WF, '
            'X name %(etype)s, S name "wfs_cmsobject_published"',
            {'etype': 'FindingAid'})[0][0]
        truncated = update_published(cnx, fastate_eid)
        cnx.commit()
    except Exception as err:
        import traceback
        traceback.print_exc()
        cnx.rollback()
        cnx.exception('while executing update_published %s', err)
        if truncated:
            restore_copied_tables(cnx)

run(cnx)
