# -*- coding: utf-8 -*-
#
# flake8: noqa
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2021
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

print("-> Add related_content_suggestion relation")
add_relation_type("related_content_suggestion")

print("-> add quality attribute on Authorities")

for etype in ("AgentAuthority", "SubjectAuthority", "LocationAuthority"):
    add_attribute(etype, "quality")

commit()

# empty fa_redirects table

print("-> drop and recreate fa_redirects table")

sql("DROP TABLE IF EXISTS fa_redirects;")

cnx.system_sql(
    """
    CREATE TABLE fa_redirects (
    eadid character varying(512),
    from_stable_id character varying(64) PRIMARY KEY NOT NULL,
    to_stable_id character varying(64) not null,
    date date,
    UNIQUE (from_stable_id, to_stable_id)
    );
    """
)
cnx.commit()
