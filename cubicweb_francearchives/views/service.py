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
from cubicweb.utils import json_dumps, UStringIO
from cubicweb.schema import display_name
from cubicweb.predicates import is_instance, empty_rset, one_line_rset, none_rset
from cubicweb.view import View, EntityView
from cubicweb.web.views.primary import PrimaryView, URLAttributeView

from cubicweb_francearchives.entities.rdf import RDF_FORMAT_EXTENSIONS
from cubicweb_francearchives.utils import merge_dicts
from cubicweb_francearchives.views import JinjaViewMixin, get_template, blank_link_title


def all_services(req):
    return req.execute(
        "Any X, D, N, LAT, LONG ORDERBY Z WHERE X is Service, X dpt_code D, "
        'X zip_code Z, X name N, X level "level-D", NOT X annex_of Y, '
        "X latitude LAT, X longitude LONG"
    ).entities()


class SocialNetworkUrLAttributeView(URLAttributeView):
    """open the url in a new tab"""

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


class DeptGeoMapForm(object):
    template = get_template("dpt-map-geo-form.jinja2")

    def render(self, req, services, selected_dpt=None):
        req.add_js("cubes.pnia_map.js")
        return self.template.render(
            _=req._, base_url=req.base_url(), services=services, selected_dpt=selected_dpt
        )


class LeafletServiceMapView(JinjaViewMixin, View):
    __regid__ = "leaflet-service-map"
    template = get_template("services-leaflet-map.jinja2")

    def add_css(self):
        for css in (
            "leaflet.css",
            "LeafletStyleSheet.css",
            "MarkerCluster.Default.css",
        ):
            self._cw.add_css(css)

    def add_js(self):
        for js in (
            "leaflet.js",
            "leaflet-sidebar.min.js",
            "leaflet.markercluster.js",
            "bundle-pniaservices-map.js",
            "leaflet.zoomhome.min.js",
        ):
            self._cw.add_js(js)

    def call(self):
        _ = self._cw._
        self.add_css()
        self.add_js()
        dept_map_form = DeptGeoMapForm()
        dpt = self._cw.form.get("dpt")
        if not isinstance(dpt, str):
            # dpt must by a string, not a list
            dpt = ""
        render = dept_map_form.render(self._cw, all_services(self._cw), dpt)
        self.call_template(
            map_form=render,
            markerurl=self._cw.build_url("services-map.json", dpt=self._cw.form.get("dpt", "")),
            geojson=self._cw.data_url("departements-version-simplifiee.geojson"),
            zoom=self._cw.form.get("zoom", ""),
            _=self._cw._,
            labels={
                "contact": _("Contact"),
                "address": _("Address"),
                "phone": _("Phone number"),
                "email": _("Email"),
                "mailing_address": _("Write to us"),
                "website": _("Website"),
                "code_insee": _("Code INSEE commune"),
                "opening": _("Opening period"),
                "annual_closure": _("Annual closure"),
                "coordinates": _("GPS coordinates"),
                "social_network": _("SocialNetwork_plural"),
                "useful_info": _("Useful information"),
                "fa_link": _("see service related documents"),
                "nomina_link": _("see service related nominarecords"),
            },
        )


class AbstractDptServiceMapView(JinjaViewMixin, View):
    __abstract__ = True
    __regid__ = "dpt-service-map"
    template = get_template("services-map.jinja2")
    title = None

    def call(self):
        _ = self._cw._
        b_url = self._cw.build_url
        breadcrumbs = [(b_url(""), _("Home"))]
        breadcrumbs.append((b_url("services"), _("Service Directory")))
        title = self.title
        if title:
            breadcrumbs.append((b_url("annuaire/departements"), title))
        self.call_template(
            _=_,
            title=self.title,
            a11y_alert=self.a11y_alert,
            mobile_alert=self._cw._("map_mobile_alert"),
            breadcrumbs=breadcrumbs,
            service_directory_content=self.service_directory_content(),
            map=self._cw.view("leaflet-service-map", rset=self.cw_rset),
        )

    def service_directory_content(self):
        return ""

    def selected_service(self):
        raise NotImplementedError()

    @property
    def a11y_alert(self):
        return None


class NoDepartmentMapView(AbstractDptServiceMapView):
    """XXX add a message for users?"""

    __select__ = empty_rset() | none_rset()

    @cachedproperty
    def xiti_chapters(self):
        return ["department_map"]

    @property
    def title(self):
        return self._cw._("All services")

    def selected_service(self):
        return None

    @property
    def a11y_alert(self):
        return self._cw._("a11y_all_services_map_info: {link}").format(
            link=self._cw.build_url("services")
        )
        return None


class DepartmentMapView(AbstractDptServiceMapView):
    __select__ = one_line_rset() & is_instance("Service")

    @property
    def title(self):
        return self.cw_rset.one().name

    def service_directory_content(self):
        return self._cw.view("service-dpt-content", rset=self.cw_rset)

    def selected_service(self):
        return self.cw_rset.one().dpt_code


class MainInfo(EntityView):
    __regid__ = "service-maininfo"
    __select__ = EntityView.__select__ & is_instance("Service")

    def render_fa_components_link(self, entity):
        anyfa = self._cw.execute(
            """Any 1 WHERE EXISTS(F service X, NOT X code NULL,
               F is FindingAid,
               X eid %(e)s)""",
            {"e": entity.eid},
        )
        if anyfa:
            title = self._cw._("see service related documents")
            self.w(
                T.a(
                    title,
                    klass="blue-button",
                    href=xml_escape(entity.documents_url()),
                )
            )

    def render_nomina_link(self, entity):
        anyfa = self._cw.execute(
            """Any 1 WHERE EXISTS(N service X, NOT X code NULL,
               N is NominaRecord,
               X eid %(e)s)""",
            {"e": entity.eid},
        )
        if anyfa:
            title = self._cw._("see service related nominarecords")
            with T.div(self.w):
                self.w(T.a(title, Class="blue-button", href=xml_escape(entity.nominarecords_url())))

    def render_download_rdf(self, entity):
        download_button = get_template("rdf-download-button.jinja2")
        return download_button.render(
            _=self._cw._,
            rdf_formats=[
                (f"{entity.absolute_url()}/rdf.{extension}", name)
                for extension, name in RDF_FORMAT_EXTENSIONS.items()
            ],
        )

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
            T.span(
                *address_tags,
                itemprop="address",
                itemscope="itemscope",
                itemtype="http://schema.org/PostalAddress",
                klass="col-sm-8"
            )
        )

    def render_parent_service(self, parent):
        return str(
            T.p(
                T.a(
                    parent.dc_title(), href=xml_escape(parent.absolute_url()), itemprop="legalName"
                ),
                itemprop="parentOrganization",
                itemscope="itemscope",
                itemtype="http://schema.org/Organization",
                klass="col-sm-8",
            )
        )

    def render_hidden_microdata(self, entity):
        """those data are hidden from html"""
        for child in entity.reverse_annex_of:
            self.w(
                T.meta(
                    content=child.absolute_url(),
                    itemprop="subOrganization",
                    itemscope="itemscope",
                    itemtype="http://schema.org/Organization",
                )
            )

    def entity_call(self, entity, with_title=True):
        heading_level = 3 if with_title else 2
        with T.section(
            self.w,
            klass="service-info",
            itemscope="itemscope",
            itemtype="http://schema.org/Organization",
        ):
            if with_title:
                self.w(
                    T.h2(
                        entity.dc_title(),
                        itemprop="legalName",
                        klass="mb-4",
                    )
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
            contact_label = _("Director") if entity.level == "level-D" else _("Contact")
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
            gps = None
            if entity.latitude and entity.longitude:
                buff = UStringIO()
                bw = buff.write
                with T.span(bw, itemprop="geo"):
                    bw(f"{entity.latitude}, {entity.longitude}")
                    bw(T.meta(content=entity.latitude, itemprop="latitude"))
                    bw(T.meta(content=entity.longitude, itemprop="longitude"))
                gps = buff.getvalue()
            with T.div(self.w, klass="row "):
                for attr, value in (
                    (_("main_service"), main_service_link),
                    (contact_label, contact_name),
                    (_("Phone number"), phone_number),
                    (_("Email"), email_link),
                    (_("Address"), address),
                    (_("Write to us"), entity.mailing_address),
                    (_("Opening period"), opening_period),
                    (_("Annual closure"), entity.printable_value("annual_closure")),
                    (_("Website"), website_link),
                    (_("Code INSEE commune"), entity.code_insee_commune),
                    (_("GPS coordinates"), gps),
                    (
                        _("SocialNetwork_plural"),
                        ", ".join(
                            e.view("urlattr", rtype="url") for e in entity.service_social_network
                        ),
                    ),
                ):
                    if value:
                        self.w(
                            T.p(
                                display_name(self._cw, attr, context="Service"),
                                klass="service-info__title col-sm-4",
                                role="heading",
                                aria_level=heading_level,
                            )
                        )
                        if value.startswith("<p"):
                            # it's html
                            self.w(value)
                        else:
                            self.w(T.p(value, klass="col-sm-8"))
            other = entity.printable_value("other")
            if other:
                self.w(other)
            with T.div(self.w, klass="service-buttons-wrapper"):
                self.render_fa_components_link(entity)
                self.render_nomina_link(entity)
                self.w(self.render_download_rdf(entity))
            self.render_hidden_microdata(entity)


class DptContextMixIn:
    def display_dpt_context(self, entity):
        rset = self._cw.execute(
            """Any X, N ORDERBY N WHERE X dpt_code C, Y dpt_code C,
               X name N, Y eid %(e)s, NOT X identity Y""",
            {"e": entity.eid},
        )
        if rset:
            with T.section(self.w, id="archives-services"):
                entities = sorted(rset.entities(), key=lambda x: x.name or x.name2)
                for e in entities:
                    self.w(e.view("service-maininfo"))


class ServiceDptContent(DptContextMixIn, EntityView):
    __regid__ = "service-dpt-content"
    __select__ = EntityView.__select__ & is_instance("Service")

    def entity_call(self, entity):
        with T.div(self.w, Class="services-info visually-hidden"):
            entity.view("service-maininfo", w=self.w)
            rset = entity.related("annex_of", "object")
            if rset:
                with T.section(self.w):
                    self.wview("service-maininfo", rset=rset)
            if entity.level == "level-D":
                self.display_dpt_context(entity)


class Service(PrimaryView):
    __select__ = PrimaryView.__select__ & is_instance("Service")

    def add_css(self):
        for css in ("leaflet.css", "LeafletStyleSheet.css"):
            self._cw.add_css(css)

    def add_js(self):
        for js in ("leaflet.js", "PruneCluster.js", "bundle-pniaservice-map.js"):
            self._cw.add_js(js)

    def render_entity(self, entity):
        self.add_css()
        self.add_js()
        with T.div(self.w, Class="service-view document-view"):
            super().render_entity(entity)

    def render_entity_title(self, entity):
        self.w(T.h1(entity.dc_title()))

    def _prepare_side_boxes(self, entity):
        return ()

    def content_navigation_components(self, context):
        pass

    def render_entity_attributes(self, entity):
        with T.div(self.w, klass="row"):
            with T.div(self.w, klass="col-xl-6"):
                entity.view("service-maininfo", w=self.w, with_title=False)
            if entity.latitude and entity.longitude:
                with T.div(self.w, klass="d-none d-md-block col-xl-6 service-geo-map"):
                    with T.div(self.w):
                        self.w(
                            T.p(self._cw._("accessibility_map_info"), Class="sr-only d-print-none")
                        )
                        markerurl = self._cw.build_url("services-map.json", srv=entity.eid)
                        self.w(T.div(id="service-map", data_markerurl=markerurl))

    def render_entity_relations(self, entity):
        # service annexes
        rset = entity.related("annex_of", "object")
        if rset:
            with T.section(self.w):
                with T.div(self.w, klass="col-xl-6"):
                    self.wview("service-maininfo", rset=rset)
