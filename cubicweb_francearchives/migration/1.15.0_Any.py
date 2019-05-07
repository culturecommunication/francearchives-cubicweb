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
#

from cubicweb_francearchives.dataimport import sqlutil


with sqlutil.no_trigger(cnx, tables=('entities',), interactive=False):
    sql('truncate same_as_relation')
    sql('truncate other_forms_relation')
    sql("delete from entities where type in ('PniaLocation', 'PniaLocationForm', 'PniaAgent', 'PniaAgentForm', 'PniaSubject', 'PniaSubjectForm', 'IndexRole', 'Index')")

    sql('''
    truncate is_relation;
    insert into is_relation select e.eid, et.cw_eid from entities e join cw_cwetype et on et.cw_name = e.type;
    truncate is_instance_of_relation;
    insert into is_instance_of_relation select * from is_relation;

    truncate cw_source_relation;
    insert into cw_source_relation select eid, 1 from entities;


    create table tmp_owned_by_relation as select * from owned_by_relation where exists (select 1 from entities where eid = eid_from);
    truncate owned_by_relation;
    insert into owned_by_relation select * from tmp_owned_by_relation;
    drop table tmp_owned_by_relation;

    create table tmp_created_by_relation as select * from created_by_relation where exists (select 1 from entities where eid = eid_from);
    truncate created_by_relation;
    insert into created_by_relation select * from tmp_created_by_relation;
    drop table tmp_created_by_relation;
    ''')
    cnx.commit()

print("drop_relation_type('index_agent')")
drop_relation_type('index_agent')
print("drop_relation_type('index_location')")
drop_relation_type('index_location')
print("drop_relation_type('index_subject')")
drop_relation_type('index_subject')
print("drop_relation_type('other_forms')")
drop_relation_type('other_forms')
for subtype in ('PniaLocation', 'PniaSubject', 'PniaAgent'):
    drop_relation_definition(subtype, 'same_as', 'ExternalUri')
print("drop_relation_definition('PniaAgent', 'same_as', 'Person')")
drop_relation_definition('PniaAgent', 'same_as', 'Person')
print("drop_relation_definition('PniaAgent', 'same_as', 'AuthorityRecord')")
drop_relation_definition('PniaAgent', 'same_as', 'AuthorityRecord')
print("drop_relation_definition('PniaSubject', 'same_as', 'Concept')")
drop_relation_definition('PniaSubject', 'same_as', 'Concept')
print("drop_entity_type('PniaLocation')")
drop_entity_type('PniaLocation')
print("drop_entity_type('PniaLocationForm')")
drop_entity_type('PniaLocationForm')
print("drop_entity_type('PniaAgent')")
drop_entity_type('PniaAgent')
print("drop_entity_type('PniaAgentForm')")
drop_entity_type('PniaAgentForm')
print("drop_entity_type('PniaSubject')")
drop_entity_type('PniaSubject')
print("drop_entity_type('PniaSubjectForm')")
drop_entity_type('PniaSubjectForm')
print("drop_entity_type('IndexRole')")
drop_entity_type('IndexRole')
print("drop_entity_type('Index')")
drop_entity_type('Index')


add_entity_type('LocationAuthority')
add_entity_type('Geogname')
add_entity_type('AgentAuthority')
add_entity_type('AgentName')
add_entity_type('SubjectAuthority')
add_entity_type('Subject')
add_relation_definition('CommemorationItem', 'related_authority', 'AgentAuthority')
add_relation_definition('ExternRef', 'related_authority', 'AgentAuthority')


sql(
    'CREATE TABLE authority_history ( '
    '  findingaid varchar(64),'
    '  type varchar(20),'
    '  label varchar(2048),'
    '  autheid int,'
    '  UNIQUE (findingaid, type, label)'
    ')'
)
