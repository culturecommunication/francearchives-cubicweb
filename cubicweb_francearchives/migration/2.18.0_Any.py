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

logger = logging.getLogger("francearchives.migration")
logger.info("update Service dpt_code from code_insee_commune if exists")

updated = 0
for service in rql(
    """Any X, C WHERE X is Service, X code_insee_commune C, X dpt_code D"""
).entities():
    if not service.dpt_code:
        code = None
        if service.code_insee_commune:
            code_insee = service.code_insee_commune.strip()
            if code_insee[:2] in ("2A", "2B"):
                code = "20"
                service.cw_set(dpt_code=code)
                updated = +1
                continue
            if not code_insee.isdigit():
                logger.warning("Service code_insee_commune is not a number")
                continue
            if int(code_insee[:2]) < 96:
                code = code_insee[:2]
            if int(code_insee[:2]) > 96:
                code = code_insee[:3]
            if code:
                service.cw_set(dpt_code=code)
                updated = +1

cnx.commit()
logger.info("updated %s Services", updated)

logger.info("-> Create table blacklisted_authorities")
cnx.system_sql(
    """
    CREATE TABLE IF NOT EXISTS blacklisted_authorities (
    label varchar(2048) PRIMARY KEY NOT NULL
    );
    """
)

commit()

logger.info("Modify Service categories")

logger.info(
    "-> move level-Z (Services interministériels) servicies to level-Y 'Ministère de la Culture'"
)

cnx.execute("SET X level 'level-Y' WHERE X level 'level-Z'")

logger.info("-> move level-O to level-E 'Institutions privées'")

cnx.execute("SET X level 'level-E' WHERE X level 'level-O'")

commit()

logger.info(
    "-> remove level-Z (Services interministériels) end level-O Organismes liés aux archives ou organismes internationaux"
)

sync_schema_props_perms("Service")
commit()

context = "archiviste_hp_links"
label_fr = "Notices producteurs"
if not cnx.find("SiteLink", context=context, label_fr=label_fr):
    logger.info("-> Create SiteLink for authority")
    order = (
        rql("Any MAX(O) WHERE X is SiteLink, X context %(c)s, X order O", {"c": context})[0][0] or 0
    )
    kwargs = {
        "context": "archiviste_hp_links",
        "link": "authorityrecord",
        "label_fr": label_fr,
        "label_en": "Record creators",
        "label_es": label_fr,
        "label_de": label_fr,
        "order": order + 1,
    }
    cnx.create_entity("SiteLink", **kwargs)
