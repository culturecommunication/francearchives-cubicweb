# -*- coding: utf-8 -*-
#
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2022
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

"""cubicweb-pnia-content persons's classes"""
from collections import OrderedDict, defaultdict
import json

from logilab.common.decorators import cachedproperty
from logilab.common.textutils import unormalize

from cubicweb import _
from cubicweb.entities import AnyEntity, fetch_config
from cubicweb.predicates import is_instance, score_entity

from cubicweb_elasticsearch.entities import IFullTextIndexSerializable
from cubicweb_francearchives.dataimport import get_year

from cubicweb_francearchives.entities.adapters import EntityMainPropsAdapter

UnknownNominaActCode = "###"

# these is not really a single unique list of nomina act codes: services can use
# differents codes. We try to normalize them for ES indexation
# and translations. All codes must be present in NominaActCodeTypes with upper cases

NominaActCodeTypes = OrderedDict(
    {
        "A": _("NMN_A"),
        "AN": _("NMN_AN"),
        "B": _("NMN_BN"),
        "N": _("NMN_BN"),
        "TN": _("NMN_BN"),
        "BN": _("NMN_BN"),
        "NA": _("NMN_BN"),
        "BANS": _("NMN_BANS"),
        "CM": _("NMN_CM"),
        "CO": _("NMN_CO"),
        "DI": _("NMN_DI"),
        "F": _("NMN_F"),
        "JU": _("NMN_JU"),
        "M": _("NMN_M"),
        "MA": _("NMN_M"),
        "TM": _("NMN_M"),
        "MPF": _("NMN_MPF"),
        "MPF14-18": _("NMN_MPF14-18"),
        "MORT 14-18": _("NMN_M14-18"),
        "P": _("NMN_P"),
        "PER": _("NMN_P"),
        "PR": _("NMN_PR"),
        "PU": _("NMN_PU"),
        "R": _("NMN_R"),
        "RE": _("NMN_RE"),
        "REA": _("NMN_REA"),
        "RM": _("NMN_RM"),
        "RP": _("NMN_RP"),
        "RT": _("NMN_RT"),
        "S": _("NMN_S"),
        "D": _("NMN_S"),
        "TD": _("NMN_S"),
        "SD": _("NMN_S"),
        "SV": _("NMN_SV"),
        "T": _("NMN_RT"),
        "ZZ": _("NMN_AU"),
        "PM": _("NMN_AU"),
        # "JU": _("NMN_AU"),
        "RC": _("NMN_AU"),
        UnknownNominaActCode: _("NMN_Inconnu"),
    }
)

# Some code refer to the same event and must be merge in ES indexation
# All codes must be present un upper cases in NominaESActCodeTypes

NominaESActCodeTypes = {
    "B": "BN",
    "N": "BN",
    "TN": "BN",
    "NA": "BN",
    "MA": "M",
    "TM": "M",
    "PER": "P",
    "D": "S",
    "TD": "S",
    "SD": "S",
    "T": "RT",
    "ZZ": "AU",
    "PM": "AU",
    "RC": "AU",
}


def normalized_doctype_code(code):
    return unormalize(code).upper()


def nomina_translate_codetype(cnx, code):
    """use this function for translate document code"""
    if not code:
        code = UnknownNominaActCode
    code = normalized_doctype_code(code)
    return cnx._(NominaActCodeTypes.get(code, code))


NominaComplementCodes = OrderedDict(
    {
        "f": _("NMN_C_conflit"),
        "c": _("NMN_C_cote"),
        "e": _("NMN_C_education"),
        "n": _("NMN_C_nro"),
        "m": _("NMN_C_mention"),
        "o": _("NMN_C_occupations"),
        "a": _("NMN_C_autre"),
        "d": _("NMN_C_digitized"),
        "p": _("NMN_C_payant"),
    }
)


NominaEducationCodes = OrderedDict(
    {
        "0": _("NMN_E_0"),
        "1": _("NMN_E_1"),
        "2": _("NMN_E_2"),
        "3": _("NMN_E_3"),
        "4": _("NMN_E_4"),
        "5": _("NMN_E_5"),
    }
)


class NominaAttributesMixIn:
    @cachedproperty
    def persons(self):
        return self.data.get("p", [])

    @cachedproperty
    def persons_data(self):
        return [
            f'{person.get("n", "?") or "?"}, {person.get("f", "?") or "?"}'
            for person in self.persons
        ]

    @cachedproperty
    def events(self):
        return self.data.get("e", {})

    @cachedproperty
    def infos(self):
        return self.data.get("c") or {}

    @cachedproperty
    def occupations(self):
        return self.infos.get("o")

    @cachedproperty
    def education(self):
        return NominaEducationCodes.get(self.infos.get("e"))

    @cachedproperty
    def doctype_code(self):
        """
        doctype code should be mandatory
        """
        return self.data.get("t", UnknownNominaActCode)

    @cachedproperty
    def normalized_doctype_code(self):
        return normalized_doctype_code(self.doctype_code)

    @cachedproperty
    def doctype_type(self):
        return nomina_translate_codetype(self._cw, self.doctype_code)

    @cachedproperty
    def es_acte_type_code(self):
        """normalize doctype code for es indexation"""
        code = self.normalized_doctype_code
        return NominaESActCodeTypes.get(code, code)

    @cachedproperty
    def source_url(self):
        return self.data.get("u", None)

    @cachedproperty
    def digitized(self):
        return self.infos.get("d") == "y"

    def get_events(self, code):
        return self.events.get(code)

    def format_dates(self, dates):
        if not dates:
            return ""
        return self._cw._("; ").join([d.get("d", d.get("y", "")) for d in dates if d])

    def get_uncorrelated_dates(self, events):
        """dates issues from nomina oai are not correlated with their locations and are
        list or dictionary in a dictionary
        ex.
        {'d': [{'y': '1851'}], 'l': [{'d': 'Ardennes', 'p': 'Gespunsart'}]}
        :param list events: list of events
        :param boolean year: True
        """
        dates = events.get("d", [])
        if isinstance(dates, dict):
            return [dates]
        return dates

    def get_correlated_dates(self, events):
        """dates issues from csv are be correlated with their locations and are
        dictionary in a list
        ex. [{'d': {'y': '1867'},
              'l': {'p': 'Labrit', 'dc': '40', 'd': 'Landes', 'cc': 'FR', 'c': 'France'}}]

        :param list events: list of events
        return array
        """
        assert isinstance(events, (list, tuple))
        data = []
        for event in events:
            data.extend(self.get_uncorrelated_dates(event))
        return data

    def get_dates(self, code, fmt=True):
        """return "d" for a date, "y" for the exact year
        :param string code: code if the event
        :param boolean fmt: True for string result else array
        """
        dates = []
        events = self.get_events(code)
        if events is None:
            return "" if fmt else dates
        if isinstance(events, dict):
            # events comes from nomina oai
            dates = self.get_uncorrelated_dates(events)
        else:
            dates = self.get_correlated_dates(events)
        if fmt:
            return self.format_dates(dates)
        return dates

    @cachedproperty
    def acte_year(self):
        code = "D" if self.mpf_doctype else self.doctype_code
        date = self.get_dates(code, fmt=False)
        if type(date) == list:
            date = list(filter(None, [d.get("y", None) for d in date if d.get("y")]))
            return date[0] if date else ""
        return date.get("y", "").strip()

    def format_location(self, location):
        context = ", ".join([e for e in (location.get(c) for c in "dc") if e])
        precision = location.get("p")
        if precision:
            if context:
                return f"{precision} ({context})"
            return precision
        if context:
            dep = location.get("d")
            country = location.get("c")
            if dep and country:
                return f"{dep} ({country})"
            return dep or country
        return ""

    def format_locations(self, locations):
        if not isinstance(locations, (list, tuple)):
            locations = [locations]
        locations = [self.format_location(loc) for loc in locations]
        return self._cw._("; ").join(locations)

    def get_uncorrelated_locations(self, events):
        """location issues from nomina oai are not correlated with their dates and are
        list or dictionary in a dictionary
        ex.
        {'d': [{'y': '1851'}], 'l': [{'d': 'Ardennes', 'p': 'Gespunsart'}]}
        :param list events: list of events
        """
        locations = events.get("l", [])
        if isinstance(locations, dict):
            locations = [locations]
        return locations

    def get_correlated_locations(self, events):
        """location issues from csv are correlated with their dates and are a
        dictionary in a list
        ex. [{'d': {'y': '1867'},
              'l': {'p': 'Labrit', 'c': '40', 'd': 'Landes', 'cc': 'FR', 'c': 'France'}}]
        :param list events: list of events
        """
        assert isinstance(events, (list, tuple))
        data = []
        for event in events:
            data.extend(self.get_uncorrelated_locations(event))
        return data

    def get_locations(self, code, fmt=True):
        """return "c" for country, "d" for departement, "p" for precision
        :param String code: code if the event
        :param boolean fmt: True for string result else array
        """
        locations = []
        events = self.get_events(code)
        if events is None:
            return "" if fmt else locations
        if isinstance(events, dict):
            # events comes from nomina oai
            locations = self.get_uncorrelated_locations(events)
        else:
            locations = self.get_correlated_locations(events)
        return self.format_locations(locations) if fmt else locations

    def get_infos_data(self, skip="o"):
        data = []
        infos = self.data.get("c")
        if infos:
            for key, values in infos.items():
                if key in skip:
                    continue
                label = self._cw._(NominaComplementCodes[key])
                if key == "e":  # niveau
                    values = NominaEducationCodes.get(values)
                    if values:
                        values = self._cw._(values)
                data.append((label, values))
        return data

    def get_events_types(self, skip=()):
        keys = self.events.keys()
        if not skip:
            return keys
        keys = set(keys) - set(skip)
        return keys

    @cachedproperty
    def notice_id(self):
        """only exists for csv imported data"""
        return self.data.get("i") or None

    @cachedproperty
    def rm_doctype(self):
        return self.normalized_doctype_code in ("RM", "MPF14-18", "MORT 14-18", "MPF")

    @cachedproperty
    def mpf_doctype(self):
        return self.normalized_doctype_code in ("MPF14-18", "MORT 14-18", "MPF")


class NominaRecord(AnyEntity, NominaAttributesMixIn):
    __regid__ = "NominaRecord"
    fetch_attrs, cw_fetch_order = fetch_config(["stable_id", "json_data"], pclass=None)

    def dc_title(self):
        return self._cw._("; ").join(self.persons_data) or self._cw._("Unknown")

    def rest_path(self, use_ext_eid=False):
        return f"basedenoms/{self.stable_id}"

    @cachedproperty
    def data(self):
        data = self.json_data
        if isinstance(data, str):
            # sqlite return unicode instead of dict
            return json.loads(data)
        return data

    @cachedproperty
    def birth_date(self):
        return self.get_dates("N")

    @cachedproperty
    def death_date(self):
        return self.get_dates.get("D")

    @property
    def label(self):
        """property to ease compatibility with AgentName entities"""
        return self.dc_title()

    def agent_indexes(self):
        return self._cw.execute(
            """
            DISTINCT Any A, L ORDERBY L WHERE P eid %(e)s,
            P same_as A, A is AgentAuthority, A label L""",
            {"e": self.eid},
        )

    @cachedproperty
    def related_service(self):
        return self.service[0]

    @cachedproperty
    def publisher(self):
        return self.related_service.short_name

    @property
    def service_code(self):
        return self.related_service.code

    @cachedproperty
    def publisher_title(self):
        return self.related_service.dc_title()


class NominaRecordMainPropsAdapter(EntityMainPropsAdapter):
    __select__ = EntityMainPropsAdapter.__select__ & is_instance("NominaRecord")

    def get_event(self, code):
        """A string formatted version of an event for display"""
        event = self.entity.get_events(code)
        if event is None:
            return ""
        if isinstance(event, dict):
            dates = self.entity.get_dates(code, fmt=True)
            locations = self.entity.get_locations(code)
            return self._cw._("; ").join(d for d in (dates, locations) if d)
        else:  # list
            data = []
            for item in event:
                date = item.get("d", "")
                if date:
                    date = date.get("d", date.get("y"))
                loc = self.entity.format_location(item.get("l"))
                data.append(self._cw._("; ").join(d for d in (date, loc) if d))
            return data

    def event_props(self, export=False, vid="incontext", text_format="text/html"):
        _ = self._cw._
        props = []
        codes = self.entity.get_events_types(skip=["N", "D"])
        for code in codes:
            data = self.get_event(code)
            if data:
                props.append((nomina_translate_codetype(self._cw, code), data))
        return props

    def source_url(self):
        return self.entity.source_url

    def properties(self, export=False, vid="incontext", text_format="text/html"):
        self.text_format = text_format
        props = self.main_props(export=export, vid=vid, text_format=text_format)
        return [(label, value) for label, value in props if value]

    def main_props(self, export=False, vid="incontext", text_format="text/html"):
        entity = self.entity
        _ = self._cw._
        infos = self.entity.infos
        props = [
            (_(NominaActCodeTypes["N"]), self.get_event("N")),
            (_("Occupation"), entity.occupations),
            (_(NominaComplementCodes["e"]), _(self.entity.education)),
            (_(NominaActCodeTypes["D"]), self.get_event("D")),
            (_("Doctype_label"), entity.doctype_type),
            (_("Date and place of the event"), self.get_event(entity.doctype_code)),
            (_(NominaComplementCodes["c"]), infos.get("c")),
            (_(NominaComplementCodes["n"]), infos.get("n")),
        ]
        codes = self.entity.get_events_types(skip=["N", "D", entity.doctype_code])
        for code in codes:
            label = nomina_translate_codetype(self._cw, code)
            props.append((label, self.get_event(code)))
        props.append(
            (
                _("See other documents"),
                ", ".join(e.view("nomina_agent") for e in entity.agent_indexes().entities()),
            )
        )
        return props


class RMNominaRecordMainPropsAdapter(NominaRecordMainPropsAdapter):
    __select__ = NominaRecordMainPropsAdapter.__select__ & score_entity(lambda e: e.rm_doctype)

    def main_props(self, export=False, vid="incontext", text_format="text/html"):
        entity = self.entity
        _ = self._cw._
        infos = self.entity.infos
        props = [
            (_(NominaActCodeTypes["N"]), self.get_event("N")),
            (_("Occupation"), entity.occupations),
            (_(NominaComplementCodes["e"]), _(self.entity.education)),
            (_("Enrolment year and place"), self.get_event("RM")),
            (_(NominaActCodeTypes["D"]), self.get_event("D")),
            (_(NominaActCodeTypes["R"]), self.get_event("R")),
            (_("Doctype_label"), entity.doctype_type),
            (_(NominaComplementCodes["c"]), infos.get("c")),
            (_(NominaComplementCodes["n"]), infos.get("n")),
        ]
        props.append(
            (
                _("See other documents"),
                ", ".join(e.view("nomina_agent") for e in entity.agent_indexes().entities()),
            )
        )
        return props


class NominaIndexJsonDataSerializable(NominaAttributesMixIn):
    def __init__(self, cnx, json_data):
        self._cw = cnx
        self.data = json_data

    @cachedproperty
    def process_persons(self):
        data = defaultdict(list)
        for p in self.persons:
            names = p.get("n")
            if names:
                data["names"].append(names)
            forenames = p.get("f")
            if forenames:
                data["forenames"].append(forenames)
        return data

    @cachedproperty
    def process_locations(self):
        """compute all locations found in json_data"""
        data = set([])
        for key, events in self.events.items():
            if isinstance(events, dict):
                # events comes from nomina oai
                data |= self.get_event_locations(events)
            else:
                for event in events:
                    data |= self.get_event_locations(event)
        return sorted(list(data))

    def get_event_locations(self, events):
        data = set([])
        locations = events.get("l", [])
        if not locations:
            return data
        if isinstance(locations, dict):
            locations = [locations]
        for loc in locations:
            data |= set([v for k, v in loc.items() if k not in ("cc", "dc")])
        return data

    @cachedproperty
    def process_all_text(self):
        """compute all text from json_data
        do not index person, locations or publisher
        as they are copied to all_text in es mapping
        """
        _ = self._cw._
        content = []

        for label, value in self.get_infos_data(skip=[]):
            if type(value) in (list, tuple):
                value = ", ".join(value)
            if value:
                content.append(value)
        for event_type in list(self.get_events_types()):
            content.append(nomina_translate_codetype(self._cw, event_type))
            dates = self.get_dates(event_type)
            if dates:
                content.append(dates)
        return " ".join(content)

    @cachedproperty
    def process_dates(self):
        # confirmed in #74059989
        acte_year = self.acte_year
        # dates can be intervals #74118518
        start, stop = None, None
        if acte_year:
            for sep in "-/":
                if sep in acte_year:
                    try:
                        start, stop = [d.strip() for d in acte_year.split(sep)]
                    except ValueError:
                        pass
        if not stop and not start:
            start = acte_year.strip() if acte_year else acte_year
            stop = start

        # try transforming the dates to 4 digit integers
        startyear = get_year(start)
        stopyear = get_year(stop)

        if startyear and stopyear:  # the transformation succeeded (no non-digit characters)
            return {"gte": startyear, "lte": stopyear}
        return  # Do not return anything if the dates could not be properly parsed

    def process_json_data(self, alltext=None):
        """
        :param str alttext: additional text to index (used for authorities labels in import)
        """
        text = self.process_all_text
        if alltext:
            text += f" {alltext}"
        data = {
            "alltext": text,
            "acte_type": self.es_acte_type_code,
            "dates": self.process_dates,
        }
        if self.persons:
            data.update(self.process_persons)
        if self.events:
            data["locations"] = self.process_locations
        return data


class INominaIndexSerializable(IFullTextIndexSerializable):
    """Adapter to serialize Nomina data."""

    __regid__ = "INominaIndexSerializable"
    __select__ = is_instance("NominaRecord")
    skip_indexable_attributes = ("cwuri",)

    @property
    def es_id(self):
        return self.entity.stable_id

    def process_attributes(self):
        data = {}
        for attr in self.fulltext_indexable_attributes:
            if attr not in self.skip_indexable_attributes:
                data[attr] = getattr(self.entity, attr)
        adapter = NominaIndexJsonDataSerializable(self.entity._cw, self.entity.json_data)
        data.update(adapter.process_json_data())
        return data

    def serialize(self, complete=True):
        # TODO there is possible to have more than 1 person per notice
        # in which cas we shell produce as mutch ES documents with unique es_eid
        # While deleting a notice by stable_id, all related ES documents must be deleted as well
        entity = self.entity
        if complete:
            entity.complete()
        agents = entity.agent_indexes()
        data = {
            "cw_etype": entity.cw_etype,
            "eid": entity.eid,
            "cwuri": entity.absolute_url(),
            "service": entity.related_service.eid,
            "stable_id": entity.stable_id,
            "authority": [e[0] for e in agents],
        }
        attributes = self.process_attributes()
        if agents:
            attributes["alltext"] += " " + " ".join(e[1] for e in agents)
        data.update(attributes)
        return data
