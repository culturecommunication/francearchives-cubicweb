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
from cubicweb.schema import RQLConstraint
from yams.buildobjs import (EntityType, RelationDefinition, RelationType,
                            SubjectRelation, Date, String, Float)


class LocationAuthority(EntityType):
    label = String()
    same_as = SubjectRelation('ExternalUri')
    longitude = Float()
    latitude = Float()


class Geogname(EntityType):
    role = String()
    label = String()
    index = SubjectRelation(('FindingAid', 'FAComponent'), cardinality='**')
    authority = SubjectRelation('LocationAuthority', cardinality='?*', inlined=True)


class AgentAuthority(EntityType):
    birthyear = Date()
    deathyear = Date()
    label = String()
    same_as = SubjectRelation(('AuthorityRecord', 'ExternalUri'))


class AgentName(EntityType):
    type = String()
    role = String()
    label = String()
    index = SubjectRelation(('FindingAid', 'FAComponent'), cardinality='**')
    authority = SubjectRelation('AgentAuthority', cardinality='?*', inlined=True)


class SubjectAuthority(EntityType):
    label = String()
    same_as = SubjectRelation(('Concept', 'ExternalUri'))


class Subject(EntityType):
    label = String()
    role = String()
    index = SubjectRelation(('FindingAid', 'FAComponent'), cardinality='**')
    authority = SubjectRelation('SubjectAuthority', cardinality='?*', inlined=True)


class authority_commemo(RelationDefinition):
    name = 'related_authority'
    subject = 'CommemorationItem'
    object = ('AgentAuthority', 'LocationAuthority', 'SubjectAuthority')
    cardinality = '**'


class authority_externref(RelationDefinition):
    name = 'related_authority'
    subject = 'ExternRef'
    object = ('AgentAuthority', 'LocationAuthority', 'SubjectAuthority')
    cardinality = '**'


class grouped_with(RelationType):
    constraints = [RQLConstraint('NOT S identity O')]
    cardinality = '?*'


class location_grouped_with(RelationDefinition):
    name = 'grouped_with'
    cardinality = '?*'
    subject = 'LocationAuthority'
    object = 'LocationAuthority'


class agent_grouped_with(RelationDefinition):
    name = 'grouped_with'
    cardinality = '?*'
    subject = 'AgentAuthority'
    object = 'AgentAuthority'


class subject_grouped_with(RelationDefinition):
    name = 'grouped_with'
    cardinality = '?*'
    subject = 'SubjectAuthority'
    object = 'SubjectAuthority'
