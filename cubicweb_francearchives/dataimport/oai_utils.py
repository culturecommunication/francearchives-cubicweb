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

""":synopsis: OAI-PMH utils."""


# standard library imports

import hashlib

from lxml import etree

import os
import os.path

from sickle import Sickle
from sickle.iterator import OAIItemIterator
from sickle.response import OAIResponse, XMLParser

import urllib.parse

from logilab.common.decorators import cachedproperty


from cubicweb_francearchives.dataimport import normalize_for_filepath
from cubicweb_francearchives.storage import S3BfssStorageMixIn


class PniaOAIResponse(OAIResponse):
    @cachedproperty
    def http_fixed_content(self):
        return self.http_response.content.replace(
            b"https://www.openarchives.org/OAI", b"http://www.openarchives.org/OAI"
        )

    @property
    def xml(self):
        """The server's response as parsed XML, after the HTTPS replacement."""
        return etree.XML(self.http_fixed_content, parser=XMLParser)


class PniaSickle(Sickle):
    def harvest(self, **kwargs):
        """Make HTTP requests to the OAI server.

        :param kwargs: OAI HTTP parameters.
        :rtype: :class:`PniaOAIResponse`
        """
        oai_response = super(PniaSickle, self).harvest(**kwargs)
        return PniaOAIResponse(oai_response.http_response, oai_response.params)


class OAIXMLError(Exception):
    """XML errors from OAI response"""

    pass


class OAIPMHWriter:
    """OAI-PMH writer."""

    def __init__(self, ead_services_dir, service_infos, subdirectories=[]):
        """Initialize OAI-PMH writer.

        :param str ead_services_dir: location of backup files
        :param dict service_infos: service information
        :param list subdirectories: list of subdirectories
        """
        self.storage = S3BfssStorageMixIn()
        self.ead_services_dir = ead_services_dir
        self.service_infos = service_infos
        self.directory = self.makedir(subdirectories)

    def makedir(self, subdirectories=[]):
        """Create directory(ies).

        :param list subdirectories: list of subdirectories

        :returns: directory
        :rtype: str
        """
        dirs = [self.ead_services_dir, self.service_infos["code"]]
        if subdirectories:
            dirs.extend(subdirectories)
        return self.storage.storage_makedir(dirs)

    def get_file_path(self, eadid):
        """Get file path.

        :param str eadid: EADID

        :returns: file path
        :rtype: str
        """
        eadid = normalize_for_filepath(eadid)
        filename = eadid + ".xml"
        # add lower test
        postfix = "{}_".format(self.service_infos["code"])
        if not filename.startswith(postfix):
            if filename.startswith(postfix.lower()):
                filename = "{}{}".format(postfix, filename.split(postfix.lower())[1])
            else:
                filename = "{}{}".format(postfix, filename)
        file_path = os.path.join(self.directory, filename)
        if self.storage.s3_bucket:
            return self.storage.s3.ensure_key(file_path)
        return file_path

    def get_file_contents(self, *args):
        """Get file contents."""
        raise NotImplementedError

    def dump(self, eadid, file_contents):
        """Dump file contents.
        :param str eadid: EADID
        :param str file_contents: file contents

        :returns: str file_path: filepath
        """
        filepath = self.get_file_path(eadid)
        return self.storage.storage_write_file(filepath, file_contents)

    def add_record(self, header, metadata):
        """Add record to list of records.

        :param _Element header: header
        :param _Element metadata: metadata
        """
        raise NotImplementedError


class PniaOAIItemIterator(OAIItemIterator):
    def __init__(self, sickle, params, ignore_deleted=False):
        super(PniaOAIItemIterator, self).__init__(sickle, params, ignore_deleted=ignore_deleted)
        self._next_harvested_url(init=True)

    def _next_harvested_url(self, init=False):
        params = self.params
        if not init and self.resumption_token and self.resumption_token.token:
            params = {"resumptionToken": self.resumption_token.token, "verb": self.verb}
        args = urllib.parse.urlencode(params)
        self._harvested_url = "{}?{}".format(self.sickle.endpoint, args)

    def _next_response(self):
        self._next_harvested_url()
        try:
            super(PniaOAIItemIterator, self)._next_response()
        except Exception as exception:
            if (
                hasattr(self, "oai_response")
                and self.oai_response
                and hasattr(self.oai_response, "xml")
            ):
                if self.oai_response.xml is None:
                    raise OAIXMLError(
                        """{} Stop harvesting.
                        <div>The response may not be a XML page</div>""".format(
                            self._harvested_url
                        )
                    )
            raise exception

    def stop_iteration_log(self):
        if (
            not (self.resumption_token and self.resumption_token.token)
            and hasattr(self, "oai_response")
            and self.oai_response
        ):
            xml = self.oai_response.xml
            if hasattr(self.oai_response, "xml") and self.oai_response.xml is not None:
                if xml.tag == "html":
                    body = xml.find(".//body")
                    if body is not None:
                        try:
                            body = etree.tostring(body[0], encoding="utf-8")
                            self.sickle.logger.error(body)
                        except Exception:
                            pass
                    raise OAIXMLError(
                        """Stop harvesting. No resumptionToken found in {}.
                        Got HTML instead of XML: the service may be unavailable.
                        """.format(
                            self._harvested_url
                        )
                    )
            elif hasattr(self.oai_response, "raw") and self.oai_response.raw:
                if "<resumptionToken" in self.oai_response.raw:
                    raise OAIXMLError(
                        """Stop harvesting. No resumptionToken found in "{}".
                        <div>The XML may not be valid</div>""".format(
                            self._harvested_url
                        )
                    )

    def next(self):
        """Return the next record/header/set.
        FranceArchives customizations:
          - add logs about harvested uri;
          - add `harvested_url` attribute on returned Record.
        """
        try:
            record = super(PniaOAIItemIterator, self).next()
            record.harvested_url = self._harvested_url
            record.cursor, record.complete_list_size = None, None
            if self.resumption_token:
                record.cursor = self.resumption_token.cursor
                record.complete_list_size = self.resumption_token.complete_list_size
            return record
        except StopIteration:
            self.stop_iteration_log()
            raise StopIteration
        except Exception:
            if self.resumption_token and self.resumption_token.token:
                self._next_response()
            else:
                self.stop_iteration_log()
                raise StopIteration


def compute_oai_id(base_url, identifier):
    """Compute an unique identifier based on record identifier and OAI repository url"""
    if isinstance(base_url, str):
        base_url = base_url.encode("utf-8")
    return "{}_{}".format(hashlib.sha1(base_url).hexdigest(), identifier)
