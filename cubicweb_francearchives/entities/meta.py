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

from logilab.common.decorators import cachedproperty

from cubicweb.view import EntityAdapter, Adapter
from cubicweb.predicates import match_kwargs

from cubicweb_francearchives.views import twitter_account_name


class MetaMixin(object):

    @cachedproperty
    def meta(self):
        metadata = getattr(self.entity, 'metadata', ())
        if metadata:
            return metadata[0]
        return None

    def meta_data(self):
        data = [
            (u'title', self.title()),
            (u'description', self.description()),
            (u'keywords', self.keywords()),
            (u'author', self.author()),
            (u'subject', self.subject()),
            (u'twitter:card', u'summary'),
            (u'twitter:site', twitter_account_name(self._cw.vreg.config)),
        ]
        return [(name, value) for name, value in data if value]

    def title(self):
        entity = self.entity
        if self.meta and self.meta.title:
            title = self.meta.title
        else:
            title = entity.dc_title()
        return title

    def description(self):
        if self.meta:
            return self.meta.description
        return None

    def keywords(self):
        if self.meta:
            return self.meta.keywords
        return None

    def author(self):
        if self.meta:
            return self.meta.creator
        return None

    def subject(self):
        if self.meta:
            return self.meta.subject
        return None


class BaseMetaAdapter(EntityAdapter, MetaMixin):
    __regid__ = 'IMeta'


class HomePageMetadApter(Adapter, MetaMixin):
    __regid__ = 'IMeta'
    __select__ = match_kwargs({'homepage': True})

    @cachedproperty
    def meta(self):
        return self._cw.find('Metadata', uuid=u'metadata-homepage').one()

    def title(self):
        return self._cw.property_value('ui.site-title')
