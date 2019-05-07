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

"""pnia_content views/homepage views and components"""

from datetime import datetime
from babel.dates import format_date
from six import text_type as unicode

from cwtags import tag as T

from logilab.common.decorators import cachedproperty

from logilab.mtconverter import xml_escape

from cubicweb.web.component import CtxComponent
from cubicweb.web.views.startup import IndexView

from cubicweb_francearchives.views import (JinjaViewMixin,
                                           get_template)
from cubicweb_francearchives.utils import title_for_link, remove_html_tags

_ = unicode


class HomepageAbstractComponent(CtxComponent):
    __abstract__ = True
    context = 'homepage'

    def render(self, w, view=None):
        self._render(w)

    def _render(self, w):
        raise NotImplementedError


class HomeContentSectionComponent(CtxComponent):
    __regid__ = 'section-title-comp'
    context = 'section'

    def render(self, w, grey_title, blue_title):
        _ = self._cw._
        with T.div(w, Class="content-section-header"):
            with T.h1(w):
                w(T.span(_(grey_title), Class="content-section-header-grey"))
                w(u'&nbsp;')
                w(T.span(_(blue_title), Class="content-section-header-blue"))
        with T.div(w, Class="rhombus-title"):
            w(T.span(Class="medium-grey-line mr20"))
            w(T.span(Class="rhombus"))
            w(T.span(Class="medium-grey-line ml20"))


class HomeContentEventsComponent(JinjaViewMixin, HomepageAbstractComponent):
    __regid__ = 'homepage-content-events'
    template = get_template('commemorations-home.jinja2')
    order = 6

    def call_template(self, w, **ctx):
        w(self.template.render(**ctx))

    def _render(self, w):
        req = self._cw
        rset = req.execute(
            'Any X ORDERBY O LIMIT 10 WHERE '
            'X is CommemorationItem, '
            'X commemoration_year XA, '
            'X on_homepage True, X on_homepage_order O')
        _ = req._
        commemos = [{
            'url': commemo.absolute_url(),
            'title': commemo.title,
            'plain_title': remove_html_tags(commemo.title),
            'link_title': title_for_link(req, commemo.title),
            'image': commemo.image} for commemo in rset.entities()]
        return self.call_template(w,
                                  grey_title=_('###events_grey###'),
                                  blue_title=_('###events_blue###'),
                                  commemos=commemos,
                                  default_picto_src=self._cw.uiprops['DOCUMENT_IMG'])


class HomeContentNewsComponent(HomepageAbstractComponent):
    __regid__ = 'homepage-content-news'
    order = 5

    def _render(self, w):
        _ = self._cw._
        with T.section(w, id="content-news"):
            w(T.div(Class="content-news-tbg"))
            comp = self._cw.vreg['ctxcomponents'].select_or_none('section-title-comp',
                                                                 self._cw,
                                                                 rset=self.cw_rset)
            if comp:
                comp.render(w=w, grey_title=_('###news_title__grey###'),
                            blue_title=_('###new_title_blue###'))
            now = datetime.now()
            with T.div(w, id="content-news-date", Class="row"):
                w(
                    T.h2(
                        format_date(now, "MMMM y", locale=self._cw.lang),
                        Class="date"
                    )
                )
            self.render_timeline(w)
            w(T.div(Class="content-news-bbg"))

    def render_timeline(self, w):
        odd, even, ordered = [], [], []
        self.w = w
        req = self._cw
        _ = self._cw._
        last_news = req.execute(
            'Any X ORDERBY SA DESC LIMIT 7 WHERE X is NewsContent, '
            'X start_date SA, X on_homepage TRUE').entities()
        default_picto_src = self._cw.uiprops['DOCUMENT_IMG']
        with T.div(w, Class="timeline"):
            last_date = None
            for i, news in enumerate(last_news):
                _even = i % 2
                current_news = []
                w = current_news.append
                slide_classes = "timeline-slide"
                if not news.start_date == last_date:
                    slide_classes = slide_classes + " first-of-day"
                last_date = news.start_date
                title = news.title
                link_title = title_for_link(self._cw, news.title)
                with T.div(w, Class=slide_classes):
                    w(T.span(Class="timeline-corner"))
                    with T.div(w, Class="timeline-news"):
                        with T.div(w, Class="clearfix"):
                            if news.news_image:
                                image = news.news_image[0]
                                img_src = (image.image_file[0]
                                           .cw_adapt_to('IDownloadable').download_url())
                                with T.a(w, href=news.absolute_url(),
                                         title=link_title):
                                    w(T.img(src=img_src,
                                            data_defaultsrc=default_picto_src,
                                            Class='timeline-news__picto responsive-img',
                                            alt=remove_html_tags(title)))
                                    w(T.span(title, Class='sr-only'))
                            with T.div(w, Class="timeline-news__datetime"):
                                day, month = format_date(
                                    news.start_date, 'dd##MMM',
                                    locale=self._cw.lang).split('##')
                                w(T.div(day, Class="timeline-news__datetime__day"))
                                w(T.div(month[:3],
                                        Class="timeline-news__datetime__month"))
                        with T.div(w, Class="timeline-news__title"):
                            with T.h3(w):
                                w(T.a(title, href=news.absolute_url(),
                                      title=link_title))
                        if news.header:
                            w(T.div(news.header, Class="timeline-news__chapo"))
                ordered.extend(current_news)
                even.extend(current_news) if _even else odd.extend(current_news)

            # XXX set border in javascript, not in CSS
            with T.div(self.w, Class="row"):
                with T.div(self.w, Class="col-12 ordered"):
                    self.w(u'\n'.join([unicode(e) for e in ordered]))
            with T.div(self.w, Class="row"):
                with T.div(self.w, Class="col-md-6 col-xs-6 odd"):
                    self.w(u'\n'.join([unicode(e) for e in odd]))
                with T.div(self.w, Class="col-md-6 col-xs-6 even"):
                    self.w(u'\n'.join([unicode(e) for e in even]))
            with T.div(self.w, Class="row"):
                url = self._cw.build_url('actualites')
                self.w(T.a(T.span(_('See all news'), Class="sr-only"),
                       href=xml_escape(url),
                       Class="timeline__more-events"))


class PniaIndexView(IndexView):
    needs_css = ('lightslider-master/css/lightslider.min.css',)

    @cachedproperty
    def xiti_chapters(self):
        return [u'Home']

    def template_context(self):
        req = self._cw
        meta = req.vreg['adapters'].select('IMeta', req, homepage=True)
        og = req.vreg['adapters'].select('IOpenGraph', req, homepage=True)
        return {'open_graph': og.og_data(),
                'meta': meta.meta_data()}

    def call(self):
        self._cw.add_css(self.needs_css)
        comps = self._cw.vreg['ctxcomponents'].poss_visible_objects(self._cw,
                                                                    context='homepage',
                                                                    rset=self.cw_rset)
        for comp in comps:
            comp.render(w=self.w)
        self._cw.add_js('lightslider-master/js/lightslider.min.js')


def registration_callback(vreg):
    vreg.unregister(IndexView)
    vreg.register_all(globals().values(), __name__)
