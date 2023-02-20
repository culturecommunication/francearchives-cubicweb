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

import logging

from cubicweb_francearchives.dataimport.oai import parse_oai_url
from cubicweb_francearchives.migration.utils import add_column_to_published_table

logger = logging.getLogger("francearchives.migration")
logger.setLevel(logging.INFO)

logger.info("add NominaRecord")
add_entity_type("NominaRecord")
add_relation_definition("AgentAuthority", "same_as", "NominaRecord")

logger.info("add periodical_import on OAIRepository")

add_attribute("OAIRepository", "periodical_import")

for repo, url in cnx.execute(
    """Any X, U WHERE X is OAIRepository, X url U"""
).iter_rows_with_entities():
    if url:
        base_url, params = parse_oai_url(url.strip())
        if params.get("metadataPrefix") == "nomina":
            continue
        else:
            repo.cw_set(periodical_import=True)

cnx.commit()

logger.info("add last_successful_import attribute on OAIRepository")

add_attribute("OAIRepository", "last_successful_import")

for repo, oai_import in cnx.execute(
    """Any X, OIT WHERE X is OAIRepository,
       OIT oai_repository X, OIT in_state S,
       S name "wfs_oaiimport_completed" """
).iter_rows_with_entities():
    wf = oai_import.cw_adapt_to("IWorkflowable")
    repo.cw_set(last_successful_import=wf.latest_trinfo().creation_date)

cnx.commit()

logger.info("drop Person definition")
with cnx.allow_all_hooks_but("es", "sync", "varnish", "reindex-suggest-es"):
    drop_entity_type("Person")


print("-> add header, on_homepage, on_homepage_order attributes)")


for etype in ("ExternRef",):
    add_column_to_published_table(cnx, etype.lower(), "header", "character varying(500)")
    add_attribute(etype, "header")
    add_column_to_published_table(cnx, etype.lower(), "on_homepage", "character varying(11)")
    add_attribute(etype, "on_homepage")
    add_column_to_published_table(cnx, etype.lower(), "on_homepage_order", "integer")
    add_attribute(etype, "on_homepage_order")

commit()
