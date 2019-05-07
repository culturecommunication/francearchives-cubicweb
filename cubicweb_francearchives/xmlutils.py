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

""" xml utility functions"""
from lxml import html as lxml_html
from utils import is_external_link

import logging

import re


def to_unicode(el):
    return lxml_html.tostring(el, encoding="unicode")


def log(msg, eid=None):
    try:
        if eid:
            msg = u'Entity {}: {}'.format(eid, msg)
        logging.getLogger('xmltulils').warn(msg)
    except Exception:
        pass


def process_html_as_xml(func):
    def wrapper(html, *args, **kwargs):
        if not html:
            return None
        # security belt
        eid = kwargs.get('eid')
        if not html.startswith('<'):
            return html
        if html.startswith('<body'):
            return html
        try:
            fragments = lxml_html.fragments_fromstring(html)
        except Exception as err:
            log(u'Invalid html: {}'.format(err), eid)
            return html
        if fragments:
            func(fragments[0], *args, **kwargs)
        html = u''.join(to_unicode(fragment) for fragment in fragments)
        return html
    return wrapper


FRFILE = re.compile(r'../file/(\w+)/(.*)')


def is_francearchive_relatif_link(href):
    match = FRFILE.match(href)
    if match:
        return True
    return False


def add_title_on_external_links(cnx, node, href=None):
    if is_external_link(href, cnx.base_url()):
        node.set('rel', 'nofollow noopener noreferrer')
        node.set('target', '_blank')
        title = node.attrib.get('title')
        if not title:
            title = node.text_content()
        title = u'{} {}'.format(title, cnx._('- New window'))
        node.set('title', title)


def fix_fa_external_links(root, cnx):
    """this method is used in views"""
    nodes = root.xpath('//*[@href]')
    tobe_removed = []
    for node in nodes:
        href = node.attrib['href']
        if href.startswith('//'):
            node.set('href', 'http:{}'.format(href))
            href = node.attrib['href']
        if is_external_link(href, cnx.base_url()):
            # add _blank target
            add_title_on_external_links(cnx, node, href)
        elif is_francearchive_relatif_link(href):
            rel = node.attrib.get('rel')
            if rel == 'nofollow noopener noreferrer':
                del node.attrib['rel']
            if 'target' in node.attrib:
                del node.attrib['target']
        else:
            # remove links with relative path
            # (cf. https://extranet.logilab.fr/ticket/54134093)
            tobe_removed.append(node)
    for node in tobe_removed:
        try:
            node.getparent().remove(node)
        except Exception:
            pass


def fix_links(root, cnx, *args, **kwargs):
    """take html as first argument `root`. This argument is then transformed
    in etree root by process_html_as_xml

    """
    base_url = cnx.base_url()
    for node in root.xpath('//a'):
        attribs = node.attrib
        # remove empty title
        title = attribs.get('title', None)
        if title is not None and not title.strip():
            attribs.pop('title')
        # remove title identical to the link's label
        content = node.text_content()
        if title is not None and title == content:
            attribs.pop('title')
        href = attribs.get('href')
        if href is None:
            if attribs.get('name') is None:
                log(
                    (u'Invalid link tag with missing href: '
                     u'content "{}", attrs"{}"').format(
                         repr(node.text_content()),
                         repr(attribs)), kwargs.get('eid'))
        else:
            if is_external_link(href, base_url):
                node.set('rel', 'nofollow noopener noreferrer')
                node.set('target', '_blank')
            else:
                for attr in ('target', 'rel'):
                    if attribs.get(attr):
                        attribs.pop(attr)
        # change the image alt
        images = node.xpath(".//child::img")
        for image in images:
            image.set('alt', content)
        if images:
            if 'class' in attribs:
                css_class = '{} image-link'.format(attribs['class'])
            else:
                css_class = 'image-link'
            node.set('class', css_class)


def fix_images(root, *args, **kwargs):
    """take html as first argument `root`. This argument is then transformed
    in etree root by process_html_as_xml

    """
    for node in root.xpath('//img'):
        attribs = node.attrib
        # add an empty alt rgaa 3.1
        alt = ''
        if 'alt' not in attribs:
            attribs['alt'] = alt
            # rgaa 3.2
            if 'title' in attribs:
                attribs.pop('title')
        else:
            # 3.3 alt must be relevent
            filename = attribs['src'].rsplit('/', 1)[-1]
            alt = attribs['alt'].strip()
            if alt == filename.strip():
                attribs['alt'] = ''
        # 3.3 alt and title must be identical is title exists
        if 'title' in attribs:
            title = attribs['title'].strip()
            if not title:
                attribs.pop('title')
            elif title != alt:
                attribs['title'] = alt


@process_html_as_xml
def enhance_accessibility(html, cnx, *args, **kwargs):
    fix_links(html, cnx, *args, **kwargs)
    fix_images(html, *args, **kwargs)
