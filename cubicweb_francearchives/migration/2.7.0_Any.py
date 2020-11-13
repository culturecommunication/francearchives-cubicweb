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


# standard library imports
# third party imports
# CubicWeb specific imports

# library specific imports

from cubicweb_francearchives.migration.utils import alter_published_table

alter_published_table(cnx, "basecontent", "summary_policy", "character varying(128)")
alter_published_table(cnx, "basecontent", "summary", "text")
alter_published_table(cnx, "basecontent", "summary_format", "character varying(50)")

add_attribute("BaseContent", "summary_policy")
add_attribute("BaseContent", "summary")
add_attribute("BaseContent", "summary_format")

cnx.system_sql(
    str(
        "UPDATE published.cw_basecontent SET cw_summary_policy='no_summary', cw_summary_format='text/html'"
    )
)

sync_schema_props_perms("search_form_url")

cursor = cnx.cnxset.cu
cursor.execute(
    "SELECT cw_eid, cw_search_form_url FROM cw_service WHERE cw_search_form_url LIKE '%\%(%'"
)
rows = [(row[1], row[0]) for row in cursor.fetchall()]
for attr in ("eadid", "unitid", "unittitle", "unititle"):
    rows = [
        (row[0].replace("%({attr})s".format(attr=attr), "{{{attr}}}".format(attr=attr)), row[1])
        for row in rows
    ]
cursor.executemany("UPDATE cw_service SET cw_search_form_url=%s WHERE cw_eid=%s", rows)

# update same_as relations on grouped authorities
rql(
    "SET NEW same_as S WHERE OLD grouped_with NEW, OLD same_as S, NOT EXISTS(NEW same_as S), NOT EXISTS (S same_as NEW)"
)

rql(
    "SET S same_as NEW WHERE OLD grouped_with NEW, S same_as OLD, NOT EXISTS(NEW same_as S), NOT EXISTS (S same_as NEW)"
)
