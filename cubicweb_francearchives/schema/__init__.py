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
from yams.buildobjs import (
    EntityType,
    RelationDefinition,
    RelationType,
    SubjectRelation,
    Date,
    String,
    RichString,
    Float,
)
from cubicweb_francearchives.schema.ead import Json


class LocationAuthority(EntityType):
    label = String()
    longitude = Float()
    latitude = Float()
    same_as = SubjectRelation(("AuthorityRecord", "ExternalUri", "ExternalId"))


class Geogname(EntityType):
    type = String(default="geogname")
    role = String(default="index")
    label = String()
    index = SubjectRelation(("FindingAid", "FAComponent"), cardinality="**")
    authority = SubjectRelation("LocationAuthority", cardinality="?*", inlined=True)
    authfilenumber = String(maxsize=128)


class AgentAuthority(EntityType):
    birthyear = Date()
    deathyear = Date()
    label = String()
    same_as = SubjectRelation(("AuthorityRecord", "ExternalUri", "ExternalId"))


class AgentName(EntityType):
    type = String()
    role = String(default="index")
    label = String()
    index = SubjectRelation(("FindingAid", "FAComponent"), cardinality="**")
    authority = SubjectRelation("AgentAuthority", cardinality="?*", inlined=True)
    authfilenumber = String(maxsize=128)


class AgentInfo(EntityType):
    """AgentInfo entities contain external information about
    an AgentAuthority.

    The 'dates' attributes contain the date of birth and date of death as well
    as related information, e.g.,
    dates = {
        'birthdate': {
            'timestamp': '1906-12-09', 'isbc': 'False', 'isdate': 'True', 'precision': 'd',
            'isiso': True
        },
        'deathdate': {
            'timestamp': '1992-01-01', 'isbc': 'False', 'isdate': 'True', 'precision': 'd',
            'isiso': True
        }
    }, with 'timestamp' being either a date string in '%Y-%m-%d' format ('isdate' is True in this
    case), or the original date if it cannot be converted into a date object ('isdate' is False
    in this case). The value 'isbc' is used to flag 'timestamp' as Before Christ.
    The value 'precision' specifies up to which time unit ('c' (century), 'dc' (decade),
    'y' (year), 'm' (month) or 'd' (day)) the timestamp is exact. The 'isiso' flag indicates
    whether BCE dates adhere to ISO8601 standard (0000 is 1BC -0001 is 2BC and so on).
    """

    dates = Json()
    description = RichString()


class SubjectAuthority(EntityType):
    label = String()
    same_as = SubjectRelation(("Concept", "ExternalUri", "ExternalId", "AuthorityRecord"))


class Subject(EntityType):
    type = String(default="subject")
    label = String()
    role = String(default="index")
    index = SubjectRelation(("FindingAid", "FAComponent"), cardinality="**")
    authority = SubjectRelation("SubjectAuthority", cardinality="?*", inlined=True)
    authfilenumber = String(maxsize=128)


class ExternalId(EntityType):
    extid = String(required=True, indexed=True, maxsize=256)
    label = String(maxsize=512)
    source = String(maxsize=32, indexed=True)


class authority_commemo(RelationDefinition):
    name = "related_authority"
    subject = "CommemorationItem"
    object = ("AgentAuthority", "LocationAuthority", "SubjectAuthority")
    cardinality = "**"


class authority_externref(RelationDefinition):
    name = "related_authority"
    subject = "ExternRef"
    object = ("AgentAuthority", "LocationAuthority", "SubjectAuthority")
    cardinality = "**"


class grouped_with(RelationType):
    constraints = [RQLConstraint("NOT S identity O")]
    cardinality = "?*"


class location_grouped_with(RelationDefinition):
    name = "grouped_with"
    cardinality = "?*"
    subject = "LocationAuthority"
    object = "LocationAuthority"


class agent_grouped_with(RelationDefinition):
    name = "grouped_with"
    cardinality = "?*"
    subject = "AgentAuthority"
    object = "AgentAuthority"


class subject_grouped_with(RelationDefinition):
    name = "grouped_with"
    cardinality = "?*"
    subject = "SubjectAuthority"
    object = "SubjectAuthority"


class agent_info_of(RelationDefinition):
    subject = "AgentInfo"
    object = "ExternalUri"
    cardinality = "1?"
    composite = "object"
    inlined = True


class xml_support(RelationDefinition):
    subject = "AuthorityRecord"
    object = "String"
    cardinality = "11"


class source(RelationDefinition):
    subject = "ExternalUri"
    object = "String"
    fulltextindexed = True
    maxsize = 32


class extid(RelationDefinition):
    subject = "ExternalUri"
    object = "String"
    fulltextindexed = True
    maxsize = 32


class label(RelationDefinition):
    subject = "ExternalUri"
    object = "String"
    maxsize = 512
