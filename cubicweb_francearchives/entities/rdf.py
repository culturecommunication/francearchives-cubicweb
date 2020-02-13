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
"""francearchives rdf adpaters"""
import logging
from itertools import chain
import urllib.request
import urllib.parse
import urllib.error
from collections import defaultdict

from lxml import etree

from rdflib.term import BNode

from logilab.common.decorators import cachedproperty

from cubicweb.predicates import is_instance
from cubicweb.view import EntityAdapter

from cubicweb_francearchives.xy import NS_VARS


class EntityRDFAdapter(EntityAdapter):
    __abstract__ = True
    rdf_type = None

    @cachedproperty
    def uri(self):
        req = self._cw
        # NOTE: do not call absolute_url() to avoid including lang prefix
        return "{}{}".format(req.base_url(), self.entity.rest_path())

    def statements(self):
        if self.rdf_type is not None:
            yield (self.uri, "rdf", "type", self.rdf_type, None)
        for prop in self.properties():
            yield (self.uri,) + prop
        for relinfo in self.relations():
            yield (self.uri,) + relinfo + (None,)
        for relinfo in self.object_relations():
            yield relinfo + (self.uri, None)
        for statement in self.extra_statements():
            yield statement

    def properties(self):
        return ()

    def relations(self):
        return ()

    def object_relations(self):
        return ()

    def extra_statements(self):
        return ()

    @classmethod
    def _date_iso8601(cls, date):
        if date:
            return date.strftime("%Y-%m-%d")


def plaintext(html):
    if html:
        try:
            html = etree.HTML(html)
            return " ".join(html.xpath("//text()"))
        except Exception:
            logging.warning("failed to extract text from %r", html)
            return html
    return ""


class ComponentMixin(object):
    rdf_type = NS_VARS["schema"] + "CreativeWork"

    @cachedproperty
    def subject_indexes(self):
        return self.entity.subject_indexes()

    def properties(self):
        entity = self.entity
        did = entity.did[0]
        yield ("schema", "name", entity.dc_title(), {})
        yield ("schema", "contentLocation", did.origination, {})
        yield ("schema", "mentions", plaintext(entity.scopecontent), {})
        for subject in self.subject_indexes.entities():
            authority_url = subject.authority[0].absolute_url()
            yield ("schema", "about", authority_url, {})

    def extra_statements(self):
        # XXX not sure if these same_as statement should be on facomponent
        for subject in self.subject_indexes.entities():
            authority = subject.authority[0]
            authority_url = authority.absolute_url()
            for url in authority.same_as_refs:
                yield (authority_url, "schema", "sameAs", url, {})


class FindingAid2SchemaOrg(ComponentMixin, EntityRDFAdapter):
    __regid__ = "rdf.schemaorg"
    __select__ = is_instance("FindingAid")
    rdf_type = NS_VARS["schema"] + "CreativeWork"

    def relations(self):
        for comp in self.entity.top_components:
            yield ("schema", "hasPart", comp.cw_adapt_to("rdf.schemaorg").uri)


class FAComponent2SchemaOrg(ComponentMixin, EntityRDFAdapter):
    __regid__ = "rdf.schemaorg"
    __select__ = is_instance("FAComponent")

    def relations(self):
        if self.entity.parent_component:
            yield (
                "schema",
                "isPartof",
                self.entity.parent_component[0].cw_adapt_to("rdf.schemaorg").uri,
            )
        else:
            yield (
                "schema",
                "isPartof",
                self.entity.finding_aid[0].cw_adapt_to("rdf.schemaorg").uri,
            )
        for comp in self.entity.reverse_parent_component:
            yield ("schema", "hasPart", comp.cw_adapt_to("rdf.schemaorg").uri)

    def extra_statements(self):
        for dv in self.entity.digitized_versions:
            encoding = BNode()
            url = None
            if dv.illustration_url:
                url = dv.illustration_url
                yield (encoding, "schema", "type", NS_VARS["schema"] + "ImageObject", None)
            elif dv.url:
                url = dv.url
                yield (encoding, "schema", "type", NS_VARS["schema"] + "DataDownload", None)
            if url:
                yield (encoding, "schema", "contentUrl", url, None)
                yield (self.uri, "schema", "encoding", encoding, None)
        for statement in super(FAComponent2SchemaOrg, self).extra_statements():
            yield (statement)


class Service2SchemaOrg(EntityRDFAdapter):
    __regid__ = "rdf.schemaorg"
    __select__ = is_instance("Service")
    rdf_type = NS_VARS["schema"] + "Organization"

    def properties(self):
        entity = self.entity
        yield ("schema", "legalName", entity.dc_title(), {})
        yield ("schema", "employee", entity.contact_name, {})
        yield ("schema", "telephone", entity.phone_number, {})
        yield ("schema", "openinghours", entity.opening_period, {})
        yield ("schema", "faxNumber", entity.fax, {})
        yield ("schema", "email", entity.email, {})

    def relations(self):
        entity = self.entity
        if entity.annex_of:
            parent = entity.annex_of[0].cw_adapt_to("rdf.schemaorg")
            if parent:
                yield ("schema", "parentOrganization", parent.uri)
        for child in entity.reverse_annex_of:
            child = child.cw_adapt_to("rdf.schemaorg")
            if child:
                yield ("schema", "subOrganization", child.uri)
        if entity.illustration_url:
            yield ("schema", "logo", entity.illustration_url)

    def extra_statements(self):
        entity = self.entity
        address = BNode()
        yield (self.uri, "schema", "address", address, None)
        yield (address, "schema", "type", NS_VARS["schema"] + "PostalAddress", None)
        yield (address, "schema", "postalCode", entity.zip_code, {})
        yield (address, "schema", "streetAddress", entity.address, {})
        yield (address, "schema", "addressLocality", entity.city, {})
        yield (address, "schema", "addressCountry", "fr", {})


class AgentAuthority(EntityRDFAdapter):
    __regid__ = "rdf.schemaorg"
    __select__ = is_instance("AgentAuthority")
    rdf_type = NS_VARS["schema"] + "Person"

    def properties(self):
        entity = self.entity
        adapter = entity.cw_adapt_to("entity.main_props")
        info = adapter.eac_info() or adapter.agent_info()
        if info:
            birthdate = info["dates"].get("birthdate")
            deathdate = info["dates"].get("deathdate")
            for (dtype, dateinfo) in (("birthDate", birthdate), ("deathDate", deathdate)):
                if dateinfo and dateinfo["isdate"] and not dateinfo["isbc"]:
                    yield ("schema", dtype, dateinfo["timestamp"], {})
            yield ("schema", "description", info["description"], {})
        yield ("schema", "givenName", entity.label, {})

    def extra_statements(self):
        for url in self.entity.same_as_refs:
            yield (self.uri, "schema", "sameAs", url, {})


class LocationAuthority(EntityRDFAdapter):
    __regid__ = "rdf.schemaorg"
    __select__ = is_instance("LocationAuthority")
    rdf_type = NS_VARS["schema"] + "Place"

    def properties(self):
        entity = self.entity
        yield ("schema", "name", entity.label, {})

    def extra_statements(self):
        entity = self.entity
        geo = BNode()
        yield (self.uri, "schema", "geo", geo, None)
        yield (geo, "schema", "type", NS_VARS["schema"] + "GeoCoordinates", None)
        yield (geo, "schema", "latitude", entity.latitude, {})
        yield (geo, "schema", "longitude", entity.longitude, {})
        for url in self.entity.same_as_refs:
            yield (self.uri, "schema", "sameAs", url, {})


class BaseContent2SchemaOrg(EntityRDFAdapter):
    __regid__ = "rdf.schemaorg"
    __select__ = is_instance("BaseContent")
    rdf_type = NS_VARS["schema"] + "Article"

    def properties(self):
        entity = self.entity
        yield ("schema", "name", entity.dc_title(), {})
        yield ("schema", "datePublished", entity.creation_date.strftime("%Y-%m-%d"), {})
        yield ("schema", "dateCreated", entity.creation_date.strftime("%Y-%m-%d"), {})
        yield ("schema", "dateModified", entity.modification_date.strftime("%Y-%m-%d"), {})
        yield ("schema", "author", entity.dc_authors(), {})
        yield ("schema", "inLanguage", entity.dc_language().upper(), {})
        yield ("schema", "keywords", entity.keywords, {})
        yield ("schema", "url", self.uri, {})


class NewsContent2SchemaOrg(EntityRDFAdapter):
    __regid__ = "rdf.schemaorg"
    __select__ = is_instance("NewsContent")
    rdf_type = NS_VARS["schema"] + "Article"

    def properties(self):
        entity = self.entity
        yield ("schema", "name", entity.dc_title(), {})
        yield ("schema", "dateCreated", entity.creation_date.strftime("%Y-%m-%d"), {})
        yield ("schema", "dateModified", entity.modification_date.strftime("%Y-%m-%d"), {})
        yield ("schema", "datePublished", entity.start_date.strftime("%Y-%m-%d"), {})
        yield ("schema", "author", entity.dc_authors(), {})
        yield ("schema", "inLanguage", entity.dc_language().upper(), {})
        yield ("schema", "keywords", entity.keywords, {})
        yield ("schema", "url", self.uri, {})


class CommemorationItem2SchemaOrg(EntityRDFAdapter):
    __regid__ = "rdf.schemaorg"
    __select__ = is_instance("CommemorationItem")
    rdf_type = NS_VARS["schema"] + "Event"

    def properties(self):
        entity = self.entity
        yield ("schema", "name", entity.dc_title(), {})
        yield ("schema", "datePublished", entity.creation_date.strftime("%Y-%m-%d"), {})
        yield ("schema", "author", entity.dc_authors(), {})
        yield ("schema", "inLanguage", entity.dc_language().upper(), {})
        yield ("schema", "url", self.uri, {})

    def extra_statements(self):
        super_event = BNode()
        yield (self.uri, "schema", "superEvent", super_event, None)
        yield (super_event, "schema", "type", NS_VARS["schema"] + "Event", None)
        yield (super_event, "schema", "url", self.entity.collection.absolute_url(), {})


class CommemoCollection2SchemaOrg(EntityRDFAdapter):
    __regid__ = "rdf.schemaorg"
    __select__ = is_instance("CommemoCollection")
    rdf_type = NS_VARS["schema"] + "Event"

    def properties(self):
        entity = self.entity
        yield ("schema", "name", entity.dc_title(), {})
        yield ("schema", "datePublished", entity.creation_date.strftime("%Y-%m-%d"), {})
        yield ("schema", "author", entity.dc_authors(), {})
        yield ("schema", "inLanguage", entity.dc_language().upper(), {})
        yield ("schema", "url", self.uri, {})

    def extra_statements(self):
        for commemoration_item in self.entity.reverse_collection_top:
            sub_event = BNode()
            yield (self.uri, "schema", "subEvent", sub_event, None)
            yield (sub_event, "schema", "type", NS_VARS["schema"] + "Event", None)
            yield (sub_event, "schema", "url", commemoration_item.absolute_url(), {})


def set_related_cache(entity, rtype, related, role="subject"):
    cache_key = "{}_{}".format(rtype, role)
    # XXX None means we can't use resultset, only entities
    entity._cw_related_cache[cache_key] = (None, related)


class EDMComponentMixin(object):
    @cachedproperty
    def uri(self):
        req = self._cw
        # NOTE: do not call absolute_url() to avoid including lang prefix
        return "{}{}".format(req.base_url(), self.entity.rest_path())

    @cachedproperty
    def agg_uri(self):
        return self.uri + "#Aggregation"

    def properties(self):
        entity = self.entity
        did = entity.did[0]
        yield ("dcterms", "identifier", did.unitid, {})
        yield ("dcterms", "title", entity.dc_title(), {})
        yield ("dcterms", "date", did.unitdate, {})
        yield ("dcterms", "description", entity.description, {})

    def extra_statements(self):
        # XXX check ore vs. edm
        # (cf. http://www-e.uni-magdeburg.de/predoiu/sda2011/sda2011_06.pdf)
        if self.entity.cw_etype == "FindingAid":
            agg_type = NS_VARS["ore"] + "Aggregation"
        else:
            agg_type = NS_VARS["edm"] + "Aggregation"
        yield (self.agg_uri, "rdf", "type", agg_type, None)
        yield (self.agg_uri, "ore", "aggregates", self.uri, None)
        indices = self.entity.indices
        for index in chain(indices["agents"], indices["subjects"], indices["locations"]):
            index_uri = index.absolute_url()  # XXX
            yield (self.uri, "dcterms", "subject", index_uri, None)
            yield (index_uri, "rdf", "type", NS_VARS["skos"] + "Concept", None)
            yield (index_uri, "skos", "prefLabel", index.label, {})
            for url in index.authority[0].same_as_refs:
                yield (index_uri, "skos", "exactMatch", url, {})
        for agent in indices["agents"]:
            index_uri = agent.absolute_url()  # XXX
            agent_uri = index_uri + "#Agent"
            # XXX skos:Concept foaf:focus foaf:Agent
            if agent.type == "persname":
                foaf_type = "Person"
            elif agent.type == "corpname":
                foaf_type = "Organization"
            else:
                foaf_type = "Agent"
            yield (agent_uri, "rdf", "type", NS_VARS["foaf"] + foaf_type, None)
            yield (self.uri, "dcterms", "subject", agent_uri, None)
            yield (agent_uri, "foaf", "name", agent.label, {})
            yield (index_uri, "foaf", "focus", agent_uri, None)


class FindingAid2EDM(EDMComponentMixin, EntityRDFAdapter):
    __regid__ = "rdf.edm"
    __select__ = is_instance("FindingAid")
    rdf_type = NS_VARS["ore"] + "Proxy"

    def properties(self):
        for stmt in super(FindingAid2EDM, self).properties():
            yield stmt
        entity = self.entity
        yield ("dcterms", "publisher", entity.publisher, {})
        if entity.service:
            yield ("dcterms", "publisher", entity.service[0].absolute_url(), {})
        if entity.fa_header[0].lang_code:
            yield ("dcterms", "language", entity.fa_header[0].lang_code, {})

    def all_components(self):
        entity = self.entity
        rset = self._cw.execute(
            "Any C,F,D,DID,DD,DT,DL,CA,CU,CD,CS,P "
            "WHERE F eid %(f)s, C finding_aid F, C did D, "
            "D unitid DID, D unitdate DD, D unittitle DT, "
            "D lang_code DL, C accessrestrict CA, "
            "C userestrict CU, C description CD, "
            "C stable_id CS, C parent_component P?",
            {"f": entity.eid},
        )
        components = {comp.eid: comp for comp in rset.entities()}
        indices = defaultdict(lambda: defaultdict(list))
        agents_rset = self._cw.execute(
            "DISTINCT Any I, L, T, C "
            "WHERE X is AgentAuthority, "
            "X label L, I type T, "
            "I authority X, I index C, "
            "C finding_aid F, F eid %(f)s",
            {"f": entity.eid},
        )
        for row, agent in zip(agents_rset, agents_rset.entities()):
            comp_eid = row[-1]
            indices[comp_eid]["agents"].append(agent)
        subjects_rset = self._cw.execute(
            "DISTINCT Any I, L, C "
            "WHERE X is SubjectAuthority, "
            "X label L, "
            "I authority X, I index C, "
            "C finding_aid F, F eid %(f)s",
            {"f": entity.eid},
        )
        for row, subject in zip(subjects_rset, subjects_rset.entities()):
            comp_eid = row[-1]
            indices[comp_eid]["subjects"].append(subject)
        locations_rset = self._cw.execute(
            "DISTINCT Any I, L, C "
            "WHERE X is LocationAuthority, "
            "X label L, "
            "I authority X, I index C, "
            "C finding_aid F, F eid %(f)s",
            {"f": entity.eid},
        )
        for row, location in zip(locations_rset, locations_rset.entities()):
            comp_eid = row[-1]
            indices[comp_eid]["locations"].append(location)
        for comp in list(components.values()):
            if comp.eid in indices:
                comp.__dict__["indices"] = indices[comp.eid]
            else:
                comp.__dict__["indices"] = {"agents": [], "subjects": [], "locations": []}
        digitized_rset = self._cw.execute(
            "Any D, DR, DU, DI, C WHERE "
            "D role DR, D url DU, D illustration_url DI, "
            "C digitized_versions D, "
            "C finding_aid F, F eid %(f)s",
            {"f": entity.eid},
        )
        dvs = defaultdict(list)
        for row, dv in zip(digitized_rset, digitized_rset.entities()):
            comp_eid = row[-1]
            dvs[comp_eid].append(dv)
        for comp in list(components.values()):
            set_related_cache(comp, "digitized_versions", dvs.get(comp.eid, ()))
        return list(components.values())

    def extra_statements(self):
        for stmt in super(FindingAid2EDM, self).extra_statements():
            yield stmt
        for facomponent in self.all_components():
            adapter = facomponent.cw_adapt_to("rdf.edm")
            for stmt in adapter.statements():
                yield stmt


class FAComponent2EDM(EDMComponentMixin, EntityRDFAdapter):
    __regid__ = "rdf.edm"
    __select__ = is_instance("FAComponent")
    rdf_type = NS_VARS["edm"] + "ProvidedCHO"

    def properties(self):
        for stmt in super(FAComponent2EDM, self).properties():
            yield stmt
        entity = self.entity
        yield ("dcterms", "accessRights", entity.accessrestrict, {})
        yield ("dcterms", "rights", entity.userestrict, {})

    def relations(self):
        entity = self.entity
        if entity.parent_component:
            parent_uri = entity.parent_component[0].cw_adapt_to("rdf.edm").uri
            yield ("dcterms", "isPartOf", parent_uri)
        else:
            findingaid = entity.finding_aid[0]
            yield ("dcterms", "isPartOf", findingaid.cw_adapt_to("rdf.edm").uri)

    def extra_statements(self):
        for stmt in super(FAComponent2EDM, self).extra_statements():
            yield stmt
        for dv in self.entity.digitized_versions:
            url = None
            if dv.illustration_url:
                url = dv.illustration_url
                description = dv.role or "thumbnail"  # default to thumbnail
            elif dv.url:
                url = dv.url
                description = dv.role
            if not url:
                continue
            url = urllib.parse.quote(url.encode("utf-8"))
            yield (url, "rdf", "type", NS_VARS["edm"] + "WebResource", None)
            yield (url, "dcterms", "description", description, {})
            yield (self.agg_uri, "edm", "hasView", url, None)
