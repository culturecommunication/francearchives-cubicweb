# -*- coding: utf-8 -*-
#
# flake8: noqa
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2020
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

from cubicweb_francearchives.migration.utils import (
    drop_column_from_published_table,
    add_column_to_published_table,
)
from cubicweb_francearchives.migration.fast_drop_entities import fast_drop_entities

print("-> create section Pages d'histoire")

# Create section rechercher if it does not exist

kwargs = {"title": "Pages d'histoire"}
rset = cnx.find("Section", **kwargs)

if len(rset) == 0:
    section = cnx.create_entity("Section", **kwargs)
    cnx.commit()
else:
    section = rset.one()
    section.cw_set(name="pages_histoire")
    cnx.commit()

cnx.execute(
    "SET S children X WHERE X is CommemorationItem, S eid {}, NOT EXISTS(S children X)".format(
        section.eid
    )
)

cnx.execute(
    "SET D children S WHERE S eid {}, D name 'decouvrir', NOT EXISTS(D children S)".format(
        section.eid
    )
)

cnx.commit()

print("-> start deleting  CommemoCollection")

ci_count = rql("Any COUNT(X) WHERE X is CommemorationItem")[0][0]
print(f"Found {ci_count} exiting CommemorationItem")

print("-> drop relation collection_top")
# remove the composite CommemorationItem collection_top CommemoCollection
# relation in order to avoid CommemorationItem deletion while deleting
# CommemoCollections

drop_relation_definition("CommemorationItem", "collection_top", "CommemoCollection")
cnx.commit()

rql("DELETE File F WHERE X is CommemoCollection, X referenced_files F")
rql("DELETE Image I WHERE X is CommemoCollection, X section_image I")

print("-> delete CommemoCollection")
with cnx.allow_all_hooks_but("es", "sync", "varnish"):
    rset = rql("Any X WHERE X is  CommemoCollection")
    fast_drop_entities(rset)

res_count = rql("Any COUNT(X) WHERE X is CommemorationItem")[0][0]
print(f"Found {res_count} CommemorationItem, p1")

if res_count and res_count == ci_count:
    cnx.commit()
else:
    cnx.rollback()
    raise

res_count = rql("Any COUNT(X) WHERE X is CommemorationItem")[0][0]
print(f"Found {res_count} CommemorationItem")

print("-> drop entity CommemoCollection")

drop_entity_type("CommemoCollection")

res_count = rql("Any COUNT(X) WHERE X is CommemorationItem")[0][0]
print(f"Found {res_count} CommemorationItem")

cnx.system_sql(
    "drop table published.cw_commemocollection",
    rollback_on_failure=False,
)


drop_column_from_published_table(cnx, "commemorationitem", "collection_top")


cnx.commit()

res_count = rql("Any COUNT(X) WHERE X is CommemorationItem")[0][0]
print(f"Found {res_count} CommemorationItem, p4")

print("-> drop manif_prog")

# delete related BaseContent
rql("DELETE BaseContent B WHERE X manif_prog B")

drop_relation_type("manif_prog")

drop_column_from_published_table(cnx, "commemorationitem", "manif_prog")

cnx.commit()

print("-> add summary on CommemorationItem")

add_column_to_published_table(cnx, "commemorationitem", "summary_policy", "character varying(128)")
add_attribute("CommemorationItem", "summary_policy")

add_column_to_published_table(cnx, "commemorationitem", "summary", "text")
add_attribute("CommemorationItem", "summary")

add_column_to_published_table(cnx, "commemorationitem", "summary_format", "character varying(50)")
add_attribute("CommemorationItem", "summary_format")

cnx.commit()

add_column_to_published_table(
    cnx, "commemorationitemtranslation", "summary_format", "character varying(50)"
)
add_attribute("CommemorationItemTranslation", "summary_format")

cnx.commit()

print("-> sync_schema_props_perms on CommemorationItem")

sync_schema_props_perms("CommemorationItem")

res_count = rql("Any COUNT(X) WHERE X is CommemorationItem")[0][0]
print(f"Found {res_count} CommemorationItem, end")
