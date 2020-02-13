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

"""cubicweb-pnia-content adapter's classes"""

import vobject

from logilab.common.decorators import cachedproperty

from cubicweb import _
from cubicweb.view import EntityAdapter
from cubicweb.predicates import is_instance
from cubicweb.entities.adapters import ITreeAdapter

from cubicweb_francearchives import FIRST_LEVEL_SECTIONS

from cubicweb_francearchives.schema.cms import CMS_OBJECTS
from cubicweb_francearchives.views import format_date


class ITemplatableApdater(EntityAdapter):
    __select__ = is_instance("Any")
    __regid__ = "ITemplatable"

    def entity_param(self):
        return self.entity


class CommemoITemplatable(ITemplatableApdater):
    __select__ = ITemplatableApdater.__select__ & is_instance("CommemorationItem")

    def entity_param(self):
        entity = self.entity
        if entity.manif_prog:
            entity.manif_prog_content = entity.manif_prog[0].content
        else:
            entity.manif_prog_content = ""
        return entity


class CMSObjectITreeAdapter(ITreeAdapter):
    __regid__ = "ITree"
    __select__ = ITreeAdapter.__select__ & is_instance(*CMS_OBJECTS)
    tree_relation = "children"

    child_role = "object"
    parent_role = "subject"

    @cachedproperty
    def main_section(self):
        section_name = self.root().name
        if section_name in FIRST_LEVEL_SECTIONS:
            return section_name
        return "home"


class Service2VcardAdapater(EntityAdapter):
    __regid__ = "vcard"

    def properties(self):
        entity = self.entity
        props = {
            "n": vobject.vcard.Name(given=entity.dc_title()),
            "fn": entity.dc_title(),
            "nickname": entity.code,
            "email": entity.email,
            "agent": entity.contact_name,
            "tel": entity.phone_number,
            "tel.fax": entity.fax,
            "adr": vobject.vcard.Address(
                street=(entity.address or ""),
                city=(entity.city or ""),
                code=(entity.zip_code or ""),
                country="FR",
            ),
            "url": entity.website_url,
            "note": entity.opening_period,
            "uid": entity.uuid,
        }
        if entity.service_image:
            imgfile = entity.service_image[0].image_file[0]
            props["logo"] = imgfile.cw_adapt_to("IDownloadable").download_url()
        return props

    def vcard(self):
        props = self.properties()
        card = vobject.vCard()
        for key, value in list(props.items()):
            if not value:
                continue
            try:
                key, value_type = key.split(".")
            except ValueError:
                value_type = None
            card.add(key)
            propvalue = getattr(card, key)
            propvalue.value = value
            if value_type is not None:
                propvalue.type_param = value_type
            # XXX uuid
        return card


class Absctract2CSV(EntityAdapter):
    __abstract__ = True
    __regid__ = "csv-props"
    headers = []

    def properties():
        return {}

    def csv_row(self):
        props = self.properties()
        return [(props[h] or "") for h in self.headers]


class Service2CSV(Absctract2CSV):
    __select__ = EntityAdapter.__select__ & is_instance("Service")

    headers = (
        "name",
        "email",
        "telephone",
        "postal_address",
        "address",
        "city",
        "postalcode",
        "openinghours",
        "website_url",
        "francearchives_url",
        "service_type",
        "service_type_label",
        "parent_organization",
    )

    def properties(self):
        entity = self.entity
        props = {
            "name": entity.dc_title(),
            "email": entity.email,
            "agent": entity.contact_name,
            "telephone": entity.phone_number,
            "fax": entity.fax,
            "address": entity.address,
            "postal_address": entity.mailing_address,
            "city": entity.city,
            "postalcode": entity.zip_code,
            "openinghours": entity.opening_period,
            "website_url": entity.website_url,
            "francearchives_url": entity.absolute_url(),
            "service_type": entity.level.rsplit("-", 1)[-1] if entity.level else None,
            "service_type_label": self._cw._(entity.level) if entity.level else None,
            "parent_organization": entity.annex_of[0].dc_title() if entity.annex_of else None,
        }
        return props


class Circular2CSV(Absctract2CSV):
    __regid__ = "csv-props"
    __select__ = EntityAdapter.__select__ & is_instance("Circular")

    def file_url(self, cwfile, prod_url):
        url = cwfile.cw_adapt_to("IDownloadable").download_url()
        base_url = self._cw.base_url()
        if url and base_url:
            return url.replace(base_url, prod_url)
        return ""

    def properties(self):
        self.entity.complete()
        entity = self.entity
        translate = self._cw._
        prod_url = "{}/".format(self._cw.vreg.config.get("consultation-base-url"))
        return (
            (_("circular_title_label"), entity.dc_title()),
            (_("circular_url"), "{}{}".format(prod_url, self.entity.rest_path())),
            (_("circular_circ_id_label"), entity.circ_id),
            (_("circular_kind_label"), entity.kind),
            (_("circular_code_label"), entity.code),
            (_("circular_nor_label"), entity.nor),
            (_("circular_status_label"), translate(entity.status)),
            (_("circular_link_label"), entity.link),
            (_("circular_additional_link_label"), "; ".join(e.url for e in entity.additional_link)),
            (
                _("circular_attachment_label"),
                "; ".join(self.file_url(e, prod_url) for e in entity.attachment),
            ),
            (
                _("circular_additional_attachment_label"),
                "; ".join(self.file_url(e, prod_url) for e in entity.additional_attachment),
            ),
            (_("circular_signing_date_label"), format_date(entity.signing_date, self._cw)),
            (_("circular_siaf_daf_kind_label"), entity.siaf_daf_kind),
            (_("circular_siaf_daf_code_label"), entity.siaf_daf_code),
            (
                _("circular_siaf_daf_signing_date_label"),
                format_date(entity.siaf_daf_signing_date, self._cw),
            ),
            (_("circular_producer_label"), entity.producer),
            (_("circular_producer_acronym_label"), entity.producer_acronym),
            (
                _("circular_modification_date_label"),
                format_date(entity.circular_modification_date, self._cw),
            ),
            (_("circular_abrogation_date_label"), format_date(entity.abrogation_date, self._cw)),
            (_("circular_abrogation_text_label"), entity.abrogation_text),
            (_("circular_archival_field_label"), entity.archival_field),
            (
                _("circular_historical_context_label"),
                "; ".join(e.dc_title() for e in entity.historical_context),
            ),
            (
                _("circular_business_field_label"),
                "; ".join(e.dc_title() for e in entity.business_field),
            ),
            (
                _("circular_document_type_label"),
                "; ".join(e.dc_title() for e in entity.document_type),
            ),
            (_("circular_action_label"), "; ".join(e.dc_title() for e in entity.action)),
            (
                _("circular_modified_text_label"),
                "; ".join(e.dc_title() for e in entity.modified_text),
            ),
            (
                _("circular_modifying_text_label"),
                "; ".join(e.dc_title() for e in entity.modifying_text),
            ),
            (
                _("circular_revoked_text_label"),
                "; ".join(e.dc_title() for e in entity.revoked_text),
            ),
        )

    def csv_row(self):
        return self.properties()
