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


import logging
import os.path as osp
import re
from collections import defaultdict, Counter
from itertools import chain

from lxml import etree

from logilab.common.decorators import cachedproperty
from string import punctuation

from cubicweb import _


from cubicweb_francearchives.dataimport import (
    normalize_entry,
    remove_extension,
    strip_nones,
    InvalidFindingAid,
    clean,
)
from cubicweb_francearchives.utils import remove_html_tags

XSLT_PATH = osp.join(osp.dirname(__file__), "xslt", "ead.html.xsl")
XSLT = etree.XSLT(etree.parse(XSLT_PATH))

LOGGER = logging.getLogger()

INDEX_TYPES = (
    _("persname"),
    _("corpname"),
    _("famname"),
    _("name"),
    _("geogname"),
    _("subject"),
    _("function"),
    _("genreform"),
    _("occupation"),
)


def html_formatter(node):
    if node is None:
        return None
    try:
        return XSLT(node)
    except Exception:
        return None


def raw_content(node):
    if node is None:
        return None
    return etree.tostring(node, method="html", encoding="unicode")


def unnest(node):
    for subnode in node.findall(".//%s" % node.tag):
        subnode.tag = "p"
        subnode.attrib.clear()
        subnode.attrib["class"] = "ead-%s" % node.tag


def to_html(node):
    if isinstance(node, (list, tuple)):
        return "\n".join([raw_content(html_formatter(node)) or "" for node in node])
    else:
        return raw_content(html_formatter(node))


def optset(value):
    if value is None:
        return None
    return set([value])


def optset_html(node):
    return optset(raw_content(html_formatter(node)))


def delete(node):
    node.getparent().remove(node)


def replace(source, target):
    source.getparent().replace(source, target)


YEAR_RANGE_RGX = [
    re.compile(
        r"""
        ^\s*(?P<start>\d{2,4})/\d{1,2}/\d{1,2}\s*-
        \s*(?P<stop>\d{2,4})/\d{1,2}/\d{1,2}\s*$""",
        re.X,
    ),
    re.compile(
        r"""
        ^\s*(?P<start>\d{2,4})-\d{1,2}-\d{1,2}\s*/
        \s*(?P<stop>\d{2,4})-\d{1,2}-\d{1,2}\s*$""",
        re.X,
    ),
    re.compile(r"^\s*(?P<start>\d{2,4})\s*[/-]\s*(?P<stop>\d{2,4})\s*$"),
    re.compile(r"^\s*(?P<start>\d{2,4})\s*$"),
]


def parse_normalized_daterange(value):
    """try to guess {start, stop} date range from a unitdate label

    Known formats are:
        - yyyy-mm-dd / yyyy-dd-dd
        - yyyy/mm/dd - yyyy/mm/dd
        - yyyy - yyyy
        - yyyy

    If ``start`` is greater than ``stop``, ``stop`` gets lowered back
    to ``start``.

    If ``start`` or ``stop`` are greater than 2100, they are ignored.
    If ``stop`` is not defined, it defaults to ``start``.
    Returns:
        - None if nothing could be parsed
        - {'start', 'stop'} mapping on success
    """
    start = stop = None
    if value is not None:
        for rgx in YEAR_RANGE_RGX:
            match = rgx.match(value)
            if match is not None:
                start = int(match.group("start"))
                if "stop" in match.groupdict():
                    stop = int(match.group("stop"))
                if start and start > 2100:
                    start = None
                if stop and stop > 2100:
                    stop = None
                if start and stop and start > stop:
                    stop = None
                stop = start if stop is None else stop
                if start and stop:
                    return {"start": start, "stop": stop}
    return None


def parse_unitdate(unitdate):
    infos = {
        "label": None,
        "start": None,
        "stop": None,
    }
    if unitdate is not None and unitdate.text:
        infos["label"] = unitdate.text
        for datelabel in (unitdate.get("normal"), unitdate.text):
            year_range = parse_normalized_daterange(datelabel)
            if year_range is not None:
                infos.update(year_range)
                break
    return infos


def lang_infos(node, tagname):
    langusage = node.find(tagname)
    lang_code = None
    if langusage is not None:
        language = langusage.find("language")
        if language is not None:
            lang_code = language.get("langcode")
    return langusage, lang_code


def component_physdesc(did):
    node = did.find("physdesc")
    if node is not None:
        unnest(node)
        nodes = defaultdict(list)
        for tag, label in (
            ("physfacet", _("physfacet_label")),
            ("extent", _("extent_label")),
            ("dimensions", _("dimensions_label")),
        ):
            for cnode in node.findall(tag):
                auto_label = cnode.attrib.get("label")
                if auto_label:
                    label = auto_label
                nodes[label].append(elt_description(cnode))
                node.remove(cnode)
        res = []
        for label, values in nodes.items():
            res.append('<div class="ead-label">{}</div>'.format(label))
            res.extend(values)
        return '<div class="ead-section ead-{}">{}\n{}</div>'.format(
            node.tag, to_html(node), "\n".join(res).strip() if res else ""
        )
    return ""


def component_materialspec(did):
    html = to_html(did.find("materialspec"))
    if html:
        # make ead-autolabel visible as "ead-autolabel" is no more displayed
        html = html.replace('class="ead-autolabel"', 'class="ead-label"')
    return html


def did_infos(did, log=None):
    if did is None:
        raise InvalidFindingAid("no DID found in component, ignoring it")
    component = did.getparent()
    date = did.find("unitdate")
    date_infos = parse_unitdate(date)
    unitdate = date_infos.get("label")
    langusage, lang_code = lang_infos(did, "langmaterial")
    titles = did.findall("unittitle")
    title = None
    if titles:
        title = " | ".join(
            " ".join([x.strip() for x in title.xpath(".//text()")]) for title in titles
        )
    if not title:
        title = unitdate or "Sans titre"
    unitid = did.find("unitid")
    extptr_link = None
    if unitid is not None:
        extptr = did.find("unitid[@type='external_link']//extptr")
        if extptr is None:
            extptr = unitid.find("extptr")
        if extptr is not None:
            extptr_link = extptr.get("{http://www.w3.org/1999/xlink}href") or extptr.get("href")
        unitid = " ".join(unitid.xpath(".//text()")).strip()
    cid = component.get("id")
    if not extptr_link and cid and cid.startswith("ark--"):
        extptr_link = cid.replace("ark-", "ark:").replace("-", "/")
    if extptr_link is not None and len(extptr_link) > 2048:
        if log:
            log.warning("ignoring to long  extptr link value (%s) caracters", len(extptr_link))
        extptr_link = None
    infos = {
        "unittitle": title,
        "unitdate": unitdate,
        "unitid": unitid,
        "extptr": extptr_link,
        "startyear": date_infos["start"],
        "stopyear": date_infos["stop"],
        "lang_description": to_html(langusage),
        "lang_code": lang_code,
    }
    for prop in ("note", "origination", "physloc", "repository", "abstract"):
        infos[prop] = to_html(did.find(prop))
    infos["physdesc"] = component_physdesc(did)
    infos["materialspec"] = component_materialspec(did)
    return infos


def elt_description(node):
    if node is not None:
        unnest(node)
        content = raw_content(html_formatter(node))
        if content is not None:
            return '<div class="ead-section ead-{}">{}</div>'.format(node.tag, content)
    return ""


def component_description(node):
    description = []
    for tag in ("accruals", "appraisal", "arrangement"):
        description.extend([elt_description(child) for child in node.findall(tag)])
    return "\n".join(description).strip() or None


def component_bibliography(node):
    description = [
        elt_description(node.find("bibliography")),
        elt_description(node.find("bibref")),
    ]
    return "\n".join(description).strip() or None


def component_acqinfo(node):
    description = [
        elt_description(node.find("acqinfo")),
        elt_description(node.find("custodhist")),
    ]
    return "\n".join(description).strip() or None


def file_info(node, relfiles, get_sha1_func):
    """
    :node: XML node
    :relfiles: list of existing RELFILES for the given service
    :get_sha1_func:  function to compute a file sha1 from its filepath

    :returns: file_info
    :rtype: dict
    """
    href = node.attrib.get("href")
    if href:
        title = osp.basename(href)
        filepath = relfiles.get(title)
        if filepath:
            return {
                "filepath": filepath,
                "title": osp.basename(href),
                "sha1": get_sha1_func(filepath),
            }


def component_additional(node, relfiles, get_sha1_func):
    description = []
    referenced_files = []
    for tag in ("otherfindaid", "relatedmaterial", "separatedmaterial", "originalsloc"):
        for child in node.findall(tag):
            if tag != "originalsloc" and relfiles:
                # index files
                for archref in child.xpath(".//archref"):
                    finfo = file_info(archref, relfiles, get_sha1_func)
                    if finfo:
                        archref.set("href", "../file/{}/{}".format(finfo["sha1"], finfo["title"]))
                        if not archref.text:
                            archref.text = finfo["title"]
                        referenced_files.append(finfo)
            description.append(elt_description(child))
    description = "\n".join(description).strip() or None
    return description, referenced_files


def component_scopecontent(node):
    return elt_description(node.find("scopecontent"))


def component_accessrestrict(node):
    for lnode in node.findall("accessrestrict/legalstatus"):
        altrender = lnode.get("altrender")
        if altrender:
            altrender.strip().rstrip(punctuation).strip()
            lnode.text = altrender + ". " + (lnode.text or "")
    content = to_html(node.findall("accessrestrict"))
    if content:
        return f'<div class="ead-section ead-accessrestrict">{content}</div>'


def component_userestrict(node):
    content = to_html(node.findall("userestrict"))
    if content:
        return f'<div class="ead-section ead-userestrict">{content}</div>'


def component_publicationstmt(node):
    if node is not None:
        description = [
            elt_description(node.find("publisher")),
            elt_description(node.find("date")),
            elt_description(node.find("address")),
        ]
        return "\n".join(description).strip() or None
    return None


def eadheader_props(eadheader):
    if eadheader is None:
        return {}
    langusage, lang_code = lang_infos(eadheader, "langusage")
    return {
        "eadid": str(eadheader.findtext("eadid")),
        "titlestmt": to_html(eadheader.find("filedesc/titlestmt")),
        "titleproper": "".join(eadheader.xpath(".//titleproper//text()")).strip(),
        "titlestmt_format": "text/html",
        "publicationstmt": component_publicationstmt(eadheader.find(".//publicationstmt")),
        "publicationstmt_format": "text/html",
        "descrules": to_html(eadheader.find("descrules")),
        "descrules_format": "text/html",
        "author": to_html(eadheader.find("author")),
        "author_format": "text/html",
        "changes": "\n".join(
            [
                raw_content(html_formatter(node)) or ""
                for node in eadheader.findall(".//revisiondesc/change")
            ]
        ),
        "changes_format": "text/html",
        "creation": to_html(eadheader.find("creation")),
        "creation_format": "text/html",
        "lang_description": to_html(langusage),
        "lang_description_format": "text/html",
        "lang_code": lang_code,
    }


def cleanup_ns(tree, ns=None):
    """hack: remove default NS.

    Some EAD files use the 'urn:isbn:1-931666-22-9' namesapce, some don't.
    To ease XML processing, remove it to access nodes using unqualified
    names in all cases.
    """
    if hasattr(tree, "getroot"):
        root = tree.getroot()
    else:
        root = tree
    if ns in root.nsmap:
        for elt in root.getiterator():
            if not hasattr(elt.tag, "find"):
                continue
            ns_idx = elt.tag.find("}")
            if ns_idx > 0:
                elt.tag = elt.tag[ns_idx + 1 :]
    return root


def preprocess_ead(data):
    """Preprocesses the EAD xml file to remove ns and internal content

    Parameters:
    -----------

    data : the path to the EAD xml file or EAD xml file  Binary file content

    Returns:
    --------

    the lxml etree object, cleaned from internal content
    """
    if isinstance(data, bytes):
        from io import BytesIO

        data = BytesIO(data)
    tree = etree.parse(data)
    cleanup_ns(tree)
    for elt in tree.findall('//*[@audience="internal"]'):
        elt.getparent().remove(elt)
    return tree


def iter_components(node):
    tagnames = ["c"] + ["c{:02d}".format(i) for i in range(1, 13)]
    if node is not None:
        for tagname in tagnames:
            for cnode in node.findall(tagname):
                yield cnode


def index_infos(node, role="index"):
    if node.text is None:
        return
    index_label = None
    #  see https://extranet.logilab.fr/73966141
    if node.tag in ("corpname", "famname", "name", "persname", "geogname", "genreform", "subject"):
        index_label = node.attrib.get("normal")
        if index_label:
            index_label = index_label.strip()
    if not index_label:
        index_label = remove_html_tags(node.text).strip()
        index_label = next(clean(index_label))
    if not index_label:
        return None
    if index_label and len(index_label) > 256:
        LOGGER.warning("truncating index entry of length %s: %r", len(index_label), index_label)
    index_label = index_label[:256].strip()
    return {
        "authfilenumber": node.get("authfilenumber"),
        "type": node.tag,
        "label": index_label,
        "normalized": normalize_entry(index_label),
        "role": role,
    }


def unique_indices(entries, keys=("type", "normalized")):
    done = set()
    uniques = []
    for entry in entries:
        key = tuple(entry[k] for k in keys)
        if key not in done:
            done.add(key)
            uniques.append(entry)
    return uniques


class EADXMLReader(object):
    def __init__(self, tree, get_sha1_func, relfiles=None, log=None):
        self.tree = tree
        self.relfiles = relfiles
        self.get_sha1_func = get_sha1_func
        self.log = LOGGER if log is None else log

    @cachedproperty
    def archdesc(self):
        archdesc = self.tree.find("archdesc")
        if archdesc is None:
            raise InvalidFindingAid("no archdesc found")
        return archdesc

    @cachedproperty
    def fa_maindid(self):
        did = self.archdesc.find("did")
        if did is None:
            raise InvalidFindingAid("no did found in archdesc")
        return did

    def originators(self):
        did = self.fa_maindid
        originators = []
        for tag in ("name", "corpname", "famname", "persname"):
            for node in did.findall("origination/{}".format(tag)):
                if node.text:
                    originators.append(node.text.strip())
        return originators

    def fa_headerprops(self):
        return eadheader_props(self.tree.find("eadheader"))

    def is_imprinted_geoname(self, node):
        if node.tag == "geogname":
            parent = node.getparent()
            if parent.tag == "imprint":
                return True
        return False

    def archdesc_indexes(self):
        for node in chain(
            self.archdesc_indexes_nodes(INDEX_TYPES),
            self.fa_maindid.findall("physdesc/{}".format("genreform")),
        ):
            if node is not None and not self.is_imprinted_geoname(node):
                yield node

    def archdesc_indexes_nodes(self, tagnames):
        archdesc = self.archdesc
        did = self.fa_maindid
        for tagname in tagnames:
            for node in chain(
                archdesc.findall("controlaccess/{}".format(tagname)),
                did.findall("unittitle/{}".format(tagname)),
                archdesc.findall("bioghist/{}".format(tagname)),
                archdesc.findall("bioghist/p/{}".format(tagname)),
                archdesc.findall("scopecontent/{}".format(tagname)),
                archdesc.findall("scopecontent/p/{}".format(tagname)),
            ):
                yield node

    def component_indexes(self, component):
        for node in chain(
            self.component_indexes_nodes(component, INDEX_TYPES),
            component.findall("did/physdesc//{}".format("genreform")),
        ):
            if node is not None and not self.is_imprinted_geoname(node):
                yield node

    def component_indexes_nodes(self, component, tagnames):
        did = component.find("did")
        for tagname in tagnames:
            for node in chain(
                component.findall("controlaccess//{}".format(tagname)),
                did.findall("unittitle//{}".format(tagname)),
                component.findall("bioghist//{}".format(tagname)),
                component.findall("scopecontent//{}".format(tagname)),
            ):
                yield node

    def origination(self, host_node):
        origination = host_node.find("origination")
        if origination is not None:
            role = origination.get("label", "originator").strip().lower()
            for tagname in ("persname", "corpname", "geogname", "subject", "famname", "name"):
                for node in origination.findall(tagname):
                    infos = index_infos(node, role=role)
                    if infos is not None:
                        yield infos

    def index_entries(self, gen_nodes):
        for node in gen_nodes:
            infos = index_infos(node)
            if infos is not None:
                yield infos

    def did_properties(self, did, parent=None):
        attrs = did_infos(did, self.log)
        parent_did = {} if parent is None else parent["did"]
        if not attrs["unitdate"]:
            attrs["unitdate"] = parent_did.get("unitdate")
            attrs["startyear"] = parent_did.get("startyear")
            attrs["stopyear"] = parent_did.get("stopyear")
        unitid = attrs["unitid"]
        if not attrs["unittitle"]:
            attrs["unittitle"] = parent_did.get("unittitle")
        if unitid:
            unitid = remove_extension(unitid)[:256]
        attrs["unitid"] = unitid or None
        return strip_nones(attrs, defaults={"unittitle": "Sans titre"})

    def website_url(self, did_info):
        eadid = self.tree.find("eadheader/eadid")
        return eadid.attrib.get("url")

    @cachedproperty
    def fa_properties(self):
        """FindingAid properties"""
        archdesc = self.archdesc
        additional_resources, referenced_files = component_additional(
            archdesc, self.relfiles, self.get_sha1_func
        )
        did_info = self.did_properties(self.fa_maindid)
        return {
            "fatype": archdesc.get("type"),
            "description": component_description(archdesc),
            "description_format": "text/html",
            "bibliography": component_bibliography(archdesc),
            "bibliography_format": "text/html",
            "bioghist": to_html(archdesc.find("bioghist")),
            "bioghist_format": "text/html",
            "accessrestrict": component_accessrestrict(archdesc),
            "accessrestrict_format": "text/html",
            "userestrict": component_userestrict(archdesc),
            "userestrict_format": "text/html",
            "acquisition_info": component_acqinfo(archdesc),
            "acquisition_info_format": "text/html",
            "additional_resources": additional_resources,
            "additional_resources_format": "text/html",
            "scopecontent": component_scopecontent(archdesc),
            "scopecontent_format": "text/html",
            "notes": to_html(archdesc.find("odd")),
            "notes_format": "text/html",
            "index_entries": list(self.index_entries(self.archdesc_indexes())),
            "origination": list(self.origination(self.fa_maindid)),
            "did": did_info,
            "daos": self.component_daos(archdesc),
            "referenced_files": referenced_files,
            "website_url": self.website_url(did_info),
        }

    def walk(self, parent=None, context=None):
        if parent is None:  # root / archdesc
            current_node = self.archdesc.find("dsc")
            context = self.fa_properties
        else:
            current_node = parent
        for idx, comp_node in enumerate(iter_components(current_node)):
            try:
                comp_props = self.component_properties(comp_node, context, component_index=idx)
            except InvalidFindingAid as err:
                self.log.warning("ignoring invalid component at path %s: %s", idx, err)
                continue
            yield comp_node, comp_props
            for subcomp_node, subcomp_props in self.walk(comp_node, comp_props):
                yield subcomp_node, subcomp_props

    def component_properties(self, cnode, parent, component_index):
        """FAComponent properties"""
        did = cnode.find("did")
        c_id = cnode.get("id", None)
        additional_resources, referenced_files = component_additional(
            cnode, self.relfiles, self.get_sha1_func
        )
        return {
            "__parent__": parent,
            "did": self.did_properties(did, parent),
            "description": component_description(cnode),
            "description_format": "text/html",
            "bibliography": component_bibliography(cnode),
            "bibliography_format": "text/html",
            "bioghist": to_html(cnode.find("bioghist")),
            "bioghist_format": "text/html",
            "acquisition_info": component_acqinfo(cnode),
            "acquisition_info_format": "text/html",
            "additional_resources": additional_resources,
            "additional_resources_format": "text/html",
            "scopecontent": component_scopecontent(cnode),
            "scopecontent_format": "text/html",
            "accessrestrict": component_accessrestrict(cnode),
            "accessrestrict_format": "text/html",
            "userestrict": component_userestrict(cnode),
            "userestrict_format": "text/html",
            "origination": list(self.origination(did)),
            "notes": to_html(cnode.find("odd")),
            "notes_format": "text/html",
            "daos": self.component_daos(cnode),
            "path": parent.get("path", ()) + (component_index,),
            # remove exact duplicates but keep variants and let
            # postprocess_ead_index handle them
            "index_entries": unique_indices(
                chain(parent["index_entries"], self.index_entries(self.component_indexes(cnode))),
                keys=("type", "label"),
            ),
            "referenced_files": referenced_files,
            "c_id": c_id,
        }

    def daodef(self, dao):
        href = dao.get("{http://www.w3.org/1999/xlink}href") or dao.get("href")
        if not href:
            return None
        role = (
            dao.get("role")
            or dao.get("{http://www.w3.org/1999/xlink}role")
            or dao.get("{http://www.w3.org/1999/xlink}title")
        )
        illustration_url = None
        ext = osp.splitext(href)[-1].lower()
        if ext in {".jpg", ".jpeg", ".png", ".jp2"} and role not in {"image", "thumbnail"}:
            role = "thumbnail"
        if role in ("image", "thumbnail"):
            illustration_url, href = href, None
            # XXX HACK for buggy URLs in FRAN inventories (cf #15142125)
            if illustration_url and illustration_url.endswith("msp-min.jpg"):
                illustration_url = illustration_url.replace(".msp-min.jpg", "-min.jpg")
        return {"role": role, "illustration_url": illustration_url, "url": href}

    def merge_daogrp(self, daogrp):
        dao_defs = []
        by_role = defaultdict(list)
        for tagpath in ("dao", "daoloc"):
            for dao in daogrp.findall(tagpath):
                ddef = self.daodef(dao)
                if ddef is None:
                    continue
                if ddef["illustration_url"] is not None:
                    dao_defs.append(ddef)
                else:
                    by_role[ddef["role"]].append(ddef)
        folder = by_role.pop("dossier", [None])[0]
        prefix = by_role.pop("prefixe", [None])[0]
        ext = by_role.pop("extension", [None])[0]
        if folder and prefix and ext:
            first = by_role.pop("premier", [None])[0]
            if first:
                illustration_url = "{}/{}{}.{}".format(
                    folder["url"], prefix["url"], first["url"], ext["url"]
                )
                dao_defs.append(
                    {"role": "thumbnail", "illustration_url": illustration_url, "url": None}
                )
            last = by_role.pop("dernier", [None])[0]
            if last:
                illustration_url = "{}/{}{}.{}".format(
                    folder["url"], prefix["url"], last["url"], ext["url"]
                )
                dao_defs.append(
                    {"role": "thumbnail", "illustration_url": illustration_url, "url": None}
                )
        for defs in list(by_role.values()):
            dao_defs.extend(defs)
        return dao_defs

    def component_daos(self, node):
        dao_defs = []
        for tagpath in ("dao", "daoloc", "did/dao", "did/daoloc"):
            for dao in node.findall(tagpath):
                ddef = self.daodef(dao)
                if ddef is not None:
                    dao_defs.append(ddef)
        for tagpath in ("daogrp", "did/daogrp"):
            for daogrp in node.findall(tagpath):
                dao_defs.extend(self.merge_daogrp(daogrp))
        return dao_defs

    def check_c_id_unicity(self, tree):
        c_ids = [x for x in tree.xpath(".//c[@id]/@id")]
        duplicate_ids = [c_id for c_id, count in Counter(c_ids).items() if count > 1 and c_id != ""]
        if duplicate_ids:
            raise InvalidFindingAid(f"Duplicate c@id : {', '.join(duplicate_ids)}")
