# -*- coding: utf-8 -*-
#
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2019
# Contact http://www.logilab.fr -- mailto:contact@logilab.fr
#
# flake8: noqa
# -*- coding: utf-8 -*-
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

from cubicweb_francearchives.dataimport.ead import ead_foreign_key_tables
from cubicweb_francearchives.migration.utils import alter_published_table

# related to #62520518

add_attribute("Service", "thumbnail_dest")
query = "SET S thumbnail_dest %(url)s WHERE S is Service, S code %(code)s"
thumbnail_dests = [{"url": "http://v-earchives.vaucluse.fr/viewer/{url}", "code": "FRAD084"}]

with cnx.deny_all_hooks_but():
    for thumbnail_dest in thumbnail_dests:
        rql(query, thumbnail_dest)

with sqlutil.sudocnx(cnx, interactive=False) as su_cnx:
    foreign_key_tables = ead_foreign_key_tables(cnx.vreg.schema)
    sqlutil.disable_triggers(su_cnx, foreign_key_tables)
    etype = "FindingAid"
    attr = "website_url"
    add_attribute(etype, attr)
    alter_published_table(cnx, etype, attr, "text")
    cnx.commit()
    sqlutil.enable_triggers(su_cnx, foreign_key_tables)
