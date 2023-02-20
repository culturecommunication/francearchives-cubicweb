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

from collections import defaultdict

from urllib.parse import urlparse

from cwtags import tag as T

from logilab.mtconverter import xml_escape

from cubicweb import _
from cubicweb.predicates import is_instance
from cubicweb.view import EntityView
from cubicweb.entity import EntityAdapter
from cubicweb.uilib import cut

from cubicweb.web.views.baseviews import InContextView
from cubicweb.web.views.primary import PrimaryView
from cubicweb_francearchives.entities.rdf import RDF_FORMAT_EXTENSIONS
from cubicweb_francearchives.views.search.nomina import PniaNominaElasticSearchView
from cubicweb_francearchives.views.search import PniaElasticSearchView
from cubicweb_francearchives.views import blank_link_title


class IndexElasticSearchView(PniaElasticSearchView):
    __regid__ = "indexes-esearch"
    title_count_templates = (_("No result"), _("1 linked content"), _("{count} linked content"))

    def call(self, entity, **kwargs):
        self.entity = entity
        super().call(**kwargs)

    def get_header_attrs(self):
        adapter = self.entity.cw_adapt_to("ISearchContextAbstract")
        if adapter:
            return adapter.get_properties()

    def get_rdf_formats(self):
        if self.entity.quality:
            return [
                (f"{self.entity.absolute_url()}/rdf.{extension}", name)
                for extension, name in RDF_FORMAT_EXTENSIONS.items()
            ]
        return None


class SubjectAuthorityElasticSearchView(IndexElasticSearchView):
    __select__ = IndexElasticSearchView.__select__ & is_instance("SubjectAuthority")

    def compute_augmented_search_options(self, response, query_string):
        """augmented_search is active only in SubjectAuhtorities"""
        is_augmented = "aug" in self._cw.form
        url_params = self._cw.form.copy()
        _ = self._cw._
        if is_augmented:
            del url_params["aug"]
            search_text = _("augmented_search_link_text_true")
            href = self._cw.build_url(**url_params)
            link = f'<a href="{href}"">{search_text}</a>'
            text = _("augmented_search_text_true {}").format(link)
        else:
            url_params["aug"] = True
            href = self._cw.build_url(**url_params)
            search_text = _("augmented_search_link_text_false")
            link = f'<a href="{href}">{search_text}</a>'
            text = _("augmented_search_text_false {}").format(link)
        return {"extra_link": text, "search_is_augmented": is_augmented}


class AgentAuthorityNominaView(PniaNominaElasticSearchView):
    __select__ = is_instance("AgentAuthority")
    __regid__ = "agents-nomina"

    def search_title(self):
        title = [self.cw_rset.get_entity(0, 0).dc_title()]
        title.append(self._cw._("All nomina records"))
        title.append("({})".format(self._cw.property_value("ui.site-title")))
        return xml_escape(" ".join(title))

    def get_header_attrs(self):
        return {
            "title": self.entity.view("outofcontext"),
            "subtitle": self._cw._("All nomina records"),
        }

    def call(self, context=None, **kwargs):
        self.entity = self.cw_rset.get_entity(0, 0)
        self._cw.form["authority"] = self.entity.eid
        super().call(context=context, **kwargs)


class AuthorityPrimaryView(PrimaryView):
    __select__ = PrimaryView.__select__ & is_instance(
        "SubjectAuthority", "AgentAuthority", "LocationAuthority"
    )

    def entity_call(self, entity, **kw):
        self._cw.form.pop("rql", None)  # remove rql form param which comes from url_rewriter
        self._cw.form["indexentry"] = entity.eid
        self._cw.form["restrict_to_single_etype"] = False
        self.wview("indexes-esearch", entity=entity)


class IndexInContextView(InContextView):
    __select__ = InContextView.__select__ & is_instance("AgentName", "Subject", "Geogname")

    def cell_call(self, row, col):
        entity = self.cw_rset.get_entity(row, col)
        self.w(
            '<a href="{0}">{1}</a>'.format(
                xml_escape(entity.authority_url), xml_escape(entity.dc_title())
            )
        )


class AbstractExternalInContextView(InContextView):
    __abstract__ = True
    uri_attr = None

    def cell_call(self, row, col):
        entity = self.cw_rset.get_entity(row, col)
        self.w(entity.view("urlattr", rtype=self.uri_attr))


class ExternalUriInContextView(InContextView):
    __select__ = InContextView.__select__ & is_instance("ExternalUri")

    def cell_call(self, row, col):
        entity = self.cw_rset.get_entity(row, col)
        label = entity.label or entity.uri
        url = entity.uri
        netloc = urlparse(url).netloc
        _ = self._cw._
        self.w("{} : ".format(_(entity.source) or _(netloc)))
        title = "{} {}".format(netloc, _("- New window"))
        with T.a(
            self.w,
            href=xml_escape(url),
            target="_blank",
            rel="nofollow noopener noreferrer",
            title=xml_escape(title),
        ):
            self.w(xml_escape(label))
            self.w(T.i(Class="fa fa-external-link", aria_hidden="true"))


class ConceptInContextView(AbstractExternalInContextView):
    __select__ = AbstractExternalInContextView.__select__ & is_instance("Concept")
    uri_attr = "cwuri"

    def cell_call(self, row, col):
        entity = self.cw_rset.get_entity(row, col)
        url = entity.printable_value("cwuri")
        if url:
            title = blank_link_title(self._cw, url)
            # for now we only have data.culture.fr thesaurus
            self.w(
                T.a(
                    entity.dc_title(),
                    href=xml_escape(url),
                    title=title,
                    target="_blank",
                    rel="nofollow noopener noreferrer",
                )
            )


class ConceptIndexView(InContextView):
    __select__ = InContextView.__select__ & is_instance("Concept")
    __regid__ = "index"

    def cell_call(self, row, col, subject):
        entity = self.cw_rset.get_entity(row, col)
        subjects = defaultdict(list, {})
        for eid, label in self._cw.execute(
            """Any S, NORMALIZE_ENTRY(L) WHERE X eid %(e)s,
                   S same_as X, S label L,
                   NOT S grouped_with S1,
                   NOT S eid %(s)s
                   """,
            {"e": entity.eid, "s": subject.eid},
        ):
            subjects[label].append(self._cw.entity_from_eid(eid))
        labels = [
            r[0]
            for r in self._cw.execute(
                """Any NORMALIZE_ENTRY(L) ORDERBY L WHERE O label_of X,
               O label L, X eid %(e)s""",
                {"e": entity.eid},
            )
        ]
        html = []
        for label in labels:
            entities = subjects.get(label, [])
            for entity in entities:
                serializable = entity.cw_adapt_to("ISuggestIndexSerializable")
                doc_count = serializable.related_docs()
                if doc_count:
                    desc = cut(entity.dc_description(), 50)
                    label = "{title}{count}".format(
                        title=xml_escape(entity.dc_title()), count=" [{}]".format(doc_count)
                    )
                    html.append(
                        str(
                            T.a(
                                label,
                                href=xml_escape(entity.absolute_url()),
                                title=xml_escape(desc),
                            )
                        )
                    )
        self.w(" ; ".join(html))


class NominaAgentInContextView(InContextView):
    __regid__ = "nomina_agent"
    __select__ = InContextView.__select__ & is_instance("AgentAuthority")

    max_title_size = 140

    def cell_call(self, row, col, es_response=None, **kwargs):
        entity = self.cw_rset.get_entity(row, col)
        full_title = entity.dc_title()
        title = self._cw._("Link to FranceArchives")
        self.w(
            '<a href="%s" title="%s">%s</a>'
            % (xml_escape(entity.absolute_url()), xml_escape(title), xml_escape(full_title))
        )


class AbstractAuthorityAdapter(EntityAdapter):
    __select__ = is_instance("Any")
    __regid__ = "ISearchContextAbstract"
    editable = False

    def get_properties(self):
        properties = [entry for entry in self.properties() if entry[-1]]
        return {"title": self.entity.dc_title(), "properties": properties}

    def same_as_property(self):
        _ = self._cw._
        data = []
        same_as = self.entity.same_as_links
        concepts = same_as.get("Concept")
        if concepts:
            data.append(
                (
                    _("same_as_label"),
                    "data.culture.fr : {}".format(", ".join(e.view("incontext") for e in concepts)),
                ),
            )
        links = same_as.get("ExternalUri", []) + same_as.get("AuthorityRecord", [])
        if links:
            data.append(
                (
                    _("same_as_label"),
                    ", ".join(e.view("incontext") for e in links),
                ),
            )
        if concepts:
            data.append(
                (
                    _("See also:"),
                    ", ".join(
                        (v for v in (e.view("index", subject=self.entity) for e in concepts) if v)
                    ),
                ),
            )
        return data

    def metadata_properties(self):
        if self.editable:
            return [
                (self._cw._("Creation date"), self.entity.fmt_creation_date),
                (self._cw._("Modification date"), self.entity.fmt_modification_date),
            ]
        return []

    def properties(self):
        data = self.same_as_property()
        data.extend(self.metadata_properties())
        return data


class AgentAuthorityAbstractAdapter(AbstractAuthorityAdapter):
    __select__ = AbstractAuthorityAdapter.__select__ & is_instance("AgentAuthority")

    def properties(self):
        adapter = self.entity.cw_adapt_to("entity.main_props")
        data = adapter.properties()
        data.extend(self.metadata_properties())
        return data


class SubjectAuthorityAbstractAdapter(AbstractAuthorityAdapter):
    __select__ = AbstractAuthorityAdapter.__select__ & is_instance("SubjectAuthority")


class LocationAuthorityAbstractAdapter(AbstractAuthorityAdapter):
    __select__ = AbstractAuthorityAdapter.__select__ & is_instance("LocationAuthority")


class AuthorityRecordView(EntityView):
    __regid__ = "maintainer.outofcontext"
    __select__ = EntityView.__select__ & is_instance("AuthorityRecord")

    def entity_call(self, entity, **kwargs):
        title = entity.dc_title()
        if entity.maintainer:
            title = "{} : {}".format(entity.maintainer[0].dc_title(), title)
        self.w(T.a(xml_escape(title), href=xml_escape(entity.absolute_url())))
