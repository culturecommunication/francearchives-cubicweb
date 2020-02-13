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
from logilab.common.decorators import cachedproperty

from cubicweb.entities import fetch_config

from cubicweb_francearchives.entities.cms import CmsObject


class CommemoCollection(CmsObject):
    __regid__ = "CommemoCollection"
    fetch_attrs, cw_fetch_order = fetch_config(
        ["order", "title", "subtitle", "content", "short_description", "year"], order="DESC"
    )
    image_rel_name = "section_image"

    def rest_path(self, use_ext_eid=False):
        return "commemo/recueil-{}/".format(self.year)

    def breadcrumbs_title(self):
        return self.dc_title()


class CommemorationItem(CmsObject):
    __regid__ = "CommemorationItem"
    image_rel_name = "commemoration_image"

    @cachedproperty
    def collection(self):
        return self.collection_top[0]

    def rest_path(self, use_ext_eid=False):
        return "commemo/recueil-{}/{}".format(self.commemoration_year, self.eid)

    def author_indexes(self):

        return self._cw.execute(
            "DISTINCT Any X, XL WHERE E eid %(e)s, " "E related_authority X, X label XL",
            {"e": self.eid},
        )
