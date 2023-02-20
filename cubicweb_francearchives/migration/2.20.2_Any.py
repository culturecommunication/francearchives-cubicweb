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

logger = logging.getLogger("francearchives.migration")
logger.setLevel(logging.INFO)

logger.info("add iiif_extptr attribute to Service. For now it is only meant for LIGEO services")

add_attribute("Service", "iiif_extptr")

cnx.commit()

IIIF_EXTPTR = (
    "FRAD002",
    "FRAD005",
    "FRAD033",
    "FRAD034",
    "FRAD074",
    "FRAD079",
    "FRAD086",
    "FRAD089",
    "FRAD092",
    "FRAC89024",
    "FRAC29103",
    "FRAMAP",
    "FRAM059MEL",
)

logger.info("set LIGEO services")

with cnx.allow_all_hooks_but("es", "sync", "varnish"):
    cnx.execute(
        "SET X iiif_extptr True WHERE X is Service, X code IN ({})".format(
            ",".join('"{}"'.format(e) for e in IIIF_EXTPTR)
        )
    )

cnx.commit()
