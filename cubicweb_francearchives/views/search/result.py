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

from six import text_type

from logilab.mtconverter import xml_escape

from cwtags import tag as T

from cubicweb import _
from cubicweb.view import EntityView
from cubicweb.predicates import is_instance
from cubicweb.schema import display_name

from cubicweb_francearchives.views import (get_template,
                                           format_date,
                                           blank_link_title)
from cubicweb_francearchives.entities import ETYPE_CATEGORIES
from cubicweb_francearchives.utils import title_for_link, remove_html_tags
from cubicweb_francearchives.views import html_link


class PniaTextSearchResultView(EntityView):
    __regid__ = 'pniasearch-item'
    template = get_template('searchitem.jinja2')

    def img_src(self, entity):
        image_url = getattr(entity, 'illustration_url', None)
        if image_url:
            return image_url

    def default_picto_src(self, entity):
        return None

    def get_default_picto_srcs(self, entity, illustration, doc_image):
        default_srcs = self.default_picto_src(entity)
        if illustration == default_srcs:
            default_srcs = doc_image
        else:
            if default_srcs:
                default_srcs = ';'.join((default_srcs,
                                         doc_image))
            else:
                default_srcs = doc_image
        return default_srcs

    def template_context(self, entity, es_response, max_highlights=3):
        highlights = []
        if 'highlight' in es_response.meta:
            for key, values in es_response.meta.highlight.to_dict().items():
                highlights.extend(values)
                if len(highlights) > max_highlights:
                    break
            highlights = highlights[:max_highlights]
        properties = []
        for label, value in self.properties(entity):
            if label is None:
                properties.append((label, value))
            else:
                properties.append(
                    (display_name(self._cw, label, context=entity.cw_etype), value)
                )
        doc_image = self._cw.uiprops['DOCUMENT_IMG']
        illustration = self.img_src(entity)
        default_srcs = ''
        if not illustration:
            illustration = doc_image
        else:
            default_srcs = self.get_default_picto_srcs(
                entity, illustration, doc_image)
        return {
            '_': self._cw._,
            'document_category': ETYPE_CATEGORIES.get(entity.cw_etype, 'default'),
            'entity': {'url': xml_escape(entity.absolute_url()),
                       'link_title': title_for_link(self._cw, entity.dc_title()),
                       'alink': entity.view('incontext'),
                       },
            'illustration': illustration,
            'illustration_alt': remove_html_tags(entity.dc_title()),
            'response': es_response,
            'highlights': highlights,
            'item_properties': properties,
            'default_picto_src': default_srcs
        }

    def cell_call(self, row, col, es_response=None):
        entity = self.cw_rset.get_entity(row, col)
        self.w(self.template.render(self.template_context(entity, es_response)))

    def properties(self, entity):
        meta = entity.cw_adapt_to('IMeta')
        if meta:
            yield (_('Author'), meta.author())


class CircularSearchResultView(PniaTextSearchResultView):
    __select__ = (PniaTextSearchResultView.__select__
                  & is_instance('Circular'))
    template = get_template('circular-searchitem.jinja2')

    def template_context(self, entity, es_response):
        ctx = super(CircularSearchResultView, self).template_context(entity, es_response)
        ctx['circular_css_class'] = entity.status
        ctx['circular_status'] = self._cw._(entity.status)
        return ctx

    def properties(self, entity):
        return [
            (_('code'), entity.nor or entity.siaf_daf_code or entity.code),
            (_('siaf_daf_kind'), entity.siaf_daf_kind),
            # TODO - removed because duplicate with visual indication
            (_('status'), self._cw._(entity.status)),
            (_('signing_date'), (None if entity.signing_date is None
                                 else format_date(entity.signing_date, self._cw))),
            (_('siaf_daf_signing_date'), (None if entity.siaf_daf_signing_date is None
                                          else format_date(entity.siaf_daf_signing_date,
                                                           self._cw))),
            (_('link'), ('<a href="{link}">{link}</a>'.format(link=entity.link)
                         if entity.link else None)),
        ]


class ServiceSearchResultView(PniaTextSearchResultView):
    __select__ = (PniaTextSearchResultView.__select__
                  & is_instance('Service'))

    def properties(self, entity):
        website_link, email_link = None, None
        website_url = entity.printable_value('website_url')
        if website_url:
            website_link = text_type(T.a(website_url,
                                         href=website_url,
                                         target="_blank",
                                         title=blank_link_title(self._cw, website_url),
                                         rel="nofollow noopener noreferrer"))
        email = entity.printable_value('email')
        if email:
            email_link = text_type(T.a(email, href="mailto:%s" % email))
        website_url = entity.website_url
        return [
            (_('name'), entity.name or entity.name2),
            (_('phone_number'), entity.phone_number),
            (_('address'), entity.physical_address()),
            (_('write to us'), entity.mailing_address),
            (_('email'), email_link),
            (_('website_url'), website_link),
        ]


class PersonSearchResultView(PniaTextSearchResultView):
    __select__ = (PniaTextSearchResultView.__select__
                  & is_instance('Person'))

    def img_src(self, entity):
        if entity.service and entity.service[0].illustration_url:
            return entity.service[0].illustration_url
        return super(PersonSearchResultView, self).img_src(entity)

    def properties(self, entity):
        props = [
            (_('name'), entity.name),
            (_('forenames'), entity.forenames),
            (_('death_year'), entity.death_year),
            (_('dates'), entity.dates_description),
            (_('locations'), entity.locations_description),
        ]
        if entity.document_uri:
            self._cw.add_css('css/font-awesome.css')
            url = entity.document_uri
            link = (u'<a href="{url}" rel="nofollow noopener noreferrer" '
                    u'target="_blank" title="{title}">'
                    u'{label} '
                    u'<i class="fa fa-external-link-square" aria-hidden="true"> </i>'
                    u'</a>'.format(url=xml_escape(url),
                                   label=self._cw._('oai-origin-website'),
                                   title=blank_link_title(self._cw, url)))
            props.insert(0, (None, link))
        return props


class FAComponentSearchResultView(PniaTextSearchResultView):
    __select__ = (PniaTextSearchResultView.__select__
                  & is_instance('FindingAid', 'FAComponent'))
    template = get_template('ir-searchitem.jinja2')

    def img_src(self, entity):
        url = getattr(entity, 'illustration_url', None)
        if url:
            return url
        if entity.related_service and entity.related_service.illustration_url:
            return entity.related_service.illustration_url
        return super(FAComponentSearchResultView, self).img_src(entity)

    def default_picto_src(self, entity):
        url = entity.related_service and entity.related_service.illustration_url
        if url:
            return url
        return super(FAComponentSearchResultView, self).default_picto_src(entity)

    def properties(self, entity):
        _ = self._cw._
        props = [
            (_('Cote'), entity.did[0].unitid),
            (_('Period'), entity.did[0].period),
            (_('Fonds'), entity.finding_aid[0].view('incontext')),
        ]
        itypes = defaultdict(list)
        for agent in entity.agent_indexes().entities():
            itypes[agent.type or u'name'].append(agent)
        for geo in entity.geo_indexes().entities():
            itypes['geogname'].append(geo)
        for idx_type in ('name', 'persname', 'corpname', 'famname', 'geogname'):
            if idx_type in itypes:
                index_list = sorted(itypes[idx_type], key=lambda idx: idx.label)
                props.append((_(idx_type), u' | '.join(idx.view('incontext')
                                                       for idx in index_list)))
        return props


class CommemorationItemSearchResultView(PniaTextSearchResultView):
    __select__ = (PniaTextSearchResultView.__select__
                  & is_instance('CommemorationItem'))

    def properties(self, entity):
        section_rset = self._cw.find('Section', title=text_type(entity.commemoration_year))
        if section_rset:
            value = section_rset.one().view('incontext')
        else:
            value = entity.commemoration_year
        yield (None, entity.subtitle)
        yield (_('commemoration_year'), value)


class NewsSearchResultView(PniaTextSearchResultView):
    __select__ = (PniaTextSearchResultView.__select__
                  & is_instance('NewsContent'))

    def properties(self, entity):
        yield (None, entity.header)


class ExternRefSearchResultView(PniaTextSearchResultView):
    __select__ = (PniaTextSearchResultView.__select__
                  & is_instance('ExternRef'))

    def img_src(self, entity):
        url = entity.illustration_url
        if url:
            return url
        if entity.exref_service and entity.exref_service[0].illustration_url:
            return entity.exref_service[0].illustration_url
        return super(ExternRefSearchResultView, self).img_src(entity)

    def properties(self, entity):
        _ = self._cw._
        data = [(_('period'), entity.years)]
        if entity.url:
            url = entity.url
            label = _('consult the virtual exhibits')
            link = text_type(html_link(self._cw, url, label=label))
            data.append((None, link))
        return data


class BaseContentResultView(PniaTextSearchResultView):
    __select__ = (PniaTextSearchResultView.__select__
                  & is_instance('BaseContent'))

    def properties(self, entity):
        _ = self._cw._
        desc = entity.printable_value('description')
        if not desc and entity.metadata:
            desc = entity.metadata[0].description
        services = entity.basecontent_service
        publisher_label = _('publisher') if len(services) < 2 else _('publishers')
        return [
            (_('Creation date'), entity.fmt_creation_date),
            (_('description'), desc),
            (publisher_label, u' ; '.join([s.dc_title() for s in services])),
        ]
