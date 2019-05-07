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

from cubicweb.predicates import is_instance

from cubicweb.view import EntityView
from cubicweb.utils import json_dumps, make_uid

from cubicweb_francearchives.views.primary import ContentPrimaryView
from cubicweb_francearchives.views import get_template
from cubicweb_francearchives.utils import cut_words, remove_html_tags


class CommemoVTimelineView(ContentPrimaryView):
    __regid__ = 'pnia.vtimeline'
    __select__ = (EntityView.__select__
                  & is_instance('CommemoCollection'))
    needs_js = ('veritejs/js/timeline-min.js',)
    needs_css = ('veritejs/css/timeline.css',
                 'veritejs/css/fonts/font.default.css',
                 'cubes.pnia.vtimeline.css')
    template = get_template('vtimeline.jinja2')

    def entity_call(self, entity, **kw):
        self._cw.add_js(self.needs_js)
        self._cw.add_css(self.needs_css)
        self.render_content(entity)

    def render_content(self, entity):
        self.call_template(**self.template_attrs(entity))

    def template_attrs(self, entity):
        entity = self.cw_rset.get_entity(0, 0)
        title = self._cw._('commemo-section-title %s') % entity.year
        title = self._cw._('Timeline for %s') % title
        json_url = self._cw.build_url('commemo/recueil-%s/timeline.json'
                                      % entity.year)
        divid = make_uid('t')
        js_cmd = "var timeline = new TL.Timeline('%s', %s, %s);" % (
            divid, json_dumps(json_url),
            json_dumps({'language': self._cw.lang}))
        self._cw.add_onload(js_cmd)
        ctx = {'title': title,
               'divid': divid}
        return ctx


class CommemorationTimelineJsonDataView(EntityView):
    __regid__ = 'pnia.vtimeline.json'
    __select__ = is_instance('CommemoCollection')
    template = False
    content_type = 'application/json'
    binary = True

    def title_for_link(self, label):
        return u'{} - {}'.format(
            self._cw._('Link the the commemoration full version'),
            label)

    def vtimeline_rset(self, entity):
        query = ('DISTINCT Any X, S, T, DD, DT, '
                 'F, FN, CP, CA ORDERBY D '
                 'WHERE X collection_top CC, X is CommemorationItem,'
                 'X content S, X title T, '  # use an other data as content or cut it
                 'X commemo_dates D, '
                 'D date DD, D type DT, '
                 'X commemoration_image I?, '
                 'I copyright CP, I caption CA, '
                 'I image_file F, F data_name FN, '
                 'CC eid %(eid)s')
        return self._cw.execute(query, {'eid': entity.eid})

    def entity_call(self, entity):
        rset = self.vtimeline_rset(entity)
        events = []
        d = {'title': '',
             'events': events
             }
        processed = set()
        for (eid, text, title, event_date, event_type, file_eid,
             data_name, copyright, caption) in rset:
            if eid in processed:
                continue
            if event_date is None:
                continue
            processed.add(eid)
            depiction_url = ''
            if file_eid and data_name:
                # compute the depiction_url without database call
                cw_file = self._cw.vreg['etypes'].etype_class('File')(self._cw)
                cw_file.cw_attr_cache['data_name'] = data_name
                cw_file.eid = file_eid
                depiction_url = cw_file.cw_adapt_to('IDownloadable').download_url()
            text = cut_words(remove_html_tags(text), 250, end=u'&nbsp;(...)')
            if event_type and title != event_type:
                text = '<div>%s</div>%s' % (title, text or '')
            label = self._cw._('See more')
            link = (u'<div><a href="%(href)s" target="_blank" title="%(title)s" '
                    u'rel="nofollow noopener noreferrer">%(label)s</div>') % {
                        'href': self._cw.entity_from_eid(eid).absolute_url(),
                        'title': self.title_for_link(label),
                        'label': label}
            text = '%s %s' % (text, link)
            event = {'text': {'headline': event_type or title,
                              'text': text},
                     'media': {'url': depiction_url,
                               'credit': copyright,
                               'caption': caption,
                               'thumbnail': depiction_url,
                               }}
            if depiction_url:
                event['background'] = {'url': depiction_url}
            if event_date:
                event['start_date'] = {'year': event_date.year,
                                       'month': event_date.month,
                                       'day': event_date.day}
            events.append(event)
        self.w(json_dumps(d))
