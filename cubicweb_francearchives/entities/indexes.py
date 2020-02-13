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

import datetime
from collections import OrderedDict

from logilab.common.decorators import cachedproperty

from cubicweb import _
from cubicweb.predicates import is_instance
from cubicweb.entities import AnyEntity, fetch_config

from cubicweb_francearchives.dataimport import es_bulk_index
from cubicweb_francearchives.views import format_agent_date, STRING_SEP
from cubicweb_francearchives.entities.adapters import EntityMainPropsAdapter
from cubicweb_francearchives.utils import cut_words, remove_html_tags


class ExternalUri(AnyEntity):
    __regid__ = "ExternalUri"
    fetch_attrs, cw_fetch_order = fetch_config(["label", "uri", "source", "extid"])


class ExternalId(AnyEntity):
    __regid__ = "ExternalId"
    fetch_attrs, cw_fetch_order = fetch_config(["extid", "label", "source"])


class AbstractIndex(AnyEntity):
    __abstract__ = True
    fetch_attrs, cw_fetch_order = fetch_config(["label", "role", "type"])

    def dc_title(self):
        return self.label or self.authority[0].dc_title()

    @cachedproperty
    def findingaid(self):
        return self._cw.execute(
            "(DISTINCT Any FA WHERE X index FAC, FAC finding_aid FA, X eid %(e)s)"
            " UNION "
            "(DISTINCT Any FA WHERE X index FA, FA is FindingAid, X eid %(e)s)",
            {"e": self.eid},
        ).one()

    @property
    def authority_url(self):
        return self.authority[0].absolute_url()

    def new_authority(self):
        req = self._cw
        auth = req.create_entity(self.authority_type, label=self.label)
        prevauthority = self.authority[0].eid
        self.update_es_docs(prevauthority, auth.eid)
        self.cw_set(authority=auth)
        return auth

    def update_es_docs(self, oldauth, newauth):
        # update esdocument related to FAComponent,FindingAid linked to current index
        # first update postgres db
        # TODO : this probabl- must go to the cubicweb_frarchives_edition
        self._cw.system_sql(
            """
UPDATE
  cw_esdocument es
SET
  cw_doc = jsonb_set(
    es.cw_doc::jsonb,
    '{index_entries}',
    update_index_entries(
      es.cw_doc -> 'index_entries',
      %(oldauth)s,
      %(newauth)s
    )
  )
FROM
  ((
     SELECT fac.cw_eid
     FROM
       cw_facomponent fac
       JOIN index_relation ir ON ir.eid_to = fac.cw_eid
     WHERE ir.eid_from = %(indexeid)s
  ) UNION (
     SELECT fa.cw_eid
     FROM
       cw_findingaid fa
       JOIN index_relation ir ON ir.eid_to = fa.cw_eid
       WHERE ir.eid_from = %(indexeid)s
  )) fa
WHERE
  fa.cw_eid = es.cw_entity
        """,
            {"indexeid": self.eid, "oldauth": oldauth, "newauth": newauth},
        )
        # then update elasticsearch db
        indexer = self._cw.vreg["es"].select("indexer", self._cw)
        index_name = indexer.index_name
        es = indexer.get_connection()
        published_indexer = self._cw.vreg["es"].select("indexer", self._cw, published=True)
        docs = []
        published_docs = []
        for fa in self.index:
            serializable = fa.cw_adapt_to("IFullTextIndexSerializable")
            json = serializable.serialize()
            if not json:
                continue
            docs.append(
                {
                    "_op_type": "index",
                    "_index": index_name,
                    "_type": "_doc",
                    "_id": serializable.es_id,
                    "_source": json,
                }
            )
            if published_indexer:
                is_published = True
                if fa.cw_etype in ("FindingAid", "FAComponent"):
                    if fa.cw_etype == "FindingAid":
                        wf = fa.cw_adapt_to("IWorkflowable")
                    else:
                        wf = fa.finding_aid[0].cw_adapt_to("IWorkflowable")
                    is_published = wf and wf.state == "wfs_cmsobject_published"
                if is_published:
                    published_docs.append(
                        {
                            "_op_type": "index",
                            "_index": published_indexer.index_name,
                            "_type": "_doc",
                            "_id": serializable.es_id,
                            "_source": json,
                        }
                    )
            if len(docs) > 30:
                es_bulk_index(es, docs)
                if published_docs:
                    es_bulk_index(es, published_docs)
                docs = []
                published_docs = []
        es_bulk_index(es, docs)
        if published_docs:
            es_bulk_index(es, published_docs)


class AgentName(AbstractIndex):
    __regid__ = "AgentName"
    authority_type = "AgentAuthority"
    fetch_attrs, cw_fetch_order = fetch_config(["label", "type", "role"])


class Geogname(AbstractIndex):
    __regid__ = "Geogname"
    authority_type = "LocationAuthority"


class Subject(AbstractIndex):
    __regid__ = "Subject"
    authority_type = "SubjectAuthority"

    def rest_path(self):
        return "subjectname/{}".format(self.eid)


class AbstractAuthority(AnyEntity):
    __abstract__ = True

    def dc_title(self):
        return self.label or self._cw._("no label")

    def rest_path(self):
        type = self.cw_etype[:-9].lower()  # remove `Authority`
        return "{}/{}".format(type, self.eid)

    @property
    def itypes(self):
        return [
            t[0]
            for t in self._cw.execute(
                """DISTINCT Any T WHERE
            I authority X, I type T, X eid {eid}""".format(
                    eid=self.eid
                )
            ).rows
        ]

    def group(self, other_auth_eids):
        req = self._cw
        grouped_with = [e.eid for e in self.reverse_grouped_with]
        grouped_auths = [self]
        for autheid in other_auth_eids:
            try:
                autheid = int(autheid)
            except Exception:
                continue
            if autheid == self.eid:
                # do not group with itself
                continue
            if autheid in grouped_with:
                # already grouped with
                continue
            auth = req.entity_from_eid(autheid)
            grouped_auths.append(auth)
            if auth.cw_etype != self.cw_etype:
                continue
            # rewrite `index_entries` in related es docs
            for index in auth.reverse_authority:
                index.update_es_docs(oldauth=auth.eid, newauth=self.eid)
            kwargs = {"new": self.eid, "old": autheid}
            # redirect index entities from old authority to new authority
            req.execute(
                "SET I authority NEW WHERE NEW eid %(new)s, I authority OLD, OLD eid %(old)s",
                kwargs,
            )
            # redirect related ExternRefs and CommemorationItems from old authority to new authority
            req.execute(
                """SET E related_authority NEW WHERE NEW eid %(new)s,
                   E related_authority OLD, OLD eid %(old)s""",
                kwargs,
            )
            # delete related ExternRefs and CommemorationItems from old authority
            req.execute("""DELETE E related_authority OLD WHERE OLD eid %(old)s""", kwargs)
            # set the grouped_with relation from the old authority to new
            # authority
            req.execute("SET OLD grouped_with NEW WHERE OLD eid %(old)s, NEW eid %(new)s", kwargs)
            # remove the possible grouped_with relation from the new authority
            # to the old
            req.execute(
                "DELETE NEW grouped_with OLD WHERE OLD eid %(old)s, NEW eid %(new)s", kwargs
            )
            # update all possible grouped_with subjects of the old authority
            # to the new authority
            req.execute(
                "SET O grouped_with NEW WHERE "
                "O grouped_with OLD, OLD eid %(old)s, NEW eid %(new)s",
                kwargs,
            )
        return grouped_auths

    @cachedproperty
    def same_as_refs(self):
        urls = []
        for ref in self.same_as:
            if ref.cw_etype == "ExternalUri":
                urls.append(ref.uri)
            else:
                urls.append(ref.absolute_url())
        return urls

    def add_to_auth_history(self):
        """
        add information of authority indexes and linked FindingAids to the `authority_history`
        table.
        TODO: update esdocument of FAComponents and FindingAids linked to the authority
        """
        indexes = self.reverse_authority
        if not indexes:
            return
        query = """
        INSERT INTO authority_history (fa_stable_id, type, label, indexrole, autheid)
        (
            SELECT DISTINCT fa.cw_stable_id, index.cw_type,
                            index.cw_label, index.cw_role, auth.cw_eid
            FROM cw_{authtable} auth
            JOIN cw_{indextable} as index ON index.cw_authority=auth.cw_eid
            JOIN index_relation i ON i.eid_from = index.cw_eid
            JOIN cw_findingaid fa ON fa.cw_eid = i.eid_to
            WHERE auth.cw_eid = {autheid}
                  AND auth.cw_label != index.cw_label
            UNION
            SELECT DISTINCT fa.cw_stable_id, index.cw_type,
                            index.cw_label, index.cw_role, auth.cw_eid
            FROM cw_{authtable} auth
            JOIN cw_{indextable} as index ON index.cw_authority=auth.cw_eid
            JOIN index_relation i ON i.eid_from = index.cw_eid
            JOIN cw_facomponent fac ON fac.cw_eid = i.eid_to
            JOIN cw_findingaid fa ON fa.cw_eid = fac.cw_finding_aid
            WHERE auth.cw_eid = {autheid}
                AND auth.cw_label != index.cw_label
                AND i.eid_from = index.cw_eid
        )
        ON CONFLICT (fa_stable_id, type, label, indexrole)
        DO UPDATE SET autheid = EXCLUDED.autheid
        ;"""
        self._cw.system_sql(
            query.format(
                autheid=self.eid,
                authtable=self.cw_etype.lower(),
                indextable=indexes[0].cw_etype.lower(),
            )
        )


class LocationAuthority(AbstractAuthority):
    __regid__ = "LocationAuthority"

    @property
    def itypes(self):
        return ()


class AgentAuthority(AbstractAuthority):
    __regid__ = "AgentAuthority"
    _index_type = None

    @property
    def index_type(self):
        if not self._index_type:
            self._index_type = "persname" if "persname" in self.itypes else "other"
        return self._index_type


class AgentAuthorityMainPropsAdapter(EntityMainPropsAdapter):
    __select__ = is_instance("AgentAuthority")
    _eac_info = None
    _agent_info = None
    date_labels = {
        "birthdate": {"persname": _("birth_date_label"), "other": _("start_date_label")},
        "deathdate": {"persname": _("death_date_label"), "other": _("stop_date_label")},
    }

    def properties(self, export=False, vid="incontext", text_format="text/html"):
        eac_info = self.eac_info(vid=vid, text_format=text_format)
        if eac_info:
            return list(eac_info["properties"].items())
        agent_info = self.agent_info(vid=vid, text_format=text_format)
        if agent_info:
            return list(agent_info["properties"].items())
        return []

    def eac_info(self, vid="incontext", text_format="text/html"):
        """EAC notice to be displayed."""
        if self._eac_info is None:
            self._eac_info = {}
            rset = self._cw.execute(
                """Any X, H, AF, OC, HA, HT, AFN, OCT, SD, ED ORDERBY SD LIMIT 1
                WHERE X is AuthorityRecord,
                X start_date SD, X end_date ED,
                H history_agent X,
                H abstract HA, H text HT,
                AF? function_agent X, AF name AFN,
                OC? occupation_agent X, OC term OCT,
                A same_as X, A eid {eid}""".format(
                    eid=self.entity.eid
                )
            )
            if rset:
                _ = self._cw._
                eac = rset.one()
                dates = {}
                properties = OrderedDict()
                for dtype, dateobj in (("birthdate", eac.start_date), ("deathdate", eac.end_date)):
                    if not dateobj:
                        continue
                    dates[dtype] = {
                        "timestamp": dateobj.strftime("%4Y-%m-%d"),
                        "precision": "d",
                        "isdate": True,
                        "isbc": False,
                    }
                    label = self.date_labels[dtype][self.entity.index_type]
                    properties[_(label)] = format_agent_date(self._cw, dateobj)
                self._eac_info["dates"] = dates
                self._eac_info["description"] = "\n".join(
                    remove_html_tags(f.text or f.abstract or "") for f in eac.reverse_history_agent
                )
                properties[_("eac_biogist_label")] = cut_words(self._eac_info["description"], 280)
                properties[_("eac_occupation_label")] = " ; ".join(
                    f.dc_title() for f in eac.reverse_occupation_agent
                )
                properties[_("eac_function_label")] = " ; ".join(
                    f.dc_title() for f in eac.reverse_function_agent
                )
                properties[_("eac_source_label")] = eac.view("maintainer.outofcontext")
                # if EAC and/or Wikidata and/or data.bnf.fr exist show
                # 1st EAC
                # 2nd Wikidata
                # 3rd data.bnf.fr
                see_also = sorted(
                    [e for e in self.entity.same_as if e.eid != eac.eid],
                    key=lambda x: getattr(x, "source", "z"),
                    reverse=True,
                )
                properties[_("see_also_label")] = "<br>".join(e.view(vid) for e in see_also)
                self._eac_info["properties"] = properties
        return self._eac_info

    def agent_info(self, vid="incontext", text_format="text/html"):
        """External agent information to be displayed."""
        if self._agent_info is None:
            self._agent_info = {}
            # ORDERBY S DESC if both Wikidata and data.bnf.fr exist use Wikidata
            rset = self._cw.execute(
                """Any E, S, U, A, DT, D ORDERBY S DESC LIMIT 1
                WHERE X same_as E, E is ExternalUri,
                E source in ('wikidata', 'databnf'), E source S, E uri U,
                A? agent_info_of E, A dates DT, A description D, X eid {eid}
                """.format(
                    eid=self.entity.eid
                )
            )
            if rset:
                _ = self._cw._
                properties = OrderedDict()
                exturi_eid, source, uri, agent, dates, description = rset.rows[0]
                dates = dates if dates else {}
                self._agent_info["dates"] = dates
                for dtype in ("birthdate", "deathdate"):
                    if not dates.get(dtype):
                        continue
                    # do not display malformatted Wikidata dates
                    if not dates[dtype]["isdate"] and source == "wikidata":
                        continue
                    label = self.date_labels[dtype][self.entity.index_type]
                    if dates[dtype]["isdate"]:
                        datestr = format_agent_date(
                            self._cw,
                            datetime.datetime.strptime(dates[dtype]["timestamp"], "%Y-%m-%d"),
                            precision=dates[dtype]["precision"],
                            isbc=dates[dtype]["isbc"],
                            iso=dates[dtype]["isiso"],
                        )
                    else:
                        datestr = dates[dtype]["timestamp"]
                    properties[_(label)] = datestr
                self._agent_info["description"] = description if description else ""
                properties[_("eac_biogist_label")] = "<br>".join(
                    self._agent_info["description"].split(STRING_SEP)
                )
                exturi = self._cw.entity_from_eid(exturi_eid)
                properties[_("same_as_label")] = exturi.view(vid)
                properties[_("see_also_label")] = "<br>".join(
                    e.view(vid) for e in self.entity.same_as if e.eid != exturi.eid
                )
                self._agent_info["properties"] = properties
        return self._agent_info


class SubjectAuthority(AbstractAuthority):
    __regid__ = "SubjectAuthority"

    @property
    def itypes(self):
        return ()
