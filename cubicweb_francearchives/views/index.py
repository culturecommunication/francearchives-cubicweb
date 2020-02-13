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
from urllib.parse import urlparse

from cwtags import tag as T

from logilab.mtconverter import xml_escape

from cubicweb.predicates import is_instance
from cubicweb.view import EntityView
from cubicweb.web.views.baseviews import InContextView
from cubicweb.web.views.primary import PrimaryView
from cubicweb_francearchives.views.search import PniaElasticSearchView
from cubicweb_francearchives.views import JinjaViewMixin, get_template


class IndexElasticSearchView(PniaElasticSearchView):
    __regid__ = "indexes-esearch"

    def format_results_title(self, response):
        if response is None or response.hits.total.value == 0:
            return None
        return super(IndexElasticSearchView, self).format_results_title(response)


class AuthorityPrimaryView(PrimaryView):
    __select__ = PrimaryView.__select__ & is_instance(
        "SubjectAuthority", "AgentAuthority", "LocationAuthority"
    )

    def entity_call(self, entity, **kw):
        self._cw.form.pop("rql", None)  # remove rql form param which comes from url_rewriter
        self._cw.form["indexentry"] = entity.eid
        self._cw.form["restrict_to_single_etype"] = True
        self.w(entity.view("index-abstract"))
        self.wview("indexes-esearch")


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
        if entity.source:
            label = "{} : {}".format(_(entity.source), label)
        else:
            label = "{} : {}".format(_(netloc), label)
        title = "{} {} {}".format(_("Go to the site:"), netloc, _("- New window"))
        self.w(
            T.a(
                xml_escape(label),
                href=xml_escape(url),
                target="_blank",
                rel="nofollow noopener noreferrer",
                title=title,
            )
        )


class ConceptInContextView(AbstractExternalInContextView):
    __select__ = AbstractExternalInContextView.__select__ & is_instance("Concept")
    uri_attr = "cwuri"


class PersonInContextView(AbstractExternalInContextView):
    __select__ = AbstractExternalInContextView.__select__ & is_instance("Person")
    uri_attr = "document_uri"


class AbstractAuthorityAbstractView(EntityView, JinjaViewMixin):
    __abstract__ = True
    __regid__ = "index-abstract"
    template = get_template("index-abstract.jinja2")

    def entity_call(self, entity):
        properties = self.properties(entity)
        properties = [entry for entry in properties if entry[-1]]
        self.call_template(title=entity.dc_title(), properties=properties)

    def same_as_property(self, entity):
        _ = self._cw._
        return [
            (
                _("same_as_label"),
                ", ".join(
                    e.view("incontext") for e in entity.same_as if e.cw_etype != "ExternalId"
                ),
            ),
        ]

    def properties(self, entity):
        return self.same_as_property(entity)


class AgentAuthorityAbstractView(AbstractAuthorityAbstractView):
    __select__ = EntityView.__select__ & is_instance("AgentAuthority")

    def properties(self, entity):
        adapter = entity.cw_adapt_to("entity.main_props")
        return adapter.properties()


class SubjectAuthorityAbstractView(AbstractAuthorityAbstractView):
    __select__ = EntityView.__select__ & is_instance("SubjectAuthority")


class LocationAuthorityAbstractView(AbstractAuthorityAbstractView):
    __select__ = EntityView.__select__ & is_instance("LocationAuthority")


class AuthorityRecordView(EntityView):
    __regid__ = "maintainer.outofcontext"
    __select__ = EntityView.__select__ & is_instance("AuthorityRecord")

    def entity_call(self, entity, **kwargs):
        title = entity.dc_title()
        if entity.maintainer:
            title = "{} : {}".format(entity.maintainer[0].dc_title(), title)
        self.w(T.a(xml_escape(title), href=xml_escape(entity.absolute_url())))
