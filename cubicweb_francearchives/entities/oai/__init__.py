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
from lxml import etree
import urllib.parse

from pyramid.response import Response

from logilab.common.decorators import cachedproperty

from cubicweb.predicates import is_instance, one_line_rset
from cubicweb.entities import AnyEntity
from cubicweb.web import httpcache
from cubicweb.web.views import idownloadable

from cubicweb_oaipmh.entities import (
    ETypeOAISetSpec,
    RelatedEntityOAISetSpec,
    NoRecordsMatch,
    OAIPMHRecordAdapter,
)
from cubicweb_oaipmh import MetadataFormat
from cubicweb_oaipmh.views import OAIView, OAIResponse

from logilab.common.decorators import monkeypatch


@monkeypatch(OAIView)
def __call__(self):
    """in order to be parsed by Archives Portal Europe Foundation the <ead> must
    have following attributes :

    <ead xsi:schemaLocation="urn:isbn:1-931666-22-9 http://www.loc.gov/ead/ead.xsd"
    audience="external" xmlns="urn:isbn:1-931666-22-9"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:xlink="http://www.w3.org/1999/xlink">

    as "xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" is already defined on
    the wrapper (OAI-PMH) lxml remove it from <ead>. We try to keep it by injecting
    the xml record string into wrapper.
    """  # noqa
    encoding = self._cw.encoding
    assert encoding == "UTF-8", "unexpected encoding {0}".format(encoding)
    content = b'<?xml version="1.0" encoding="%s"?>\n' % encoding.encode("utf-8")
    oai_response = OAIResponse(self.oai_request)
    # combine errors coming from view selection with those of request
    # processing.
    errors = self.errors() or {}
    verb_content = self.verb_content() if not errors else None
    errors.update(self.oai_request.errors)
    response_elem = oai_response.to_xml(verb_content, errors=errors)
    for ead in response_elem.xpath("..//s:ead", namespaces={"s": "urn:isbn:1-931666-22-9"}):
        ead.attrib["S"] = "#"
    content += etree.tostring(response_elem, encoding="utf-8")
    # realy ugly stuff
    content = content.replace(b'S="#"', b'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"')
    return Response(content, content_type="text/xml")


METADATA_FORMATS = {
    "ape_ead": (
        MetadataFormat("http://www.loc.gov/ead/ead.xsd", "urn:isbn:1-931666-22-9"),
        "oai_ead.export",
    ),
}


class FindingAidStableIdFARecordAdapter(OAIPMHRecordAdapter):
    __select__ = OAIPMHRecordAdapter.__select__ & is_instance("FindingAid")
    metadata_formats = METADATA_FORMATS.copy()
    etype = "FindingAid"

    @classmethod
    def set_definition(cls):
        return FindingAidSetSpec()

    @property
    def identifier(self):
        return self.entity.stable_id


class AbstractOAIDownloadView(idownloadable.DownloadView):
    """oai download view"""

    __select__ = one_line_rset()
    http_cache_manager = httpcache.NoHTTPCacheManager

    def set_request_content_type(self):
        entity = self.cw_rset.get_entity(self.cw_row or 0, self.cw_col or 0)
        adapter = entity.cw_adapt_to(self.adapter_id)
        self._cw.set_content_type(
            adapter.content_type,
            filename=adapter.file_name,
            encoding=adapter.encoding,
            disposition="attachment",
        )

    def call(self):
        entity = self.cw_rset.get_entity(self.cw_row or 0, self.cw_col or 0)
        adapter = entity.cw_adapt_to(self.adapter_id)
        self.w(adapter.dump())


class FindingAidSetSpec(ETypeOAISetSpec):
    """OAI-PMH findinaid set specification

    available sets are:

    - ``findingaid``
    - ``findingaid:service:{service_code}`` (e.g. ``findingaid:service:FRAD005``)
    """

    def __init__(self):
        super(FindingAidSetSpec, self).__init__("FindingAid", "stable_id")

    def setspec_restrictions(self, value=None):
        if value is not None:
            raise NoRecordsMatch("unexpected setspec")
        return "X is FindingAid", {}

    def all_services(self, cnx):
        return list(
            cnx.execute(
                """Any S,SC,SN,SSN,SN2 WHERE S is Service, S code SC,
                S name SN, S short_name SSN, S name2 SN2,
                NOT S code NULL,
                EXISTS(X is FindingAid, X service S,
                X in_state ST, ST name %(st)s)""",
                {"st": "wfs_cmsobject_published"},
            ).entities()
        )

    def setspecs(self, cnx):
        yield "findingaid", cnx._("FindingAid")  # main set
        # + list of all services that have provided some findingaids
        for service in self.all_services(cnx):
            yield ("findingaid:service:{}".format(service.code), service.publisher())

    def __getitem__(self, key):
        assert key == "service", "other relations than 'service' are not tested yet"
        specifier = RelatedEntityOAISetSpec("service", "Service", "code")
        specifier.__parent__ = self
        return specifier


class OAIRepository(AnyEntity):
    __regid__ = "OAIRepository"

    @property
    def tasks(self):
        """return the list of task entities associated to the repository

        The returned tasks are sorted by their creation date.
        """
        return sorted(self.reverse_oai_repository, key=lambda t: t.creation_date)

    @cachedproperty
    def oai_params(self):
        url = urllib.parse.urlparse(self.url)
        return urllib.parse.parse_qs(url.query)

    @property
    def last_successful_import(self):
        rset = self._cw.execute(
            "Any OIT ORDERBY OIT DESC LIMIT 1 "
            "WHERE OIT oai_repository X, X eid %(x)s, "
            'OIT in_state S, S name "wfs_oaiimport_completed"',
            {"x": self.eid},
        )
        if rset:
            oai_import = rset.one()
            wf = oai_import.cw_adapt_to("IWorkflowable")
            return wf.latest_trinfo().creation_date
        return None
