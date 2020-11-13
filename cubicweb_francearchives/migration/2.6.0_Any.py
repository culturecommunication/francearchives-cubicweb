# -*- coding: utf-8 -*-
#
# flake8: noqa
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


# standard library imports
# third party imports
# CubicWeb specific imports
# library specific imports

from collections import defaultdict

for obj in ("AgentAuthority", "LocationAuthority", "SubjectAuthority"):
    add_relation_definition("BaseContent", "related_authority", obj)

#

authors = defaultdict(set)

for eid, l in rql("""Any X, L WHERE X is CommemorationItem, X related_authority A, A label L"""):
    authors[eid].add(l)

with cnx.allow_all_hooks_but("es", "sync", "varnish"):
    for i, (eid, labels) in enumerate(authors.items()):
        commemo = cnx.entity_from_eid(eid)
        metadata = commemo.metadata
        if not metadata:
            metadata = cnx.create_entity("Metadata", reverse_metadata=commemo)
        else:
            metadata = metadata[0]
        cnx.entity_from_eid(eid).metadata[0].cw_set(creator=" ; ".join(sorted(labels)))

cnx.commit()

# update  normalize_entry sql function

cnx.system_sql(
    r"""
CREATE OR REPLACE FUNCTION normalize_entry(entry varchar)
RETURNS varchar AS $$
DECLARE
        normalized varchar;
BEGIN
 normalized := translate(entry, E'!"#$%&()*+,-./:;<=>?@[\\]^_`{|}~\'', '                                ');
 normalized := translate(normalized, E'\xc2\xa0\xc2\xb0\u2026\u0300\u0301', ' _.__');
 normalized := btrim(regexp_replace(unaccent(lower(normalized)), '\s+', ' ', 'g'));
 RETURN btrim(normalized);
END;
$$ LANGUAGE plpgsql;
    """
)

for attr in ("should_normalize", "context_service"):
    add_attribute("OAIRepository", attr)
