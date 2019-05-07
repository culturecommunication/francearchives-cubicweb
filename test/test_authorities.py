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
import unittest

from cubicweb.devtools.testlib import CubicWebTC

from cubicweb_francearchives.testutils import PostgresTextMixin, EADImportMixin
from cubicweb_francearchives.utils import merge_dicts

from pgfixtures import setup_module, teardown_module  # noqa


class GroupAuthoritiesTests(EADImportMixin, PostgresTextMixin, CubicWebTC):
    readerconfig = merge_dicts({},
                               EADImportMixin.readerconfig,
                               {'nodrop': False})

    def setUp(self):
        super(GroupAuthoritiesTests, self).setUp()
        with self.admin_access.cnx() as cnx:
            self.service = cnx.create_entity(
                'Service', code=u'FRAD054', category=u'foo')
            cnx.commit()

    def create_findingaid(self, cnx, eadid, service=None):
        service = service or self.service
        return cnx.create_entity(
            'FindingAid', name=eadid,
            stable_id=u'stable_id{}'.format(eadid),
            eadid=eadid,
            publisher=u'publisher',
            did=cnx.create_entity(
                'Did', unitid=u'unitid{}'.format(eadid),
                unittitle=u'title{}'.format(eadid)),
            fa_header=cnx.create_entity('FAHeader'),
            service=service
        )

    def group_locations(self, cnx, loc1, loc2,
                        service_infos=None, **custom_settings):
        loc1.group([loc2.eid])
        cnx.commit()
        loc2 = cnx.find('LocationAuthority', eid=loc2.eid).one()
        self.assertEqual([loc1], loc2.grouped_with)
        fc_rql = 'Any X WHERE X is FAComponent, X did D, D unitid %(u)s'
        self.import_filepath(cnx, self.datapath('ir_data/FRAD054_0000000407.xml'),
                             service_infos=service_infos, **custom_settings)
        fc = cnx.execute(fc_rql, {'u': u'31 Fi 47-185'}).one()
        loc = [ie.authority[0] for ie in fc.reverse_index if ie.cw_etype == 'Geogname'][0]
        self.assertEqual(loc1.eid, loc.eid)
        return loc

    def test_service_strict_orphan_authorities_same_labels(self):
        """newly created GEOGNAMES must not be attached to a grouped
        LocationAuthority:
         - index_policy == 'service/strict'
         - we have orphan locations with the same label
        """
        with self.admin_access.cnx() as cnx:
            loc_label = u'Nancy (Meurthe-et-Moselle, France)'
            loc1 = cnx.create_entity(
                'LocationAuthority', label=loc_label
            )
            loc2 = cnx.create_entity(
                'LocationAuthority', label=loc_label
            )
            cnx.commit()
            linked_authority = self.group_locations(cnx, loc1, loc2)
            # geogname label is the same that the linked_authority label
            self.assertEqual(loc1.label, linked_authority.reverse_authority[0].label)

    def test_service_strict_orphan_authorities_different_labels(self):
        """newly created GEOGNAMES must not be attached to a grouped
        LocationAuthority:
         - index_policy == 'service/strict'
         - we have orphan locations with different labels
        """
        with self.admin_access.cnx() as cnx:
            loc1 = cnx.create_entity(
                'LocationAuthority', label=u'Nancy (Meurthe-et-Moselle, France) regrouped'
            )
            loc2 = cnx.create_entity(
                'LocationAuthority', label=u'Nancy (Meurthe-et-Moselle, France)'
            )
            cnx.commit()
            linked_authority = self.group_locations(cnx, loc1, loc2)
            # geogname label is different from the linked_authority label
            self.assertNotEqual(loc1.label, linked_authority.reverse_authority[0].label)

    def test_service_strict_linked_authorities_same_labels(self):
        """newly created GEOGNAMES must not be attached to a grouped
        LocationAuthority:
         - index_policy == 'service/strict'
         - we have locations linked to the same service locations with the same label
        """
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            loc_label = u'Nancy (Meurthe-et-Moselle, France)'
            loc1 = cnx.create_entity(
                'LocationAuthority', label=loc_label
            )
            loc2 = cnx.create_entity(
                'LocationAuthority', label=loc_label
            )
            fa1 = self.create_findingaid(cnx, u'eadid1')
            ce('Geogname',
               label=u'index location 1',
               index=fa1, authority=loc1)
            fa2 = self.create_findingaid(cnx, u'eadid2')
            ce('Geogname',
               label=u'index location 2',
               index=fa2, authority=loc2)
            cnx.commit()
            linked_authority = self.group_locations(
                cnx, loc1, loc2,
                service_infos={"code": self.service.code, 'eid': self.service.eid})
            self.assertIn(loc1.label,
                          [l.label for l in linked_authority.reverse_authority])

    def test_global_strict_orphan_authorities_different_labels(self):
        """newly created GEOGNAMES must not be attached to a grouped
        LocationAuthority:
         - index_policy == 'global/strict'
         - we have orphan locations with different labels
        """
        with self.admin_access.cnx() as cnx:
            loc1 = cnx.create_entity(
                'LocationAuthority', label=u'Nancy (Meurthe-et-Moselle, France) regrouped'
            )
            loc2 = cnx.create_entity(
                'LocationAuthority', label=u'Nancy (Meurthe-et-Moselle, France)'
            )
            cnx.commit()
            linked_authority = self.group_locations(
                cnx, loc1, loc2, autodedupe_authorities='global/strict')
            # geogname label is different from the linked_authority label
            self.assertNotEqual(loc1.label, linked_authority.reverse_authority[0].label)

    def test_grouped_location_history(self):
        """ In case locations authorities are grouped,
            only the target autheid must be kept in authority_history
        """
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            loc_label = u'Nancy (Meurthe-et-Moselle, France)'
            loc1 = cnx.create_entity(
                'LocationAuthority', label=loc_label
            )
            loc2 = cnx.create_entity(
                'LocationAuthority', label=loc_label
            )
            fa1 = self.create_findingaid(cnx, u'eadid1')
            geog1 = ce('Geogname',
                       role=u'index',
                       label=u'index location 1',
                       index=fa1, authority=loc1)
            fa2 = self.create_findingaid(cnx, u'eadid2')
            geog2 = ce('Geogname',
                       role=u'index',
                       label=u'index location 2',
                       index=fa2, authority=loc2)
            cnx.commit()
            query = '''
            SELECT fa_stable_id, type, label, indexrole, autheid
            FROM authority_history'''
            res = cnx.system_sql(query).fetchall()
            self.assertCountEqual(
                [(fa1.stable_id, u'geogname', geog1.label, u'index', loc1.eid),
                 (fa2.stable_id, u'geogname', geog2.label, u'index', loc2.eid)],
                res)
            loc1.group([loc2.eid])
            cnx.commit()
            query = '''
            SELECT fa_stable_id, type, label, indexrole, autheid
            FROM authority_history'''
            res = cnx.system_sql(query).fetchall()
            self.assertCountEqual(
                [(fa1.stable_id, u'geogname', geog1.label, u'index', loc1.eid),
                 (fa2.stable_id, u'geogname', geog2.label, u'index', loc1.eid)],
                res)


class IndexHookTests(PostgresTextMixin, CubicWebTC):

    def create_findingaid(self, cnx, eadid):
        return cnx.create_entity(
            'FindingAid', name=eadid,
            stable_id=u'stable_id{}'.format(eadid),
            eadid=eadid,
            publisher=u'publisher',
            did=cnx.create_entity(
                'Did', unitid=u'unitid{}'.format(eadid),
                unittitle=u'title{}'.format(eadid)),
            fa_header=cnx.create_entity('FAHeader')
        )

    def test_grouped_authority_indexes(self):
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            loc1 = ce('LocationAuthority', label=u'location 1')
            loc2 = ce('LocationAuthority', label=u'location 2')
            loc3 = ce('LocationAuthority', label=u'location 3')
            fa1 = self.create_findingaid(cnx, u'eadid1')
            ce('Geogname',
               label=u'index location 1',
               index=fa1, authority=loc1)
            fa2 = self.create_findingaid(cnx, u'eadid2')
            ce('Geogname',
               label=u'index location 2',
               index=fa2, authority=loc2)
            fa3 = self.create_findingaid(cnx, u'eadid3')
            ce('Geogname',
               label=u'index location 3',
               index=fa3, authority=loc3)
            cnx.commit()
            loc2.group((loc3.eid,))
            loc1.group((loc2.eid,))
            cnx.commit()
            loc1 = cnx.find('LocationAuthority', eid=loc1).one()
            loc2 = cnx.find('LocationAuthority', eid=loc2).one()
            loc3 = cnx.find('LocationAuthority', eid=loc3).one()
            for fa in (fa1, fa2, fa3):
                fa = cnx.find('FindingAid', eid=fa).one()
                fa_index = fa.reverse_index[0]
                self.assertEqual(fa_index.authority[0].eid,
                                 loc1.eid)

    def test_grouped_authority_check_simple_cycle(self):
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            loc1 = ce('LocationAuthority', label=u'location 1')
            loc2 = ce('LocationAuthority', label=u'location 2')
            cnx.commit()
            loc1.group((loc2.eid,))
            cnx.commit()
            loc1 = cnx.find('LocationAuthority', eid=loc1).one()
            loc2 = cnx.find('LocationAuthority', eid=loc2).one()
            self.assertEqual(loc1.eid, loc2.grouped_with[0].eid)
            loc2.group((loc1.eid,))
            cnx.commit()
            loc1 = cnx.find('LocationAuthority', eid=loc1).one()
            loc2 = cnx.find('LocationAuthority', eid=loc2).one()
            self.assertEqual(loc2.eid, loc1.grouped_with[0].eid)
            self.assertEqual((), loc2.grouped_with)

    def test_grouped_authority_check_pipeline(self):
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            loc1 = ce('LocationAuthority', label=u'location 1')
            loc2 = ce('LocationAuthority', label=u'location 2')
            loc3 = ce('LocationAuthority', label=u'location 3')
            cnx.commit()
            loc2.group((loc1.eid,))
            cnx.commit()
            loc1 = cnx.find('LocationAuthority', eid=loc1).one()
            loc2 = cnx.find('LocationAuthority', eid=loc2).one()
            loc3 = cnx.find('LocationAuthority', eid=loc3).one()
            self.assertEqual(loc2.eid, loc1.grouped_with[0].eid)
            self.assertEqual((), loc2.grouped_with)
            self.assertEqual((), loc3.grouped_with)
            loc2.group((loc3.eid,))
            cnx.commit()
            loc1 = cnx.find('LocationAuthority', eid=loc1).one()
            loc2 = cnx.find('LocationAuthority', eid=loc2).one()
            loc3 = cnx.find('LocationAuthority', eid=loc3).one()
            self.assertEqual(loc2.eid, loc1.grouped_with[0].eid)
            self.assertEqual((), loc2.grouped_with)
            self.assertEqual(loc2.eid, loc3.grouped_with[0].eid)
            loc1.group((loc2.eid,))
            cnx.commit()
            loc1 = cnx.find('LocationAuthority', eid=loc1).one()
            loc2 = cnx.find('LocationAuthority', eid=loc2).one()
            loc3 = cnx.find('LocationAuthority', eid=loc3).one()
            self.assertEqual(loc1.eid, loc2.grouped_with[0].eid)
            self.assertEqual(loc1.eid, loc3.grouped_with[0].eid)
            self.assertEqual((), loc1.grouped_with)

    def test_grouped_authority_check_inhertied(self):
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            loc1 = ce('LocationAuthority', label=u'location 1')
            loc2 = ce('LocationAuthority', label=u'location 2')
            loc3 = ce('LocationAuthority', label=u'location 3')
            cnx.commit()
            loc2.group((loc3.eid,))
            loc1.group((loc2.eid,))
            cnx.commit()
            loc1 = cnx.find('LocationAuthority', eid=loc1).one()
            loc2 = cnx.find('LocationAuthority', eid=loc2).one()
            loc3 = cnx.find('LocationAuthority', eid=loc3).one()
            self.assertEqual(loc1.eid, loc2.grouped_with[0].eid)
            self.assertEqual(loc1.eid, loc3.grouped_with[0].eid)
            loc2.group((loc1.eid,))
            cnx.commit()
            loc1 = cnx.find('LocationAuthority', eid=loc1).one()
            loc2 = cnx.find('LocationAuthority', eid=loc2).one()
            loc3 = cnx.find('LocationAuthority', eid=loc3).one()
            self.assertEqual(loc2.eid, loc1.grouped_with[0].eid)
            self.assertEqual(loc2.eid, loc3.grouped_with[0].eid)


if __name__ == '__main__':
    unittest.main()
