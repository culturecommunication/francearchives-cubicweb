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
"""cubicweb-pnia-eac entity's classes"""
from collections import OrderedDict
import datetime
from lxml import etree

from cubicweb_francearchives.views import html_link

import cubicweb_eac.entities as eac


format_dates = "{0.day:2d}/{0.month:02d}/{0.year:4d}"


def format_eac_dates(start_date, end_date):
    """for dates processing see https://extranet.logilab.fr/ticket/6637699066376990"""
    dates = []
    today = datetime.date.today()
    for date_ in (start_date, end_date):
        if date_:
            if date_ > today:
                continue
            date_ = format_dates.format(date_)
        if date_ and date_ not in dates:
            # avoid start_date == end_date
            dates.append(date_)
    return "-".join(dates)


def filter_none(func):
    def wrapper(*args, **kwargs):
        def filter_values(value):
            if isinstance(value, dict):
                return OrderedDict([(k, filter_values(v)) for (k, v) in list(value.items()) if v])
            elif isinstance(value, list):
                return [filter_values(v) for v in value if v]
            elif value:
                return value

        result = func(*args, **kwargs)
        return OrderedDict([(k, filter_values(v)) for (k, v) in list(result.items()) if v])

    return wrapper


class AuthorityRecord(eac.AuthorityRecord):
    rest_attr = "record_id"

    def __init__(self, req, **extra):
        super(AuthorityRecord, self).__init__(req, **extra)
        self._authorized_nameentiry = None

    @property
    def authorized_nameentiry(self):
        """ Initialize the NameEntry of "authorized" form variant, if any; otherwise any
        NameEntry.
        """
        if self._authorized_nameentiry is None:
            rset = self._cw.find("NameEntry", name_entry_for=self, form_variant="authorized")
            if not rset:
                rset = self._cw.find("NameEntry", name_entry_for=self)
            self._authorized_nameentiry = next(rset.entities())
        return self._authorized_nameentiry

    def dc_title(self):
        """A NameEntry of "authorized" form variant, if any; otherwise any
        NameEntry.
        """
        return self.authorized_nameentiry.parts

    def other_names_rset(self):
        """Get all declared NameEntries for this AuthorityRecord other then the authorized one
        """
        return self._cw.execute(
            """
        Any X, P, SD, ED ORDERBY SD, ED, P WHERE
        X is NameEntry, X parts P,
        X name_entry_for A, NOT X eid  %(auteid)s,
        X date_relation D?, D start_date SD, D end_date ED,
        A eid %(eid)s
        """,
            {"auteid": self.authorized_nameentiry.eid, "eid": self.eid},
        )

    def parallel_names_rset(self):
        """Get all declared ParallelNames for this AuthorityRecord
        """
        return self._cw.execute(
            """
        Any P WHERE P is ParallelNames,
        P parallel_names_of X,
        X eid %(eid)s""",
            {"eid": self.eid},
        )

    def ternary_relations_rset(self, etype, rtype_from, rtype_to):
        query = """
        DISTINCT Any H, C WITH H, C BEING (
        (Any H, C WHERE H is {etype},
         H {rtype_from} X, H {rtype_to} C, X eid %(eid)s, NOT C eid %(eid)s)
        UNION
        (Any H, C WHERE H is {etype},
        H {rtype_to} X, H {rtype_from} C, X eid %(eid)s, NOT C eid %(eid)s)
        )
        """
        return self._cw.execute(
            query.format(etype=etype, rtype_from=rtype_from, rtype_to=rtype_to), {"eid": self.eid}
        )

    def resource_relations_rset(self):
        return self._cw.execute(
            """
        Any R ,C  WHERE R is EACResourceRelation,
        R resource_relation_agent X,
        R resource_relation_resource C, NOT C eid %(eid)s,
        X eid %(eid)s""",
            {"eid": self.eid},
        )

    def function_relations_rset(self):
        return self._cw.execute(
            """
        Any R, C WHERE R is EACFunctionRelation,
        R function_relation_agent X,
        R function_relation_function C, NOT C eid %(eid)s,
        X eid %(eid)s
        """,
            {"eid": self.eid},
        )

    def agent_place_rset(self):
        return self._cw.execute(
            """
        Any A, C, R, I, CN, CI WHERE A is AgentPlace,
        A place_agent X, A role R, A items I,
        A has_citation C?, C note CN, C uri CI,
        X eid %(eid)s""",
            {"eid": self.eid},
        )

    def maintenance_events_rset(self):
        return self._cw.execute(
            """
        Any M, S, E, D, T, A, AT ORDERBY S DESC LIMIT 1 WHERE M is Activity,
        M generated X OR M used X,
        M start S, M end E, M description D,
        M type T, M agent A, M agent_type AT,
        X eid %(eid)s""",
            {"eid": self.eid},
        )

    @property
    def main_infos(self):
        if self.isni:
            format_infos = lambda x, y: "{}<br>{}".format(x, y)
        else:
            format_infos = lambda x, y: x
        return OrderedDict(
            [(self._cw._("record_id_label"), format_infos(self.record_id, self.isni))]
        )

    @property
    def main_date(self):
        """A NameEntry of "authorized" form variant, if any; otherwise any
        NameEntry.
        """
        return format_eac_dates(self.start_date, self.end_date)

    def name_entry(self, klass="list list-unstyled", subvid="francearchives.eac"):
        rset_names = self.other_names_rset()
        rset_parallel = self.parallel_names_rset()
        views = []
        if rset_names:
            view_names = self._cw.vreg["views"].select("list", self._cw, rset=rset_names)
            views.append(view_names.render(klass=klass, subvid=subvid))
        if rset_parallel:
            view_parallel = self._cw.vreg["views"].select("list", self._cw, rset=rset_parallel)
            views.append(view_parallel.render(klass=klass, subvid=subvid))
        if views:
            return {self._cw._("name_entries_label"): views}
        return {}

    @property
    def agency(self):
        return self.reverse_agency_of[0] if self.reverse_agency_of else None

    @property
    def related_service(self):
        return self.maintainer[0] if self.maintainer else None

    @staticmethod
    def extract_from_tag(xml_str, name):
        values = OrderedDict()
        elem = etree.fromstring(xml_str)
        values[name] = elem.text.strip()
        # values.update(elem.attrib)
        return values

    @property
    def language_used(self):
        if self.languages:
            return {self._cw._("language_used_label"): self.languages}
        return {}

    @property
    def function_relations(self):
        return {
            self._cw._("function_relation_label"): self.relation_views(self.function_relations_rset)
        }

    def relation_views(self, rset_generator, **kw):
        rset = rset_generator()
        if rset:
            view = self._cw.vreg["views"].select("francearchives.eac.list", self._cw, rset=rset)
            return view.render()
        return {}

    @property
    def cpf_relations(self):
        return {
            self._cw._("cpf_relations_label"): OrderedDict(
                [
                    (
                        self._cw._("associative_link_label"),
                        self.ternary_relation_views(
                            "AssociationRelation",
                            rtype_from="association_from",
                            rtype_to="association_to",
                        ),
                    ),
                    (
                        self._cw._("temporal_link_label"),
                        self.ternary_relation_views(
                            "ChronologicalRelation",
                            rtype_from="chronological_predecessor",
                            rtype_to="chronological_successor",
                        ),
                    ),
                    (
                        self._cw._("hierarchical_link_label"),
                        self.ternary_relation_views(
                            "HierarchicalRelation",
                            rtype_from="hierarchical_parent",
                            rtype_to="hierarchical_child",
                        ),
                    ),
                    (
                        self._cw._("identity_link_label"),
                        self.ternary_relation_views(
                            "IdentityRelation", rtype_from="identity_from", rtype_to="identity_to"
                        ),
                    ),
                    (
                        self._cw._("family_link_label"),
                        self.ternary_relation_views(
                            "FamilyRelation", rtype_from="family_from", rtype_to="family_to"
                        ),
                    ),
                ]
            )
        }

    def ternary_relation_views(self, etype, **kw):
        rset = self.ternary_relations_rset(etype, kw["rtype_from"], kw["rtype_to"])
        if rset:
            view = self._cw.vreg["views"].select("francearchives.eac.list", self._cw, rset=rset)
            return view.render()
        return {}

    @property
    def places(self):
        rset = self.agent_place_rset()
        if rset:
            view = self._cw.vreg["views"].select("francearchives.eac", self._cw, rset=rset)
            return {self._cw._("places_label"): view.render()}
        return {}

    @property
    def maintenance_events(self):
        rset = self.maintenance_events_rset()
        if rset:
            view = self._cw.vreg["views"].select(
                "francearchives.eac", self._cw, rset=rset, klass="maintenance-event"
            )
            return {self._cw._("maintenance_event_label"): view.render()}
        return {}

    @property
    def history(self):
        rset = self.related("history_agent", role="object")
        if rset:
            view = self._cw.vreg["views"].select("francearchives.eac", self._cw, rset=rset)
            return {self._cw._("history_label"): view.render()}
        return {}

    @property
    def functions(self):
        rset = self.related("function_agent", role="object")
        if rset:
            view = self._cw.vreg["views"].select("francearchives.eac", self._cw, rset=rset)
            return {self._cw._("functions_label"): view.render()}
        return {}

    @property
    def mandates(self):
        rset = self.related("mandate_agent", role="object")
        if rset:
            view = self._cw.vreg["views"].select("francearchives.eac", self._cw, rset=rset)
            return {self._cw._("mandates_label"): view.render()}
        return {}

    @property
    def resource_relations(self):
        return {
            self._cw._("resource_relation_label"): self.relation_views(self.resource_relations_rset)
        }

    @property
    def general_context(self):
        return {
            self._cw._("general_context_label"): [
                e.content for e in self.reverse_general_context_of
            ]
        }

    @property
    def occupations(self):
        rset = self.related("occupation_agent", role="object")
        if rset:
            view = self._cw.vreg["views"].select("francearchives.eac", self._cw, rset=rset)
            return {self._cw._("occupation_label"): view.render()}
        return {}

    @property
    def legal_statuses(self):
        rset = self.related("legal_status_agent", role="object")
        if rset:
            view = self._cw.vreg["views"].select("francearchives.eac", self._cw, rset=rset)
            return {self._cw._("legal_statuses_label"): view.render()}
        return {}

    @property
    def structure(self):
        rset = self.related("structure_agent", role="object")
        if rset:
            view = self._cw.vreg["views"].select("francearchives.eac", self._cw, rset=rset)
            return {self._cw._("structure_label"): view.render()}
        return {}

    @property
    def source_entry(self):
        rset = self.related("source_agent", role="object")
        if rset:
            view = self._cw.vreg["views"].select("francearchives.eac", self._cw, rset=rset)
            return {self._cw._("source_entry_label"): view.render()}
        return {}

    @property
    def authorities(self):
        _ = self._cw._
        indexes = []
        for label, etype in ((_("indexes_label"), "AgentAuthority"),):
            rset = self._cw.execute(
                """
                DISTINCT Any X, XP WHERE E eid %%(e)s,
                X is %s, EXISTS(R related_authority X) OR EXISTS(I authority X, I index FA),
                X same_as E, X label XP"""
                % etype,
                {"e": self.eid},
            )
            if rset:
                indexes.append((label, [e.view("outofcontext") for e in rset.entities()]))
        return OrderedDict(indexes)


class Citation(eac.Citation):
    @property
    @filter_none
    def displayable_attributes(self):
        note = self.printable_value("note")
        if self.uri:
            note += str(html_link(self._cw, self.uri, label=self._cw._("Consult the source")))
        return OrderedDict([(None, note)])


class GeneralContext(eac.GeneralContext):
    @property
    @filter_none
    def displayable_attributes(self):
        _ = self._cw._
        return OrderedDict([(_("content"), self.content), (_("items_label"), self.items)])


class EACRelation(object):
    def dc_title(self):
        return self.relation_entry or self._cw._("Missing title")


class EACFunctionRelation(EACRelation, eac.EACFunctionRelation):
    pass


class EACResourceRelation(EACRelation, eac.EACResourceRelation):
    pass


class DateEntity(eac.DateEntity):
    @property
    def raw_dates(self):
        if self.raw_date:
            dates = self.raw_date.split("-")
            if len(dates) == 1:
                return self.raw_date, None
            elif len(dates) == 2:
                return dates
        return None, None

    def format_date(self):
        """for dates processing see https://extranet.logilab.fr/ticket/6637699066376990"""
        dates = []
        today = datetime.date.today()
        raw_start_date, raw_end_date = self.raw_dates
        for date_, raw_date_ in ((self.start_date, raw_start_date), (self.end_date, raw_end_date)):
            if date_:
                if date_ > today:
                    continue
                if date_.day == 1 and date_.month == 1 and raw_date_:
                    date_ = raw_date_
                else:
                    date_ = format_dates.format(date_)
            else:
                date_ = raw_date_
            if date_ and date_ not in dates:
                # avoid start_date == end_date
                dates.append(date_)
        return "-".join(dates)

    @property
    def displayable_attributes(self):
        return self.format_date()


class PlaceEntry(eac.PlaceEntry):
    def dc_long_title(self):
        title = self.name
        info = self.local_type or ""
        geo = ", ".join([str(l) for l in (self.latitude, self.longitude) if l])
        if geo:
            info = " ; ".join([info, geo]) if info else geo
        if info:
            title = "{place} ({info})".format(place=title, info=info)
        return title


class History(eac.History):
    def dc_title(self):
        return self.abstract


class HistoricalEvent(eac.HistoricalEvent):
    def dc_title(self):
        return self.event


class Occupation(eac.Occupation):
    def dc_title(self):
        return self.term


class AgentFunction(eac.AgentFunction):
    def dc_title(self):
        return self.name


class Mandate(eac.Mandate):
    def dc_title(self):
        return self.term


class EACSource(eac.EACSource):
    def dc_title(self):
        return self.title


class LegalStatus(eac.LegalStatus):
    def dc_title(self):
        return self.term


class NameEntry(eac.NameEntry):
    @classmethod
    def cw_fetch_order(cls, select, attr, var):
        if attr == "parts":
            select.add_sort_var(var)
