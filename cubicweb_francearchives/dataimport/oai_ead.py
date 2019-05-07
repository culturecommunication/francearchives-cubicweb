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
from __future__ import print_function, unicode_literals

import lxml.etree

from collections import defaultdict

from cubicweb_francearchives.dataimport import (es_bulk_index, oai_utils,
                                                OAIPMH_EAD_PATH)
from cubicweb_francearchives.dataimport.ead import Reader, readerconfig
from cubicweb_francearchives.dataimport.eadreader import cleanup_ns


class OAIEADWriter(oai_utils.OAIPMHWriter):
    """OAI-PMH writer (EAD)."""

    def get_file_contents(self, metadata):
        """Get file contents.

        :param _Element metadata: contents of metadata tag
        """
        file_contents = lxml.etree.tostring(
            metadata, encoding="utf-8", xml_declaration=True
        )
        return file_contents


class OAIEadReader(object):

    def __call__(self, record, *args, **kwargs):
        return cleanup_ns(record[0])


def import_oai_ead(store, records, service_infos, log):
    """Import records based on OAI EAD standard.

    :param RQLObjectStore store: store
    :param function records: read-in records (generator)
    :param dict service_infos: service information
    :param Logger log: logger
    """
    cnx = store._cnx
    cwconfig = cnx.vreg.config
    reader = Reader(
        readerconfig(
            cwconfig, cwconfig.appid,
            log=log, esonly=False, nodrop=True, reimport=True,
            force_delete=True
        ),
        store
    )
    indexer = cnx.vreg["es"].select("indexer", cnx)
    stable_ids = defaultdict(list)
    writer = OAIEADWriter(cwconfig["ead-services-dir"], service_infos)
    directory = writer.makedir(subdirectories=OAIPMH_EAD_PATH.split('/'))
    for i, (header, metadata, about) in enumerate(records):
        if metadata is None:
            log.warning("no metadata found")
            continue
        identifier = header.identifier()
        eadid = metadata.findtext(".//eadid")
        if not eadid:
            msg = "no EADID value found for record %r"
            log.warning(msg, identifier)
            continue
        log.info("importing %r, eadid %r", identifier, eadid)
        stable_ids[eadid].append(eadid)
        existing_eadids = stable_ids.get(eadid, [])
        if len(existing_eadids) > 1:
            existing_eadids.pop()
            msg = (
                "record %r, eadid %r ignored:"
                "a record with the same eadid"
                "has already been imported in this harvest session (%r)"
            )
            log.warning(
                msg, identifier, eadid, existing_eadids[0]
            )
            continue
        try:
            file_path = writer.get_file_path(directory, eadid)
            file_contents = writer.get_file_contents(metadata)
            writer.dump(file_path, file_contents)
            findingaid_support = reader.create_file(file_path)
            if findingaid_support is None:
                # the file exists and will not be reimported
                continue
            es_docs = reader.import_ead_xmltree(
                metadata, service_infos, findingaid_support
            )
        except Exception as exception:
            log.warning("ignoring finding aid %r: %s", eadid, exception)
            es_docs = []
        if es_docs:
            es_bulk_index(indexer.get_connection(), es_docs)
        store.flush()
