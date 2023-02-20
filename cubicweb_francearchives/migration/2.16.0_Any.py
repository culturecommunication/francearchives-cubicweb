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

print("-> add Dao on FindingAid")
add_relation_definition("FindingAid", "digitized_versions", "DigitizedVersion")

from cubicweb_francearchives.migration.utils import (
    add_column_to_published_table,
    drop_column_from_published_table,
)

print("-> add stop_year on CommemorationItem")

add_attribute("CommemorationItem", "stop_year")
cnx.commit()

add_column_to_published_table(cnx, "CommemorationItem", "stop_year", "integer")
cnx.commit()

years = [(eid, year) for eid, year in rql("Any X, Y WHERE X is CommemorationItem, X year Y")]

print("-> add start_year on CommemorationItem")

add_attribute("CommemorationItem", "start_year")
add_column_to_published_table(cnx, "CommemorationItem", "start_year", "integer")
cnx.commit()

with cnx.allow_all_hooks_but("es", "sync", "varnish"):
    for eid, year in years:
        if year is not None:
            rql("SET X start_year %(y)s WHERE X eid %(e)s", {"e": eid, "y": year})

cnx.commit()

print("-> drop_year on CommemorationItem")

drop_attribute("CommemorationItem", "year")
drop_column_from_published_table(cnx, "CommemorationItem", "year")
cnx.commit()


start_years = rql("Any COUNT(X) WHERE X is CommemorationItem, X start_year Y")[0][0]

print(f"Expected {len(years)} start_years, found {start_years}")
