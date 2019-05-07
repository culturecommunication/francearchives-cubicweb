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

from six import text_type
from six.moves.urllib.parse import urlparse

from logilab.common.decorators import cachedproperty

from cubicweb.predicates import is_instance
from cubicweb.entities.adapters import ITreeAdapter
from cubicweb.entities import AnyEntity, fetch_config

from cubicweb_elasticsearch.entities import IFullTextIndexSerializable

from cubicweb_francearchives.entities import systemsource_entity


class FAComponentIFTIAdapter(IFullTextIndexSerializable):
    __select__ = (IFullTextIndexSerializable.__select__
                  & is_instance('FAComponent', 'FindingAid'))

    @property
    def es_id(self):
        return self.entity.stable_id

    def serialize(self, complete=True, es_doc=None):
        entity = self.entity
        if es_doc is None:
            if 'EsDocument' in entity.cw_rset.description[entity.cw_row]:
                # if an EsDocument is on the same row we assume it is the related es document
                doc_col = entity.cw_rset.description[entity.cw_row].index('EsDocument')
                esdoc = entity.cw_rset.get_entity(entity.cw_row, doc_col)
                es_doc = esdoc.doc
            else:
                es_doc = entity.reverse_entity
                if not es_doc:
                    return {}
                es_doc = es_doc[0].doc
        data = {
            'eid': entity.eid,
            'cwuri': entity.cwuri,
        }
        if isinstance(es_doc, text_type):
            # sqlite return unicode instead of dict
            es_doc = json.loads(es_doc)
        es_doc.update(data)
        return es_doc


class RecordITreeAdapter(ITreeAdapter):
    __regid__ = 'ITree'
    __select__ = ITreeAdapter.__select__ & is_instance('FAComponent')
    tree_relation = 'parent_component'


class IndexableMixin(object):

    def index_by_types(self):
        by_types = defaultdict(list)
        for index in self.index_entries:
            by_types[index.type].append(index)
        return by_types

    @cachedproperty
    def indices(self):
        return {
            'agents': self.agent_indexes().entities(),
            'subjects': self.subject_indexes().entities(),
            'locations': self.geo_indexes().entities(),
        }

    def main_indexes(self, itype):
        return self._cw.execute(
            'DISTINCT Any X, XP WHERE E eid %(e)s, '
            'X is AgentName, X index E, '
            'X label XP, X type %(t)s',
            {'t': itype, 'e': self.eid})

    def agent_indexes(self):
        return self._cw.execute(
            'DISTINCT Any X, XP, XT WHERE E eid %(e)s, '
            'X is AgentName, X index E, '
            'X label XP, X type XT',
            {'e': self.eid}
        )

    def subject_indexes(self):
        return self._cw.execute(
            'DISTINCT Any X, XP WHERE E eid %(e)s, '
            'X is Subject, X index E, '
            'X label XP',
            {'e': self.eid}
        )

    def geo_indexes(self):
        return self._cw.execute(
            'DISTINCT Any X, XP WHERE E eid %(e)s, '
            'X is Geogname, X index E, '
            'X label XP',
            {'e': self.eid}
        )


class FindingAidBaseMixin(object):

    def get_extptr_for_bounce_url(self, eadid, did):
        if did.extptr:
            # special handling for ANOM arks, we have to rebuild the full URL
            if did.extptr.startswith('ark:/'):
                if eadid.startswith('FRANOM'):
                    return 'http://anom.archivesnationales.culture.gouv.fr/' + did.extptr
            else:
                return did.extptr

    @cachedproperty
    def bounce_url(self):
        eadid = self.finding_aid[0].eadid
        did = self.did[0]
        extptr = self.get_extptr_for_bounce_url(eadid, did)
        if extptr:
            return extptr
        if self.cw_etype == 'FindingAid' and self.website_url:
            return self.website_url
        if self.cw_etype == 'FAComponent':
            return self.finding_aid[0].bounce_url
        if self.related_service:
            attrs = {'unittitle': did.unittitle,
                     'unitid': did.unitid, 'eadid': eadid}
            return self.related_service.bounce_url(attrs)

    @cachedproperty
    def digitized_urls(self):
        urls = []
        for dv in self.digitized_versions:
            if dv.url:
                has_scheme = urlparse(dv.url).scheme
                if has_scheme:
                    urls.append(dv.url)
                else:
                    fa = self.finding_aid[0]
                    if fa.eadid.startswith('FRAD015'):
                        path = dv.url.replace('\\', '/')
                        urls.append(u'http://archives.cantal.fr/'
                                    u'accounts/mnesys_ad15/datas/medias'
                                    u'/{}'.format(path))
        return urls


@systemsource_entity
class Did(AnyEntity):
    __regid__ = 'Did'
    fetch_attrs, cw_fetch_order = fetch_config(['unitid', 'unittitle', 'startyear', 'stopyear'])

    def dc_title(self):
        return self.unittitle or self.unitid or u'???'

    @property
    def period(self):
        period = []
        if self.startyear:
            period.append(text_type(self.startyear))
        if self.stopyear:
            period.append(text_type(self.stopyear))
        return ' - '.join(period)


@systemsource_entity
class FAComponent(IndexableMixin, FindingAidBaseMixin, AnyEntity):
    __regid__ = 'FAComponent'
    fetch_attrs, cw_fetch_order = fetch_config(['component_order', 'stable_id', 'description',
                                                'description_format', 'did'],
                                               pclass=None)
    rest_attr = 'stable_id'

    def dc_title(self):
        return self.did[0].dc_title()

    @property
    def thumbnail_dest(self):
        """Thumbnail target URL."""
        # TODO refactor duplicated code
        target = self.bounce_url
        if self.related_service and self.related_service.thumbnail_dest:
            illustration_url = None
            if self.digitized_versions:
                for digitized_version in self.digitized_versions:
                    if digitized_version.role in {'image', 'thumbnail'}:
                        illustration_url = digitized_version.illustration_url
                        break
            if illustration_url:
                target = self.related_service.thumbnail_dest.format(url=illustration_url)
        return target

    @property
    def illustration_url(self):
        dvs = self.digitized_versions
        if not dvs:
            return None
        url = role = None
        # take first url with role 'thumbnail' or 'image'. Otherwise, take
        # any non null illustration url
        for dv in dvs:
            if dv.illustration_url:
                url = dv.illustration_url
                role = dv.role
                if role in {'thumbnail', 'image'}:
                    break
        service_code = self.related_service.code if self.related_service else None
        if not url and service_code == 'FRBNF':
            # special case for BnF
            urls = [d.url for d in dvs if d.url]
            url = urls[0] if urls else None
        if not url:
            return None
        service_code = self.related_service.code if self.related_service else None
        # not service and not url is a relative URL (root or path unknown)
        if not urlparse(url).netloc and not self.related_service:
            return None
        if url.startswith('/'):
            url = url[1:]
        if service_code == 'FRAD001':
            return (
                u'http://hatch3.vtech.fr/cgi-bin/iipsrv.fcgi?'
                u'FIF=/home/httpd/ad01/data/files/images'
                u'/{eadid}/{url}&HEI=375&QLT=80&CVT=JPG&SIZE=1045163'.format(
                    eadid=self.finding_aid[0].eadid.upper(), url=url
                )
            )
        elif service_code == 'FRAD015':
            basepath, ext = osp.splitext(url)
            return (
                u'http://archives.cantal.fr/accounts/mnesys_ad15/'
                u'datas/medias/{}_{}_/0_0{}'.format(
                    basepath.replace('\\', '/'), ext[1:], ext
                )
            )
        elif service_code == 'QUAIBR75':
            basepath, ext = osp.splitext(url)
            return (
                u'http://archives.quaibranly.fr:8990/accounts/'
                u'mnesys_quaibranly/datas/{}_{}_/0_0{}'.format(
                    basepath.replace('\\', '/'), ext[1:], ext
                )
            )
        else:
            if service_code == 'FRAD085' and not url.isdigit():
                url = url.replace('\\', '/')
            if self.related_service and self.related_service.thumbnail_url:
                url = self.related_service.thumbnail_url.format(url=url)
        # relative URL (root or path unknown)
        if not url.startswith(u'http'):
            return None
        return url

    @cachedproperty
    def publisher(self):
        rset = self._cw.execute('Any P WHERE X finding_aid FA, FA publisher P, '
                                'X eid %(x)s', {'x': self.eid})
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


class FAHeader(AnyEntity):
    __regid__ = 'FAHeader'

    def dc_title(self):
        if self.titlestmt:
            return self.titlestmt
        return u'FAHeader #{}'.format(self.eid)


@systemsource_entity
class FindingAid(IndexableMixin, FindingAidBaseMixin, AnyEntity):
    __regid__ = 'FindingAid'
    fetch_attrs, cw_fetch_order = fetch_config(['stable_id', 'did'])

    rest_attr = 'stable_id'

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
            return self.eadid.split('_')[0]

    @cachedproperty
    def related_service(self):
        if hasattr(self, 'service') and self.service:
            return self.service[0]

    @cachedproperty
    def publisher_title(self):
        service = self.related_service
        if service:
            return self.related_service.dc_title()
        return self.publisher


class DigitizedVersion(AnyEntity):
    __regid__ = 'DigitizedVersion'
    fetch_attrs, cw_fetch_order = fetch_config(['url', 'illustration_url', 'role'])
