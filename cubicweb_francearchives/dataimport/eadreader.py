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
from collections import defaultdict
from itertools import chain


from lxml import etree

from logilab.common.decorators import cachedproperty

from cubicweb import _


from cubicweb_francearchives.dataimport import (
    normalize_entry,
    remove_extension,
    strip_nones,
    usha1,
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


def file_info(node, relfiles):
    href = node.attrib.get("href")
    if href:
        title = osp.basename(href)
        filepath = relfiles.get(title)
        if filepath:
            return {
                "filepath": filepath,
                "title": osp.basename(href),
                "sha1": usha1(open(filepath, "rb").read()),
            }


def component_additional(node, relfiles):
    description = []
    referenced_files = []
    for tag in ("otherfindaid", "relatedmaterial", "separatedmaterial", "originalsloc"):
        for child in node.findall(tag):
            if tag != "originalsloc" and relfiles:
                # index files
                for archref in child.xpath(".//archref"):
                    finfo = file_info(archref, relfiles)
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


FRAD085_RE = re.compile(r"^(fr\\ad85)\\(.*)", re.I)


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


def preprocess_ead(filepath):
    """Preprocesses the EAD xml file to remove ns and internal content

    Parameters:
    -----------

    filepath : the path to the EAD xml file

    Returns:
    --------

    the lxml etree object, cleaned from internal content
    """
    tree = etree.parse(filepath)
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
        return None
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
    def __init__(self, tree, relfiles=None, log=None):
        self.tree = tree
        self.relfiles = relfiles
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

    def archdesc_index_nodes(self):
        for node in self.archdesc_controlacces_nodes(INDEX_TYPES):
            yield node

    def archdesc_controlacces_nodes(self, tagnames):
        archdesc = self.archdesc
        did = self.fa_maindid
        for tagname in tagnames:
            for node in chain(
                archdesc.findall("controlaccess/{}".format(tagname)),
                did.findall(".//unittitle/{}".format(tagname)),
            ):
                if node is not None:
                    yield node

    def archdesc_controlacces(self, tagname):
        values = []
        for node in self.archdesc_controlacces_nodes((tagname,)):
            if node is not None and node.text:
                values.append(node.text.strip())
        return " ; ".join(values)

    def component_index_nodes(self, component):
        for node in self.component_controlacces_nodes(component, INDEX_TYPES):
            yield node

    def component_controlacces_nodes(self, component, tagnames):
        for tagname in tagnames:
            for node in component.findall("controlaccess/{}".format(tagname)):
                if node is not None:
                    yield node

    def component_controlacces(self, component, tagname):
        values = []
        for node in self.component_controlacces_nodes(component, (tagname,)):
            if node is not None and node.text:
                values.append(node.text.strip())
        return " ; ".join(values)

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
        additional_resources, referenced_files = component_additional(archdesc, self.relfiles)
        did_info = self.did_properties(self.fa_maindid)
        return {
            "fatype": archdesc.get("type"),
            "description": component_description(archdesc),
            "description_format": "text/html",
            "bibliography": component_bibliography(archdesc),
            "bibliography_format": "text/html",
            "bioghist": to_html(archdesc.find("bioghist")),
            "bioghist_format": "text/html",
            "accessrestrict": to_html(archdesc.find("accessrestrict")),
            "accessrestrict_format": "text/html",
            "userestrict": to_html(archdesc.find("userestrict")),
            "userestrict_format": "text/html",
            "acquisition_info": component_acqinfo(archdesc),
            "acquisition_info_format": "text/html",
            "additional_resources": additional_resources,
            "additional_resources_format": "text/html",
            "scopecontent": component_scopecontent(archdesc),
            "scopecontent_format": "text/html",
            "notes": to_html(archdesc.find("odd")),
            "notes_format": "text/html",
            "index_entries": list(self.index_entries(self.archdesc_index_nodes())),
            "origination": list(self.origination(self.fa_maindid)),
            "did": did_info,
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
            except InvalidFindingAid:
                self.log.warning("ignoring invalid component at path %s", idx)
                continue
            yield comp_node, comp_props
            for subcomp_node, subcomp_props in self.walk(comp_node, comp_props):
                yield subcomp_node, subcomp_props

    def component_properties(self, cnode, parent, component_index):
        """FAComponent properties"""
        did = cnode.find("did")
        eadid = self.fa_headerprops()["eadid"]
        additional_resources, referenced_files = component_additional(cnode, self.relfiles)
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
            "accessrestrict": to_html(cnode.find("accessrestrict")),
            "accessrestrict_format": "text/html",
            "userestrict": to_html(cnode.find("userestrict")),
            "userestrict_format": "text/html",
            "origination": list(self.origination(did)),
            "notes": to_html(cnode.find("odd")),
            "notes_format": "text/html",
            # 'stable_id': component_stable_id(context['fa']['stable_id'],  # XXX
            #                                  context['path']),
            "daos": self.component_daos(cnode, eadid),
            "path": parent.get("path", ()) + (component_index,),
            # remove exact duplicates but keep variants and let
            # postprocess_ead_index handle them
            "index_entries": unique_indices(
                chain(
                    parent["index_entries"], self.index_entries(self.component_index_nodes(cnode))
                ),
                keys=("type", "label"),
            ),
            "referenced_files": referenced_files,
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

    def merge_daogrp_FRAD085(self, daogrp, eadid):
        """cf. https://extranet.logilab.fr/ticket/15384564"""
        dao_defs = []
        base_url = (
            "http://www.archinoe.net/cg85/visu_serie.php?serie={serie}&"
            "dossier={dos}&page=1&pagefin={nombre}"
        )
        for tagpath in ("dao", "daoloc"):
            kwargs = {}
            illustration_url = None
            illustration_role = None
            for dao in daogrp.findall(tagpath):
                ddef = self.daodef(dao)
                if ddef is None:
                    continue
                role = ddef["role"]
                if role == "nombre":
                    kwargs["nombre"] = ddef["url"]
                else:
                    illustration_url = ddef["illustration_url"]
                    illustration_role = role
                    iurl = ddef["url"] or illustration_url
                    matchobj = re.match(FRAD085_RE, iurl)
                    if matchobj:
                        dos = matchobj.groups()[1].replace("\\", "/")
                        if dos.endswith(".jpg"):
                            dos = dos.split(".jpg")[0]
                        kwargs.update({"serie": eadid.split("FRAD085_")[1], "dos": dos})
            kwargs = {k: v for k, v in list(kwargs.items()) if v}
            try:
                url = base_url.format(**kwargs)
            except KeyError:
                continue
            dao_defs.append(
                {"role": illustration_role, "url": url, "illustration_url": illustration_url}
            )
        return dao_defs

    def component_daos(self, node, eadid):
        dao_defs = []
        for tagpath in ("dao", "daoloc", "did/dao", "did/daoloc"):
            for dao in node.findall(tagpath):
                ddef = self.daodef(dao)
                if ddef is not None:
                    dao_defs.append(ddef)
        for tagpath in ("daogrp", "did/daogrp"):
            for daogrp in node.findall(tagpath):
                if eadid.startswith("FRAD085_"):
                    dao_defs.extend(self.merge_daogrp_FRAD085(daogrp, eadid))
                else:
                    dao_defs.extend(self.merge_daogrp(daogrp))
        return dao_defs
