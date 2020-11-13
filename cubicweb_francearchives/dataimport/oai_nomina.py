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
from itertools import count

import logging

from sickle import Sickle
from sickle.models import Record

from cubicweb.dataimport.importer import ExtEntity
from cubicweb_francearchives.dataimport.ead import readerconfig
from cubicweb_francearchives.dataimport.oai_utils import PniaOAIItemIterator


def qname(tag):
    return "{http://www.france-genealogie.fr/ns/nomina/1.0}" + tag


def first(value):
    return next(iter(value))


class OAIENominaRecord(Record):
    def __init__(self, record_element, strip_ns=True):
        self.error = None
        try:
            super(OAIENominaRecord, self).__init__(record_element, strip_ns=strip_ns)
        except Exception as e:
            self.error = e
            return
        self.nomina = self.xml.find(".//" + self._oai_namespace + "metadata/")
        self.harvested_url = ""


class OAINominaImporter(object):
    """OAI Nomina schema importer.

    :ivar dict config: server-side configuration
    :ivar OAINominaReader reader: OAI Nomina schema reader
    :ivar Connection cnx: connection
    :ivar es: Elasticsearch connection
    """

    def __init__(self, store, config=None, log=None):
        """Initialize OAI Nomina schema reader.

        :param RQLObject store: store
        :param dict config: server-side configuration
        :param Logger log: logger
        """
        cwconfig = store._cnx.vreg.config
        if log is None:
            log = logging.getLogger("rq.task")
        self.log = log
        if config is None:
            config = readerconfig(
                cwconfig,
                cwconfig.appid,
                log=self.log,
                esonly=False,
                nodrop=True,
                reimport=True,
                force_delete=True,
            )
        self.config = config
        self.reader = OAINominaReader()

    def import_records(self, service_infos, headers, **params):
        """Harvest data and check they contain the needed information
        :param dict service_infos: service information
        :param dict params: harvest parameters
        """
        base_url = service_infos["oai_url"]
        oai_mapping = {
            "ListRecords": OAIENominaRecord,
            "GetRecord": OAIENominaRecord,
        }
        self.client = Sickle(
            base_url,
            iterator=PniaOAIItemIterator,
            class_mapping=oai_mapping,
            headers=headers,
            retry_status_codes=(500, 502, 503),
        )
        self.client.logger = self.log
        records = self.client.ListRecords(**params)
        for record in records:
            if record is None:
                # PniaOAIItemIterator raised an error before creating a record
                continue
            identifier = record.header.identifier
            url = record.harvested_url
            if record.deleted:
                self.log.info(
                    "%s. The record with identifier %r is set to be deleted. Nothing is done.",
                    url,
                    identifier,
                )
                continue
            self.log.info("%s. Oai identifier: %s", url, identifier)
            # directly import data whitout storing it on the filesystem
            for person in self.reader(record.nomina, service_infos):
                yield person


class OAINominaReader(object):
    def __init__(self):
        self.next_id = lambda c=count(1): next(c)

    def __call__(self, record, service_infos):
        """Generate extentities read from `record` etree"""
        death_year, dates = build_dates(record)
        locations = build_locations(record)
        persons = build_persons(record, death_year, dates, locations)
        if service_infos:
            service_eid = service_infos.get("eid")
            service_name = service_infos.get("name")
        else:
            service_eid = service_name = None
        for person in persons:
            if service_eid:
                # use service extid, not eid
                person["service"] = "service-{}".format(service_eid)
            # "publisher" is supposed to be required
            person["publisher"] = service_name or "unknown"
            person_id = self.next_id()
            person = ExtEntity("Person", person_id, format_data(person))
            yield person


def build_dates(record):
    death_year = None
    dates_description = ""
    for date in record.findall(qname("date")):
        year = date.attrib.get("annee")
        code = date.get("code", "")
        if code in ("D", "TD") and year:
            try:
                death_year = int(year)
            except ValueError:
                pass
        else:
            date = date.text or year
            dates_description += '<li class="{0}">{1}</li>'.format(code, date)
    if dates_description:
        dates_description = "<ul>" + dates_description + "</ul>"
    else:
        dates_description = None
    return death_year, dates_description


def build_persons(record, death_year=None, dates=None, locations=None):
    person_data = []
    uri = record.get("uri") or None
    for person in record.findall(qname("personne")):
        nomelt = person.find(qname("nom"))
        if nomelt is not None and nomelt.text:
            name = nomelt.text
        else:
            name = None
        data = {
            "name": name,
            "death_year": death_year,
            "dates_description": dates,
            "locations_description": locations,
            "document_uri": uri,
        }
        forenames = []
        for forenames_node in person.findall(qname("prenoms")):
            if forenames_node.text:
                forenames.append(forenames_node.text.strip())
        data["forenames"] = " ".join(forenames)
        person_data.append(data)
    return person_data


def build_locations(record):
    locations_description = ""
    for location in record.findall(qname("localisation")):
        code = location.get("code", "")
        location_fields = []
        pays = location.find(qname("pays"))
        if pays is not None and pays.text:
            location_fields.append(pays.text)
        department = location.find(qname("departement"))
        if department is not None and department.text:
            location_fields.append(department.text)
        precision = location.find(qname("precision"))
        if precision is not None and precision.text:
            location_fields.append(precision.text)
        if location_fields:
            locations_description += '<li class="{0}">{1}</li>'.format(
                code, ", ".join(location_fields)
            )
    if locations_description:
        locations_description = "<ul>" + locations_description + "</ul>"
    else:
        locations_description = None
    return locations_description


def format_data(values):
    """format `values` attributes dict

    - convert str to unicode
    - put values in sets
    - ignore None attributes
    """
    formatted = {}
    for key, value in list(values.items()):
        if isinstance(value, str):
            value = {str(value)}
        else:
            value = {value}
        if value:
            formatted[key] = value
    return formatted
