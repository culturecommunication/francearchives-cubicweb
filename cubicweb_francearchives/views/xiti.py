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
from six import text_type

from cubicweb.predicates import is_instance
from cubicweb.view import EntityAdapter

from cubicweb_francearchives.utils import merge_dicts
from cubicweb_francearchives.dataimport import TRANSMAP

XITI_FORBIDDEN_PUNCT = '!"#$%&\'()*+,;<=>?@[\\]^`{|}'

XITI_TRANSMAP = merge_dicts(
    {},
    TRANSMAP, dict.fromkeys(ord(c) for c in XITI_FORBIDDEN_PUNCT), {
        ord(' '): ord('_'),
    }
)


def normalize_xiti_chapter(chapter):
    """chapter names have to be normalized for Xiti

    cf. http://help.atinternet-solutions.com/fr/implementation/general/abouttagging_fr.htm
    """
    if isinstance(chapter, str):
        # safety belt if the "u" prefix was forgotten, we're supposed
        # to have ascii here
        chapter = text_type(chapter)
    try:
        return chapter.lower().translate(XITI_TRANSMAP)
    except Exception:
        return u'unknown-error-fallback'


def pagename_from_chapters(chapters):
    return u'::'.join(normalize_xiti_chapter(c) for c in chapters)


class XitiEntityAdapter(EntityAdapter):
    """default implementation returns 3 chapters: (etype, <main-attr>, title)
    """
    __regid__ = 'IXiti'

    append_title = True  # set to False if <main-attr> is self-explanatory

    @property
    def get_xiti_attrname(self):
        return self.entity.cw_rest_attr_info()[0]

    @property
    def chapters(self):
        entity = self.entity
        attrname = self.get_xiti_attrname
        chapters = [entity.__regid__,
                    # we might get integers
                    text_type(getattr(entity, attrname))]
        if self.append_title:
            chapters.append(entity.dc_title())
        return chapters


class FAXitiAdapater(XitiEntityAdapter):
    """generate 3 chapters (etype, service_code, stable_id)"""
    __select__ = is_instance('FindingAid', 'FAComponent')

    @property
    def chapters(self):
        entity = self.entity
        chapters = [entity.cw_etype]
        service = entity.related_service
        if service is None:
            chapters.append(u'unknown-service')
        else:
            chapters.append(
                service.code or service.zip_code or service.dc_title()
            )
        chapters.append(entity.stable_id)
        return chapters


class ServiceXitiAdapter(XitiEntityAdapter):
    __select__ = is_instance('Service')

    @property
    def chapters(self):
        chapters = [u'Service']
        entity = self.entity
        service_code = entity.code or entity.zip_code or entity.dc_title()
        chapters.append(service_code)
        return chapters


class CommemoCollectionXitiAdapter(XitiEntityAdapter):
    __select__ = is_instance('CommemoCollection')

    @property
    def chapters(self):
        return [u'CommemoCollection', text_type(self.entity.year)]


class CommemorationItemXitiAdapter(XitiEntityAdapter):
    __select__ = is_instance('CommemorationItem')

    @property
    def chapters(self):
        return [u'Commemo',
                text_type(self.entity.commemoration_year),
                self.entity.dc_title()]


class NoTitleXitiAdapter(XitiEntityAdapter):
    __select__ = is_instance('Card')
    append_title = False


class CircularXitiAdapter(XitiEntityAdapter):
    __select__ = is_instance('Circular')
    append_title = False

    @property
    def get_xiti_attrname(self):
        """ avoid self.entity.cw_rest_attr_info()[0] returning uuid instead of circ_id
        """
        return 'circ_id'


class BaseContentXitiAdapter(XitiEntityAdapter):
    __select__ = is_instance('BaseContent')

    @property
    def chapters(self):
        chapters = super(BaseContentXitiAdapter, self).chapters
        if self.entity.is_a_publication:
            chapters[0] = 'Publication'
        return chapters
