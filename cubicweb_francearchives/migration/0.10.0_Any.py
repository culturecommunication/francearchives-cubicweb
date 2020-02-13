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

from cubicweb_francearchives import SUPPORTED_LANGS
from cubicweb_francearchives.dataimport.directories import get_dpt_code

print("import FRSHD annexes")

headers = [
    "code",
    "page",
    "category",
    "annex_of",
    "name",
    "level",
    "name2",
    "address",
    "zip_code",
    "city",
    "mailing_address",
    "website_url",
    "contact_name",
    "phone_number",
    "fax",
    "email",
    "annual_closure",
    "opening_period",
    "rss",
    "daylmotion",
    "scoop it",
    "pinterest",
    "vimeo",
    "twitter",
    "storify",
    "foursquare",
    "facebook",
    "youtube",
    "wikimédia",
    "flickr",
    "blogs",
    "instagram",
]

annexes = [
    [
        "",
        "",
        "Présidence de la République et Ministères",
        "Ministère de la Défense - SHD",
        "",
        "M",
        "Centre historique des archives",
        "Château de Vincennes, avenue de Paris",
        "94300",
        "Vincennes",
        "Château de Vincennes, avenue de Paris, 94306 Vincennes Cedex",
        "",
        "Thierry Sarmant",
        "01.41.93.23.57",
        "01.41.93.43.00",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
    ],
    [
        "",
        "",
        "Présidence de la République et Ministères",
        "Ministère de la Défense - SHD",
        "",
        "M",
        "Centre des archives de l'armement et du personnel",
        "",
        "",
        "",
        "211 Grande Rue de Châteauneuf, CS 50650, 86106 Châtellerault Cedex",
        "",
        "Commissaire en chef Nicolas Jacob",
        "05.49.20.01.20",
        "05.49.20.22.39",
        "dmpa-shd-caapc.recherches.fct@intradef.gouv.fr",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
    ],
    [
        "",
        "",
        "Présidence de la République et Ministères",
        "Ministère de la Défense - SHD",
        "",
        "M",
        "Centre des archives du personnel militaire",
        "",
        "",
        "",
        "Caserne Bernadotte, place de Verdun, 64023 Pau Cedex",
        "",
        "Lieutenant-colonel Patrick Rongier",
        "05.59.40.46.92",
        "05.49.40.45.53",
        "capm-pau.courrier.fct@intradef.gouv.fr",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
    ],
]

shd_service = cnx.find("Service", code="FRSHD").one()

for row in annexes:
    data = dict((k, v.decode("utf-8").strip()) for k, v in zip(headers, row) if v)
    data["annex_of"] = shd_service.eid
    if "zip_code" in data:
        zip_code = data.pop("zip_code")
        dpt_code = get_dpt_code(zip_code)
        data["dpt_code"] = dpt_code
    level = data["level"]
    if level:
        data["level"] = "level-%s" % level
    cnx.create_entity("Service", **data)


for wikiid, title in (
    ("open_data", "Open data"),
    ("emplois", "Offres d'emplois"),
    ("about", "A propos"),
):
    for lang in SUPPORTED_LANGS:
        create_entity(
            "Card", wikiid="%s-%s" % (wikiid, lang), title=title, content_format="text/html"
        )
commit()
