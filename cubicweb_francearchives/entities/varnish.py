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

from collections import defaultdict

from cubicweb.predicates import is_instance

from cubicweb_varnish.entities import IVarnishAdapter

from cubicweb_francearchives import SUPPORTED_LANGS
from cubicweb_francearchives.schema import cms as schema_cms
from cubicweb_francearchives.pviews.catch_all import ApplicationSchema
from cubicweb_francearchives.entities.cms import get_ancestors


reverse_application_schema_translations = defaultdict(list)
for url, etype in ApplicationSchema.translations.items():
    reverse_application_schema_translations[etype].append('/' + url)


def extend_with_lang_prefixes(purgefunc):

    def wrapped_method(self):
        urls = purgefunc(self)
        extended_urls = []
        base_url = self._cw.base_url()
        for url in urls:
            # during db-init base_url seems to be None
            if base_url and url.startswith(base_url):
                path = url[len(base_url):]
            else:
                path = url
            if not path:
                continue  # safety belt only, we should not have an empty path
            if path[0] != '/':
                path = u'/' + path
            # XXX
            for prefix in SUPPORTED_LANGS:
                if path.startswith(prefix):
                    path = path[len(prefix):]
                    break
            extended_urls.append(path)
            for prefix in SUPPORTED_LANGS:
                extended_urls.append(u'/{}{}'.format(prefix, path))
        return extended_urls
    return wrapped_method


class FAVarnishMixin(object):

    def etype_urls(self):
        return reverse_application_schema_translations.get(self.entity.cw_etype, [])

    def sitemap(self):
        return ['/sitemap']


class BasicVarnish(FAVarnishMixin, IVarnishAdapter):
    __select__ = IVarnishAdapter.__select__ & is_instance('Service')

    @extend_with_lang_prefixes
    def urls_to_purge(self):
        return [self.entity.rest_path()] + self.etype_urls()


class CircularVarnish(FAVarnishMixin, IVarnishAdapter):
    __select__ = IVarnishAdapter.__select__ & is_instance('Circular')

    @extend_with_lang_prefixes
    def urls_to_purge(self):
        return [self.entity.rest_path()] + self.etype_urls() + self.sitemap()


class CmsObjectsVarnish(FAVarnishMixin, IVarnishAdapter):
    __select__ = IVarnishAdapter.__select__ & is_instance(
        *(set(schema_cms.CMS_OBJECTS) - {
            'CommemorationItem', 'Section', 'Service', 'Circular', 'NewsContent',
        }))

    def ancestors_urls(self):
        return ['/section/%s' % eid for eid in get_ancestors(self.entity)]

    @extend_with_lang_prefixes
    def urls_to_purge(self):
        rest_path = self.entity.rest_path()
        return [rest_path] + self.etype_urls() + self.ancestors_urls() + self.sitemap()


class SectionVarnish(CmsObjectsVarnish):
    __select__ = IVarnishAdapter.__select__ & is_instance('Section')

    @extend_with_lang_prefixes
    def urls_to_purge(self):
        urls = [self.entity.rest_path()]
        if self.entity.name in {'decouvrir', 'comprendre', 'gerer'}:
            urls.append('/' + self.entity.name)
        return urls + self.ancestors_urls() + self.sitemap()


def handle_on_homepage(entity, urls):
    if entity.on_homepage:
        urls.append('/')
    elif hasattr(entity, 'cw_edited') and not entity.cw_edited.saved:
        old, new = entity.cw_edited.oldnewvalue('on_homepage')
        if old:
            # if this entity was on homepage we should purge homepage
            urls.append('/')
    elif hasattr(entity, 'cw_edited') and entity.cw_edited.get('on_homepage') is False:
        urls.append('/')


class NewsVarnish(CmsObjectsVarnish):
    __select__ = IVarnishAdapter.__select__ & is_instance('NewsContent')

    @extend_with_lang_prefixes
    def urls_to_purge(self):
        urls = [self.entity.rest_path()]
        handle_on_homepage(self.entity, urls)
        return urls + self.etype_urls() + self.ancestors_urls() + self.sitemap()


class CommemoVarnish(CmsObjectsVarnish):
    __select__ = IVarnishAdapter.__select__ & is_instance('CommemorationItem')

    @extend_with_lang_prefixes
    def urls_to_purge(self):
        urls = [self.entity.rest_path()] + self.sitemap()
        handle_on_homepage(self.entity, urls)
        if self.entity.collection_top:
            collection = self.entity.collection_top[0].rest_path()
            index = '%s/index' % collection
            timeline = '%s/timeline' % collection
            timeline_json = '%s.json' % timeline
            return (urls + [collection, index, timeline, timeline_json]
                    + self.etype_urls() + self.ancestors_urls())
        return urls


class FindingAidVarnish(FAVarnishMixin, IVarnishAdapter):
    __select__ = IVarnishAdapter.__select__ & is_instance('FindingAid')

    def service_urls(self):
        return self._service_urls(self.entity)

    def _service_urls(self, entity):
        urls = []
        if entity.service:
            urls.append(entity.service[0].documents_url())
        return urls

    def index_urls(self):
        urls = []
        authorities_rset = self._cw.execute(
            'DISTINCT Any A WHERE I index X, X eid %(x)s, I authority A',
            {'x': self.entity.eid}
        )
        for authority in authorities_rset.entities():
            urls.append(authority.absolute_url())
        return urls

    @extend_with_lang_prefixes
    def urls_to_purge(self):
        return (
            ['search/', self.entity.rest_path(), 'inventaires/'] + self.service_urls()
            + self.index_urls()
        )


class FAComponentVarnish(FindingAidVarnish):
    __select__ = IVarnishAdapter.__select__ & is_instance('FAComponent')

    def service_urls(self):
        if self.entity.finding_aid:
            return self._service_urls(self.entity.finding_aid[0])
        return []


class CardVarnishAdapter(IVarnishAdapter):
    __select__ = is_instance('Card')

    @extend_with_lang_prefixes
    def urls_to_purge(self):
        entity = self.entity
        urls = [entity.rest_path()]
        if entity.wikiid and entity.wikiid.startswith('alert'):
            urls.append('/')
        return urls


class CssImageVarnishAdapter(IVarnishAdapter):
    __select__ = is_instance('CssImage')

    @extend_with_lang_prefixes
    def urls_to_purge(self):
        return [self.entity.rest_path(), '/']


class FileImageVarnishAdapter(IVarnishAdapter):
    __select__ = is_instance('File')

    @extend_with_lang_prefixes
    def urls_to_purge(self):
        return [self.entity.rest_path(), '/']


class AuthorityImageVarnishAdapter(IVarnishAdapter):
    __select__ = is_instance('LocationAuthority',
                             'SubjectAuthority',
                             'AgentAuthority')

    @extend_with_lang_prefixes
    def urls_to_purge(self):
        return [self.entity.rest_path()]
