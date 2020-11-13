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


from cwtags import tag as T

from logilab.mtconverter import xml_escape
from logilab.common.decorators import cachedproperty

from cubicweb import _
from cubicweb.utils import json_dumps
from cubicweb.schema import display_name
from cubicweb.predicates import is_instance, empty_rset, one_line_rset, none_rset
from cubicweb.view import View, EntityView
from cubicweb.web.views.primary import PrimaryView, URLAttributeView

from cubicweb_francearchives.utils import merge_dicts, id_for_anchor
from cubicweb_francearchives.views import JinjaViewMixin, get_template, blank_link_title


def all_services(req):
    return req.execute(
        "Any X, D, N ORDERBY Z WHERE X is Service, X dpt_code D, "
        'X zip_code Z, X name N, X level "level-D", NOT X annex_of Y'
    ).entities()


class SocialNetworkUrLAttributeView(URLAttributeView):
    """ open the url in a new tab"""

    __select__ = URLAttributeView.__select__ & is_instance("SocialNetwork")

    def entity_call(self, entity, rtype="subject", **kwargs):
        url = entity.printable_value(rtype)
        if url:
            url = xml_escape(url)
            self.w(
                T.a(
                    entity.name,
                    href=url,
                    target="_blank",
                    title=blank_link_title(self._cw, url),
                    rel="nofollow noopener noreferrer",
                )
            )


class DeptMapForm(object):
    template = get_template("dpt-map-form.jinja2")

    map_defaults = {"disabledRegions": ["97133"]}

    def __init__(self, custom_settings=None):
        self.map_settings = merge_dicts({}, self.map_defaults, custom_settings or {})

    def render(self, req, services, selected_dpt=None):
        req.add_js("jqvmap/jquery.vmap.js")
        req.add_js("jqvmap/jquery.vmap.dpt.js")
        req.add_js("cubes.pnia_map.js")
        req.add_css("jqvmap/jqvmap.css")
        self.init_onload(req)
        return self.template.render(
            _=req._, base_url=req.base_url(), services=services, selected_dpt=selected_dpt
        )

    def init_onload(self, req):
        jscmd = "$('#dpt-vmap').dptMap(%s);" % (json_dumps(self.map_settings))
        req.add_onload(jscmd)


class AbstractDptServiceMapView(JinjaViewMixin, View):
    __abstract__ = True
    __regid__ = "dpt-service-map"
    template = get_template("dpt-map.jinja2")
    title = None

    def call(self):
        _ = self._cw._
        b_url = self._cw.build_url
        breadcrumbs = [(b_url(""), _("Home"))]
        breadcrumbs.append((b_url("services"), _("Service Directory")))
        title = self.title
        if title:
            breadcrumbs.append((b_url("annuaire/departements"), title))
        dept_map_form = DeptMapForm()
        render = dept_map_form.render(self._cw, all_services(self._cw), self.selected_service())
        ctx = {
            "breadcrumbs": breadcrumbs,
            "map_form": render,
            "service_directory_content": self.service_directory_content(),
        }
        return self.call_template(**ctx)

    def service_directory_content(self):
        return ""

    def selected_service(self):
        raise NotImplementedError()


class NoDepartmentMapView(AbstractDptServiceMapView):
    """XXX add a message for users?"""

    __select__ = empty_rset() | none_rset()

    @cachedproperty
    def xiti_chapters(self):
        return ["department_map"]

    @property
    def title(self):
        return self._cw._("Archives Departementales")

    def selected_service(self):
        return None


class DepartmentMapView(AbstractDptServiceMapView):
    __select__ = one_line_rset() & is_instance("Service")

    @property
    def title(self):
        return self.cw_rset.one().name

    def service_directory_content(self):
        return self._cw.view("primary", rset=self.cw_rset)

    def selected_service(self):
        return self.cw_rset.one().dpt_code


class MainInfo(EntityView):
    __regid__ = "service-maininfo"
    __select__ = EntityView.__select__ & is_instance("Service")

    def render_fa_components_link(self, entity):
        anyfa = self._cw.execute(
            "Any 1 WHERE EXISTS(F service X, NOT X code NULL, X eid %(e)s)", {"e": entity.eid}
        )
        if anyfa:
            title = self._cw._("see service related documents")
            self.w(T.a(title, href=xml_escape(entity.documents_url())))

    def render_physical_address(self, entity):
        address = [
            ("streetAddress", entity.address),
            ("postalCode", entity.zip_code),
            ("addressLocality", entity.city),
        ]
        address_tags = []
        for prop, value in address:
            if value:
                address_tags.append(str(T.span(value, itemprop=prop)))
        address_tags = [
            ", ".join((address_tags)),
            str(T.meta(content="fr", itemprop="addressCountry")),
        ]
        return str(
            T.div(
                *address_tags,
                itemprop="address",
                itemscope="itemscope",
                itemtype="http://schema.org/PostalAddress"
            )
        )

    def render_parent_service(self, parent):
        return str(
            T.div(
                T.span(parent.dc_title(), itemprop="legalName"),
                itemprop="parentOrganization",
                itemscope="itemscope",
                itemtype="http://schema.org/Organization",
            )
        )

    def render_hidden_microdata(self, entity):
        """those data are hidden from html"""
        if entity.fax:
            self.w(T.meta(content=entity.fax, itemprop="faxNumber"))
        for child in entity.reverse_annex_of:
            self.w(
                T.meta(
                    content=child.absolute_url(),
                    itemprop="subOrganization",
                    itemscope="itemscope",
                    itemtype="http://schema.org/Organization",
                )
            )

    def entity_call(self, entity):
        with T.section(
            self.w,
            klass="service-info",
            itemscope="itemscope",
            itemtype="http://schema.org/Organization",
        ):
            self.w(
                T.h2(entity.dc_title(), itemprop="legalName", id=id_for_anchor(entity.dc_title()))
            )
            website_link, email_link = None, None
            website_url = entity.printable_value("website_url")
            if website_url:
                website_link = str(
                    T.a(
                        website_url,
                        href=website_url,
                        target="_blank",
                        title=blank_link_title(self._cw, website_url),
                        rel="nofollow noopener noreferrer",
                    )
                )
            else:
                website_link = None
            address = entity.physical_address()
            zip_code = entity.zip_code
            if zip_code and str(zip_code) == address:
                zip_code = None
            email = entity.printable_value("email")
            if email:
                email_link = str(T.a(T.span(email, itemprop="email"), href="mailto:%s" % email))
            contact_label = _("director") if entity.level == "level-D" else _("contact_name")
            contact_name = entity.printable_value("contact_name")
            if contact_name:
                contact_name = str(T.span(contact_name, itemprop="employee"))
            phone_number = entity.printable_value("phone_number")
            if phone_number:
                phone_number = str(T.span(phone_number, itemprop="telephone"))
            opening_period = entity.printable_value("opening_period")
            if opening_period:
                opening_period = str(T.span(opening_period, itemprop="openinghours"))
            if entity.annex_of:
                main_service = entity.annex_of[0]
                main_service_link = self.render_parent_service(main_service)
            else:
                main_service_link = None
            address = entity.address
            if address:
                address = self.render_physical_address(entity)
            with T.dl(self.w, klass="dl-horizontal"):
                for attr, value in (
                    (_("main_service"), main_service_link),
                    (contact_label, contact_name),
                    (_("phone_number"), phone_number),
                    (_("email"), email_link),
                    (_("address"), address),
                    (_("write to us"), entity.mailing_address),
                    (_("zip_code"), entity.zip_code),
                    (_("opening_period"), opening_period),
                    (_("annual_closure"), entity.printable_value("annual_closure")),
                    (_("website_url"), website_link),
                    (
                        _("service_social_network"),
                        ", ".join(
                            e.view("urlattr", rtype="url") for e in entity.service_social_network
                        ),
                    ),
                ):
                    if value:
                        self.w(T.dt(display_name(self._cw, attr, context="Service")))
                        self.w(T.dd(value))
            other = entity.printable_value("other")
            if other:
                self.w(other)
            self.render_fa_components_link(entity)
            self.render_hidden_microdata(entity)


class Service(PrimaryView):
    __select__ = PrimaryView.__select__ & is_instance("Service")

    def render_entity_title(self, entity):
        self.w(T.h1(entity.name or ""))

    def _prepare_side_boxes(self, entity):
        return ()

    def content_navigation_components(self, context):
        pass

    def render_entity_attributes(self, entity):
        entity.view("service-maininfo", w=self.w)

    def render_entity_relations(self, entity):
        # service annexes
        rset = entity.related("annex_of", "object")
        if rset:
            with T.section(self.w):
                self.wview("service-maininfo", rset=rset)
        if entity.level != "level-D":
            return
        rset = self._cw.execute(
            "Any X ORDERBY N WHERE X category C, "
            "Y category C, "
            "X name N, "
            "X level %(l)s, "
            "Y eid %(e)s, NOT X annex_of Z, "
            "NOT X identity Y",
            {"e": entity.eid, "l": "level-C"},
        )
        if rset:
            with T.section(self.w, id="archives-services"):
                # XXX remove name2 attibute for Service?
                entities = sorted(rset.entities(), key=lambda x: x.name or x.name2)
                for e in entities:
                    self.w(e.view("service-maininfo"))
                    rset = e.related("annex_of", "object")
                    if rset:
                        self.wview("service-maininfo", rset=rset)
