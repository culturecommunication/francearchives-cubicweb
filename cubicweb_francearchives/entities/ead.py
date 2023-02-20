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

"""cubicweb-pnia-ead entity's classes"""
import os.path as osp
import json
from collections import defaultdict
import requests

from urllib.parse import urlparse

from logilab.common.decorators import cachedproperty

from cubicweb.predicates import is_instance
from cubicweb.entities.adapters import ITreeAdapter
from cubicweb.entities import AnyEntity, fetch_config

from cubicweb_elasticsearch.entities import IFullTextIndexSerializable

from cubicweb_francearchives import FEATURE_IIIF, get_user_agent
from cubicweb_francearchives.utils import is_absolute_url
from cubicweb_francearchives.entities import systemsource_entity
from cubicweb_francearchives.dataimport.ead import dates_for_es_doc, service_infos_for_es_doc


class FAComponentIFTIAdapter(IFullTextIndexSerializable):
    __select__ = IFullTextIndexSerializable.__select__ & is_instance("FAComponent", "FindingAid")

    @property
    def es_id(self):
        return self.entity.stable_id

    def serialize(self, complete=True, es_doc=None):
        entity = self.entity
        if es_doc is None:
            if "EsDocument" in entity.cw_rset.description[entity.cw_row]:
                # if an EsDocument is on the same row we assume it is the related es document
                doc_col = entity.cw_rset.description[entity.cw_row].index("EsDocument")
                esdoc = entity.cw_rset.get_entity(entity.cw_row, doc_col)
                es_doc = esdoc.doc
                if es_doc is None:
                    return {}
            else:
                es_doc = entity.reverse_entity
                if not es_doc:
                    return {}
                es_doc = es_doc[0].doc
                if es_doc is None:
                    return {}
        data = {
            "eid": entity.eid,
            "cwuri": entity.cwuri,
            "creation_date": entity.creation_date,
        }
        # This is a temporary fix, remove it after ESDocuments are updated
        if "service" not in es_doc or "dates" not in es_doc:
            if self.entity.cw_etype == "FindingAid":
                sql_query = """
                SELECT _S.cw_eid,_S.cw_code, _S.cw_level, _S.cw_name, _S.cw_name2,
                       _D.cw_startyear, _D.cw_stopyear
                FROM cw_Did AS _D, cw_FindingAid AS _X
                LEFT OUTER JOIN cw_Service AS _S ON (_X.cw_service=_S.cw_eid)
                WHERE _X.cw_did=_D.cw_eid AND _X.cw_eid=%(eid)s"""
            else:
                sql_query = """
                SELECT _S.cw_eid,_S.cw_code, _S.cw_level, _S.cw_name, _S.cw_name2,
                       _D.cw_startyear, _D.cw_stopyear
                FROM cw_Did AS _D, cw_FAComponent AS _X, cw_FindingAid AS _F
                LEFT OUTER JOIN cw_Service AS _S ON (_F.cw_service=_S.cw_eid)
                WHERE _X.cw_finding_aid=_F.cw_eid AND
                      _X.cw_did=_D.cw_eid AND
                      _X.cw_eid=%(eid)s
            """
            cu = self._cw.system_sql(sql_query, {"eid": self.entity.eid})
            rset = cu.fetchall()

            def service_title(level, name, name2):
                if level == "level-D":
                    return name2 or name
                else:
                    terms = [name, name2]
                    return " - ".join(t for t in terms if t)

            infos = [
                {
                    "startyear": startyear,
                    "stopyear": stopyear,
                    "service": {
                        "eid": s_eid,
                        "code": s_code,
                        "level": self._cw._(s_level),
                        "title": service_title(s_level, s_name, s_name2),
                    },
                }
                for (s_eid, s_code, s_level, s_name, s_name2, startyear, stopyear) in rset
            ][0]
            es_doc.update(service_infos_for_es_doc(self._cw, infos["service"]))
            es_doc.update(dates_for_es_doc(infos))

        if isinstance(es_doc, str):
            # sqlite return unicode instead of dict
            es_doc = json.loads(es_doc)
        es_doc.update(data)
        if "dates" in es_doc and not es_doc["dates"]:
            es_doc.pop("dates")
        return es_doc


class RecordITreeAdapter(ITreeAdapter):
    __regid__ = "ITree"
    __select__ = ITreeAdapter.__select__ & is_instance("FAComponent")
    tree_relation = "parent_component"


class IndexableMixin(object):
    def index_by_types(self):
        by_types = defaultdict(list)
        for index in self.index_entries:
            by_types[index.type].append(index)
        return by_types

    @cachedproperty
    def indices(self):
        return {
            "agents": self.agent_indexes().entities(),
            "subjects": self.subject_indexes().entities(),
            "locations": self.geo_indexes().entities(),
        }

    def main_indexes(self, itype):
        return self._cw.execute(
            "DISTINCT Any X, XP WHERE E eid %(e)s, "
            "X is AgentName, X index E, "
            "X label XP, X type %(t)s",
            {"t": itype, "e": self.eid},
        )

    def agent_indexes(self):
        return self._cw.execute(
            "DISTINCT Any X, XP, XT ORDERBY XP WHERE E eid %(e)s, "
            "X is AgentName, X index E, "
            "X label XP, X type XT",
            {"e": self.eid},
        )

    def subject_indexes(self):
        return self._cw.execute(
            "DISTINCT Any X, XP, XT ORDERBY XP WHERE E eid %(e)s, "
            "X is Subject, X index E, "
            "X label XP, X type XT",
            {"e": self.eid},
        )

    def subject_authority_indexes(self):
        return self._cw.execute(
            "DISTINCT Any A, AP WHERE E eid %(e)s, "
            "X is Subject, X index E, "
            "A label AP, X authority A",
            {"e": self.eid},
        )

    def geo_indexes(self):
        return self._cw.execute(
            "DISTINCT Any X, XP WHERE E eid %(e)s, X is Geogname, X index E, X label XP",
            {"e": self.eid},
        )


class FindingAidBaseMixin(object):
    def get_extptr_for_bounce_url(self, eadid, did):
        if did.extptr:
            # special handling for ANOM arks, we have to rebuild the full URL
            if did.extptr.startswith("ark:/"):
                if eadid.startswith("FRANOM"):
                    return "http://anom.archivesnationales.culture.gouv.fr/" + did.extptr
            else:
                return did.extptr

    @cachedproperty
    def bounce_url(self):
        """URL of the website the FindingAid originates from
        (cf. https://extranet.logilab.fr/ticket/64667749)
        """
        eadid = self.finding_aid[0].eadid
        did = self.did[0]
        extptr = self.get_extptr_for_bounce_url(eadid, did)
        if extptr:
            return extptr
        if self.cw_etype == "FindingAid" and self.website_url:
            return self.website_url
        if self.cw_etype == "FAComponent":
            fa = self.finding_aid[0]
            extptr = self.get_extptr_for_bounce_url(eadid, fa.did[0])
            if extptr:
                return extptr
            if fa.website_url:
                return fa.website_url
        if self.related_service:
            attrs = {"unittitle": did.unittitle, "unitid": did.unitid, "eadid": eadid}
            return self.related_service.bounce_url(attrs)

    @cachedproperty
    def digitized_urls(self):
        """List of URLs of related dao tags whose role is neither 'image' or 'thumbnail'."""
        urls = []
        for dv in self.digitized_versions:
            if dv.url:
                has_scheme = urlparse(dv.url).scheme
                if has_scheme:
                    urls.append(dv.url)
                else:
                    fa = self.finding_aid[0]
                    if fa.eadid.startswith("FRAD015"):
                        path = dv.url.replace("\\", "/")
                        urls.append(
                            "http://archives.cantal.fr/accounts/mnesys_ad15/datas/medias/{}".format(
                                path
                            )
                        )
        # try to sort urls especially for the case of viewer links such as
        # http://www.archinoe.fr/ark:/77293/c2mzpfn3jmb4ootg/1,
        # http://www.archinoe.fr/ark:/77293/c2mzpfn3jmb4ootg/N
        return sorted(urls)

    def unprocessed_illustration_url(self):
        dvs = self.digitized_versions
        if not dvs:
            return None
        # take first url with role 'thumbnail' or 'image'. Otherwise, take
        # any non null illustration url
        url = None
        for dv in dvs:
            if dv.illustration_url:
                url = dv.illustration_url
                if dv.role in {"thumbnail", "image"}:
                    break
        return url

    @property
    def thumbnail_dest(self):
        """Thumbnail target URL.

        The URI the user will be redirected to when clicking on the thumbnail.
        """
        illustration_url = self.unprocessed_illustration_url()
        if not illustration_url:
            return self.bounce_url
        if is_absolute_url(illustration_url):
            return illustration_url
        thumbnail_dest = self.related_service.thumbnail_dest if self.related_service else ""
        if thumbnail_dest:
            return thumbnail_dest.format(url=illustration_url)
        return self.bounce_url

    @property
    def illustration_url(self):
        """Illustration URL.

        The URL shown as the illustration's source. If there are related dao tags whose role
        is either 'image' or 'thumbnail', one of these tags' URL will be used. If no such dao
        tag exists, either one of the other associated dao tags' URL is returned (BnF) if there
        is any, or illustration_url is not set.
        If thumbnail_url is defined on the service, the URL will be formatted
        accordingly.
        """
        url = self.unprocessed_illustration_url()
        if url and is_absolute_url(url):
            return url
        service_code = self.related_service.code if self.related_service else None
        if not url and service_code == "FRBNF":
            # special case for BnF
            urls = [d.url for d in self.digitized_versions if d.url]
            url = urls[0] if urls else None
        if not url:
            return None
        # not service and not url is a relative URL (root or path unknown)
        if not urlparse(url).netloc and not self.related_service:
            return None
        if url.startswith("/"):
            url = url[1:]
        if service_code == "FRAD001":
            return (
                "http://hatch3.vtech.fr/cgi-bin/iipsrv.fcgi?"
                "FIF=/home/httpd/ad01/data/files/images"
                "/{eadid}/{url}&HEI=375&QLT=80&CVT=JPG&SIZE=1045163".format(
                    eadid=self.finding_aid[0].eadid.upper(), url=url
                )
            )
        elif service_code == "FRAD015":
            basepath, ext = osp.splitext(url)
            return (
                "http://archives.cantal.fr/accounts/mnesys_ad15/datas/medias/{}_{}_/0_0{}".format(
                    basepath.replace("\\", "/"), ext[1:], ext
                )
            )
        elif service_code == "QUAIBR75":
            basepath, ext = osp.splitext(url)
            return (
                "http://archives.quaibranly.fr:8990/accounts/"
                "mnesys_quaibranly/datas/{}_{}_/0_0{}".format(
                    basepath.replace("\\", "/"), ext[1:], ext
                )
            )
        else:
            if service_code == "FRAD085" and not url.isdigit():
                url = url.replace("\\", "/")
            if self.related_service and self.related_service.thumbnail_url:
                url = self.related_service.thumbnail_url.format(url=url)
        # relative URL (root or path unknown)
        if not url.startswith("http"):
            return None
        return url

    @cachedproperty
    def iiif_manifest(self):
        if not FEATURE_IIIF or not self.digitized_urls:
            return None
        manifest = None
        service = self.related_service
        if not service:
            self.error("No service found for %s (stable_id %s)", self, self.stable_id)
            return None
        if self._cw.vreg.config.get("instance-type") == "consultation" and not service.iiif_extptr:
            # so far in cms we try all services
            return None
        # services with iiif manifest url encoded in <extptr> (LIGEO editor)
        extptr = self.did[0].extptr
        if extptr and "ark:/" in extptr:
            manifest = f"{extptr.rstrip('/')}/manifest"
        if manifest:
            try:
                headers = {
                    "Accept": "application/json",
                    "user-agent": get_user_agent(),
                }
                response = requests.head(manifest, headers=headers)
                # should we check the manifest is a valid json file ?
            except Exception as ex:
                self.exception("[iiif urls] %s" % ex)
                return None
            if response.status_code >= 400:
                # XXX response.status_code != HTTPStatus.OK
                return None
            if "json" not in response.headers.get("Content-Type", "").lower():
                return None
            # or test response.json
        return manifest

    @property
    def qualified_index_authorities(self):
        """indexes with role other than "index" come from tags other than <origination>"""
        return self._cw.execute(
            """Any A,T WHERE I authority A, I index F, I type T,
                F eid %(eid)s, I role "index", A quality True""",
            {"eid": self.eid},
        )

    @property
    def qualified_originators(self):
        """indexes with role other than "index" come from <origination>"""
        return self._cw.execute(
            """DISTINCT Any A WHERE F eid %(e)s, I index F, NOT I role 'index',
            I authority A, A quality True""",
            {"e": self.eid},
        ).entities()


@systemsource_entity
class Did(AnyEntity):
    __regid__ = "Did"
    fetch_attrs, cw_fetch_order = fetch_config(["unitid", "unittitle", "startyear", "stopyear"])

    def dc_title(self):
        return self.unittitle or self.unitid or "???"

    @property
    def period(self):
        period = []
        if self.startyear:
            period.append(str(self.startyear))
        if self.stopyear:
            period.append(str(self.stopyear))
        return " - ".join(period)


@systemsource_entity
class FAComponent(IndexableMixin, FindingAidBaseMixin, AnyEntity):
    __regid__ = "FAComponent"
    fetch_attrs, cw_fetch_order = fetch_config(["component_order", "stable_id"], pclass=None)
    rest_attr = "stable_id"

    def dc_title(self):
        return self.did[0].dc_title()

    @cachedproperty
    def publisher(self):
        rset = self._cw.execute(
            "Any P WHERE X finding_aid FA, FA publisher P, X eid %(x)s", {"x": self.eid}
        )
        return rset[0][0]

    @cachedproperty
    def related_service(self):
        return self.finding_aid[0].related_service

    @cachedproperty
    def publisher_title(self):
        service = self.related_service
        if service:
            return self.related_service.dc_title()
        return self.publisher

    def children_components_stable_ids_and_labels(self):
        query = """Any FC, SI, LA WHERE
                X is FAComponent, X eid %(eid)s,
                FC parent_component X, FC stable_id SI,
                FC did D, D unittitle LA"""
        return self._cw.execute(query, {"eid": self.eid})


class FAHeader(AnyEntity):
    __regid__ = "FAHeader"

    def dc_title(self):
        if self.titlestmt:
            return self.titlestmt
        return "FAHeader #{}".format(self.eid)


@systemsource_entity
class FindingAid(IndexableMixin, FindingAidBaseMixin, AnyEntity):
    __regid__ = "FindingAid"
    fetch_attrs, cw_fetch_order = fetch_config(["stable_id", "did"])

    rest_attr = "stable_id"

    def dc_title(self):
        return self.fa_header[0].titleproper or self.did[0].dc_title()

    @property
    def finding_aid(self):
        """implement finding_aid to mimic FAComponent interface"""
        return [self]

    @property
    def service_code(self):
        if self.service and self.service[0].code:
            return self.service[0].code
        else:
            return self.eadid.split("_")[0]

    @cachedproperty
    def related_service(self):
        if hasattr(self, "service") and self.service:
            return self.service[0]

    @cachedproperty
    def services(self):
        return self.service

    @cachedproperty
    def publisher_title(self):
        service = self.related_service
        if service:
            return self.related_service.dc_title()
        return self.publisher

    def all_authorities_eids(
        self,
    ):
        """
        all distinct authorities eids for FindingAid and related FAComponent
        """
        query = """DISTINCT Any A WITH A BEING (
            (DISTINCT Any A WHERE I authority A, I index F,
                F eid %(eid)s, F is FindingAid)
            UNION
            (DISTINCT Any A WHERE I authority A, I index FA,
                F eid %(eid)s, FA finding_aid F)
            )"""
        return {eid[0] for eid in self._cw.execute(query, {"eid": self.eid})}

    def top_components_stable_ids_and_labels(self):
        query = """Any FC, SI, LA WHERE
                F is FindingAid, F eid %(eid)s,
                F top_components FC, FC stable_id SI,
                FC did D, D unittitle LA"""
        return self._cw.execute(query, {"eid": self.eid})


class DigitizedVersion(AnyEntity):
    __regid__ = "DigitizedVersion"
    fetch_attrs, cw_fetch_order = fetch_config(["url", "illustration_url", "role"])
