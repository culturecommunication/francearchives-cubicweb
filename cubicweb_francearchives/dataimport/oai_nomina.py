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

from six import text_type as unicode

from cubicweb.dataimport.importer import ExtEntity


def qname(tag):
    return '{http://www.france-genealogie.fr/ns/nomina/1.0}' + tag


def first(value):
    return next(iter(value))


class OAINominaReader(object):

    def __init__(self):
        self.next_id = lambda c=count(1): next(c)

    def __call__(self, record, cnx, service_infos):
        """Generate extentities read from `record` etree"""
        record = record[0]
        death_year, dates = build_dates(record)
        locations = build_locations(record)
        persons = build_persons(record, death_year, dates, locations)
        if service_infos:
            service_eid = service_infos.get('eid')
            service_name = service_infos.get('name')
        else:
            service_eid = service_name = None
        for person in persons:
            if service_eid:
                # use service extid, not eid
                person['service'] = u'service-{}'.format(service_eid)
            # "publisher" is supposed to be required
            person['publisher'] = service_name or u'unknown'
            person_id = self.next_id()
            person = ExtEntity('Person', person_id, format_data(person))
            yield person


def build_dates(record):
    death_year = None
    dates_description = u''
    for date in record.findall(qname('date')):
        year = date.attrib.get('annee')
        code = date.get('code', u'')
        if code in ('D', 'TD') and year:
            try:
                death_year = int(year)
            except ValueError:
                pass
        else:
            date = date.text or year
            dates_description += u'<li class="{0}">{1}</li>'.format(code, date)
    if dates_description:
        dates_description = u'<ul>' + dates_description + u'</ul>'
    else:
        dates_description = None
    return death_year, dates_description


def build_persons(record, death_year=None, dates=None, locations=None):
    person_data = []
    uri = record.get('uri') or None
    for person in record.findall(qname('personne')):
        data = {
            'name': person.find(qname('nom')).text,
            'death_year': death_year,
            'dates_description': dates,
            'locations_description': locations,
            'document_uri': uri,
        }
        forenames = []
        for forenames_node in person.findall(qname('prenoms')):
            if forenames_node.text:
                forenames.append(forenames_node.text.strip())
        data['forenames'] = ' '.join(forenames)
        person_data.append(data)
    return person_data


def build_locations(record):
    locations_description = u''
    for location in record.findall(qname('localisation')):
        code = location.get('code', u'')
        location_fields = []
        pays = location.find(qname('pays'))
        if pays is not None and pays.text:
            location_fields.append(pays.text)
        department = location.find(qname('departement'))
        if department is not None and department.text:
            location_fields.append(department.text)
        precision = location.find(qname('precision'))
        if precision is not None and precision.text:
            location_fields.append(precision.text)
        if location_fields:
            locations_description += u'<li class="{0}">{1}</li>'.format(
                code, ', '.join(location_fields))
    if locations_description:
        locations_description = u'<ul>' + locations_description + u'</ul>'
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
    for key, value in values.items():
        if isinstance(value, str):
            value = {unicode(value)}
        else:
            value = {value}
        if value:
            formatted[key] = value
    return formatted
