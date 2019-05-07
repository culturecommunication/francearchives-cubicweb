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

"""cubicweb-pnia-content section management"""

from cubicweb.entities import fetch_config

from cubicweb_francearchives.entities.cms import CmsObject


def get_children(cnx, section_eid):
    children = []
    rset = cnx.execute(
        'Any X, T ORDERBY O WHERE S is IN (Section, CommemoCollection), '
        'X order O, '
        'S eid %(eid)s, S children X, X title T',
        {'eid': section_eid})
    for child in rset.entities():
        infos = dict(
            title=child.title,
            etype=child.cw_etype,
            url=child.absolute_url(),
            children=None
        )
        if child.cw_etype == 'Section':
            infos['children'] = get_children(cnx, child.eid)
        children.append(infos)
    return children


class Section(CmsObject):
    __regid__ = 'Section'
    rest_attr = 'eid'
    fetch_attrs, cw_fetch_order = fetch_config(
        ['order', 'title', 'subtitle', 'content', 'short_description'],
        order='DESC')

    def dc_title(self):
        titles = [self.title, self.subtitle]
        return u' - '.join(t for t in titles if t)

    def breadcrumbs_title(self):
        return self.title

    def is_commemo_section(self):
        return (self.reverse_children
                and self.reverse_children[0].cw_etype == 'CommemoCollection')

    @property
    def commemo_section(self):
        if self.is_commemo_section():
            return self.reverse_children[0]
        return None

    @property
    def image(self):
        images = self.reverse_cssimage_of or self.section_image
        return images[0] if images else None
