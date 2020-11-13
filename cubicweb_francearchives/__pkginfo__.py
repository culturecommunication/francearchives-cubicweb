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
"""cubicweb-francearchives application packaging information"""

modname = "francearchives"
distname = "cubicweb-francearchives"

numversion = (2, 9, 2)
version = ".".join(str(num) for num in numversion)

license = "CeCILL-C"
author = "LOGILAB S.A. (Paris, FRANCE)"
author_email = "contact@logilab.fr"
description = "FranceArchives"
web = "https://github.com/culturecommunication/francearchives-cubicweb-edition"

__depends__ = {
    "pyramid": None,
    "cubicweb[pyramid,crypto]": ">= 3.26.0,<3.27.0",
    "cubicweb-file": ">= 2.3.0",
    "cubicweb-link": ">= 1.8.0",
    "cubicweb-eac": ">= 0.9.1",
    "cubicweb-prov": ">= 0.4.0",
    "cubicweb-skos": None,
    "cubicweb-elasticsearch": ">= 0.8.0",
    "cubicweb-varnish": ">= 0.5.1",
    "cubicweb-card": ">= 1.1.2",
    "cubicweb-sentry": None,
    "sentry-sdk": None,
    "sickle": ">= 0.7.0",
    "glamconv": ">= 0.1.8",
    "cubicweb-oaipmh": ">= 0.6.1",
    "cwtags": ">= 1.1.0",
    "rdflib": ">= 4.2.0",
    "rdflib-jsonld": None,
    "jinja2": None,
    "babel": None,
    "PyYAML": None,
    "pillow": None,
    "requests": None,
    "urllib3": "> 1.21.1,<1.25",
    "psycopg2": None,
    "vobject": ">= 0.9.3",
    "tqdm": None,
}

classifiers = [
    "Environment :: Web Environment",
    "Framework :: CubicWeb",
    "Programming Language :: Python",
    "Programming Language :: JavaScript",
    "License :: CeCILL-C Free Software License Agreement (CECILL-C)",
]
