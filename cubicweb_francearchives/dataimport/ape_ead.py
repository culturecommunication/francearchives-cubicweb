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
from itertools import chain
from six import text_type

from glamconv.ead.utils import NS, split_qname
from glamconv.transformer.actions import TransformAction
from glamconv.ead.formats import EAD_2002
from glamconv.transformer.parameters import SingleParameter

from glamconv.transformer.libraries import register_action

from cubicweb_francearchives.utils import is_absolute_url


class EADIDTransformer(TransformAction):
    applicable_for = (EAD_2002, )
    uid = u"francearchives-eadid-transformer"
    name = u"Transform eadid tag"
    category = u"Header"
    desc = (u"Set a new <eadid> url attribute value is no exists""")
    params_def = (
        SingleParameter(
            u"eadid_url", u"Eadid Url",
            u"Url inserted as <eadid> element url attribute value if no exists "
            u"content.", u"Text", text_type, u""),
    )

    def _execute(self, xml_root, logger, log_details, eadid_url):
        for eadid in xml_root.xpath('.//eadid'):
            if not eadid.attrib.get('url'):
                eadid.set(u'url', eadid_url)
        return xml_root


class XLinkAdjuster(TransformAction):
    applicable_for = (EAD_2002,)
    uid = u"francearchives-xlink-adjuster"
    name = u"Remove <extptr>, <dao>, <daoloc> with relative href"
    category = u"Links & Refs"
    desc = (u"Remove <extptr>, <dao>, <daoloc> with relative href")

    def _execute(self, xml_root, logger, log_details):
        to_remove = set()
        tags = ('archref', 'bibref', 'dao', 'daoloc',
                'extptr', 'extptrloc', 'extref', 'extrefloc',
                'ptrloc', 'refloc', 'title')
        elts = chain(xml_root.xpath('.//{}'.format(tag)) for tag in tags)
        for elts_list in elts:
            for elt in elts_list:
                _, name = split_qname(elt.tag)
                url = elt.get(u"{{{xlink}}}href".format(**NS), None)
                if url and not is_absolute_url(url):
                    to_remove.add(elt)
        if len(to_remove) > 0:
            for elt in to_remove:
                elt.getparent().remove(elt)
            logger.warning(
                u"Remove relative internal links. {0:d} elements "
                u"have been removed.".format(len(to_remove)))
            if log_details:
                logger.warning(u"The following elements have been removed:",
                               u"\n".join(to_remove))
        return xml_root


def register_ead_actions():
    register_action(EADIDTransformer, EAD_2002.uid)
    register_action(XLinkAdjuster, EAD_2002.uid)
