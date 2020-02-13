# flake8: noqa
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

STYLESHEETS[:] = [
    data("css/bootstrap.min.css"),
    data("css/font-awesome.css"),
    data("css/francearchives.bundle.css"),
    data("jquery-typeahead/jquery.typeahead.min.css"),
]

# don't use ``JAVASCRIPTS`` since CW will automatically add
# ``cubicweb.js`` to it.
PNIA_JAVASCRIPTS = [
    data("jquery-3.1.1.min.js"),
    data("jquery-typeahead/jquery.typeahead.min.js"),
    data("cubes.pnia_portal.js"),
]  # noqa

# to be removed
ARCHIVES_TOPIC = data("images/body_topics_imagespace-440x295px.jpg")
ARCHIVES_NEWS = data("images/body_timeline_info-image-535x235.jpg")
DOCUMENT_IMG = data("images/FranceArchives_NoImage-narrow.jpg")
# country (languages) flags

FLAG_FR = data("images/header_topbar_language-france.png")
FLAG_EN = data("images/header_topbar_language-united-kingdom.png")
FLAG_DE = data("images/header_topbar_language-germany.png")
FLAG_ES = data("images/header_topbar_language-spain.png")

PICTO_DOCTYPE_DEFAULT = data("images/body_document.png")
# PICTO_DOCTYPE_FACOMPONENT = data('images/body_highlights_item3-gerer.png')
# PICTO_DOCTYPE_FINDINGAID = data('images/body_highlights_item3-gerer.png')
PICTO_DOCTYPE_ARCHIVES = data("images/body_highlights_item3-gerer.png")

# XXX to be removed
ARCHIVES_TOPIC = data("images/body_topics_imagespace-440x295px.jpg")
