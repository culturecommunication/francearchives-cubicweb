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

from cubicweb.predicates import is_instance

from cubicweb.view import EntityAdapter

from cubicweb_file.entities import FileIDownloadableAdapter

from cubicweb_francearchives.views import load_portal_config
from cubicweb_francearchives.views.xiti import pagename_from_chapters


class FAFileAdapter(FileIDownloadableAdapter):
    def ape_service_code(self):
        rset = self._cw.execute(
            "Any C WHERE FA ape_ead_file X, X eid %(e)s, " "FA service S, S code C",
            {"e": self.entity.eid},
        )
        if rset:
            return rset[0][0]

    def download_url(self, **kwargs):
        service_code = self.ape_service_code()
        name = self._cw.url_quote(self.download_file_name())
        rest_path = self.entity.rest_path()
        if service_code:
            path = "%s/ape-ead/%s/%s" % (rest_path, service_code, name)
        else:
            path = "%s/%s" % (rest_path, name)
        return self._cw.build_url(path, **kwargs)

    def download_file_name(self):
        return self.entity.data_name


class IPublisherInfoAdapter(EntityAdapter):
    __regid__ = "IPublisherInfo"
    __abstract__ = True

    @property
    def service(self):
        return self.entity.related_service

    @property
    def publisher_title(self):
        return self.entity.publisher_title

    @property
    def bounce_url(self):
        return self.entity.bounce_url

    @property
    def publisher_label(self):
        return self._cw._("Conservation institutions: ")

    @cachedproperty
    def portal_config(self):
        return load_portal_config(self._cw.vreg.config)

    def serialize(self):
        _ = self._cw._
        service = self.service
        publisher_params = {}
        if service:
            contact_url = service.url_anchor
            publisher_params = {
                "contact_url": contact_url,
                "contact_label": _("Contact_label"),
            }
            ixiti = service.cw_adapt_to("IXiti")
            xiti_config = self.portal_config.get("xiti")
            if xiti_config and ixiti is not None:
                publisher_params["xiti"] = {
                    "type": "S",
                    "n2": xiti_config.get("n2", ""),
                    "access_site": pagename_from_chapters(ixiti.chapters + ["site_access"]),
                    "thumbnail_access_site": pagename_from_chapters(
                        ixiti.chapters + ["thumbnail_site_access"]
                    ),
                }
        publisher_params["title"] = self.publisher_title
        publisher_params["title_label"] = self.publisher_label
        if self.bounce_url:
            publisher_params.update(
                {"site_label": _("Access to the site"), "site_url": self.bounce_url}
            )
        return publisher_params


class IRIPublisherInfoAdapter(IPublisherInfoAdapter):
    __select__ = is_instance("FindingAid", "FAComponent")


class AuthorityRecordIPublisherInfoAdapter(IPublisherInfoAdapter):
    __select__ = IPublisherInfoAdapter.__select__ & is_instance("AuthorityRecord")

    @property
    def publisher_label(self):
        return self._cw._("Notice author :")

    @property
    def publisher_title(self):
        return self.service.dc_title()

    @property
    def bounce_url(self):
        return False


class EntityMainPropsAdapter(EntityAdapter):
    __regid__ = "entity.main_props"
    __abstract__ = True

    def properties(self, export=False, vid="incontext", text_format="text/html"):
        raise NotImplementedError()


def registration_callback(vreg):
    for adapter in (IRIPublisherInfoAdapter, AuthorityRecordIPublisherInfoAdapter):
        vreg.register(adapter)
    vreg.register_and_replace(FAFileAdapter, FileIDownloadableAdapter)
