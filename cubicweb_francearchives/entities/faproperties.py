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

from lxml import etree

from os import path as osp

from logilab.common.decorators import cachedproperty, cached

from cubicweb.predicates import is_instance

from cubicweb_francearchives.views import exturl_link
from cubicweb_francearchives.dataimport import remove_extension
from cubicweb_francearchives.utils import cut_words

from cubicweb_francearchives.entities.adapters import EntityMainPropsAdapter


from cubicweb_francearchives.utils import remove_html_tags
from cubicweb_francearchives.xmlutils import process_html_as_xml, fix_fa_external_links


@process_html_as_xml
def fix_links(root, cnx, labels=None):
    """take html as first argument `root`. This argument is then transformed
    in etree root by process_html_as_xml

    """
    fix_fa_external_links(root, cnx)
    if labels:
        insert_labels(cnx, root, labels)
    else:
        translate_labels(cnx, root)


def insert_labels(cnx, root, labels):
    for label in labels:
        _class = "ead-section ead-%s" % label
        for parent in root.xpath("//div[@class='%s']" % _class):
            # test the empty parent
            if not any(r.strip() for r in parent.xpath(".//child::*/text()")):
                continue
            if not parent.xpath(".//div[@class='ead-label']"):
                div = '<div class="ead-label">%s</div>' % cnx._("%s_label" % label)
                parent.insert(0, etree.XML(div))


def translate_labels(cnx, root):
    for node in root.xpath("//div[@class='ead-label']"):
        node.text = cnx._(node.text)


def format_html(html, text_format="text/html"):
    if html and remove_html_tags(html).strip():
        if text_format != "text/html":
            # XXX use mtc_transform
            return remove_html_tags(html).strip()
        return html
    return None


def process_html(cnx, html, text_format="text/html", labels=None):
    processed = fix_links(html, cnx, labels)
    if processed:
        return format_html(processed, text_format)


def process_title(title):
    splited = title.split("|")
    if len(splited) > 1:
        return "<br />".join(e.strip() for e in splited)
    return title


class AbstractFAEntityMainPropsAdapter(EntityMainPropsAdapter):
    __regid__ = "entity.main_props"
    __abstract__ = True

    def __init__(self, _cw, **kwargs):
        fmt = kwargs.get("fmt", {"text": "text/html", "vid": "incontext"})
        self.text_format = fmt["text"]
        self.vid = fmt["vid"]
        super(AbstractFAEntityMainPropsAdapter, self).__init__(_cw, **kwargs)

    def clean_value(self, entity, attr):
        """skip data containing html tags without actual value"""
        return process_html(self._cw, entity.printable_value(attr), text_format=self.text_format)

    @cached
    def shortened_title(self, max_length=130):
        return process_title(cut_words(self.entity.dc_title(), max_length))

    @cachedproperty
    def formatted_title(self):
        return process_title(self.entity.dc_title())

    def formatted_description(self):
        return process_html(
            self._cw,
            self.entity.printable_value("description"),
            text_format=self.text_format,
            labels=["accruals", "appraisal", "arrangement"],
        )

    def bibliography(self):
        return self.clean_value(self.entity, "bibliography")

    def formatted_acqinfo(self):
        return process_html(
            self._cw,
            self.entity.printable_value("acquisition_info"),
            text_format=self.text_format,
            labels=["custodhist"],
        )

    def formatted_additional_resources(self):
        return process_html(
            self._cw,
            self.entity.printable_value("additional_resources"),
            text_format=self.text_format,
            labels=["originalsloc"],
        )

    def formatted_physdec(self):
        return process_html(
            self._cw, self.did.printable_value("physdesc"), text_format=self.text_format
        )

    def publisher_export_label(self):
        if self.entity.related_service:
            return self.entity.related_service.dc_title()
        return self.entity.publisher

    @cachedproperty
    def dates(self):
        if self.did.period:
            return self.did.period
        return self.did.unitdate

    def languages(self, did):
        desc = did.lang_description
        if desc and did.lang_code not in ("fre", "fr", "français"):
            return desc

    @cachedproperty
    def formatted_dates(self):
        _ = self._cw._
        date = self.dates
        if date:
            date = "%s %s" % (_("Date :"), date)
        else:
            date = _("Sans date")
        return date

    @cachedproperty
    def formatted_content(self):
        content = [
            self.clean_value(self.entity, "scopecontent"),
            self.clean_value(self.did, "abstract"),
        ]
        return "\n".join(e for e in content if e).strip() if content else ""

    @cachedproperty
    def bioghist(self):
        data = [
            self.clean_value(self.did, "origination"),
            self.clean_value(self.entity, "bioghist"),
        ]
        return "\n".join(e for e in data if e).strip() if data else ""

    @cachedproperty
    def did(self):
        did = self.entity.did[0]
        did.complete()
        return did

    @cachedproperty
    def attachment(self):
        return None

    def downloadable_attachements(self):
        return None

    def properties(self, export=False, vid="incontext", text_format="text/html"):
        self.text_format = text_format
        self.vid = vid
        _ = self._cw._
        entity = self.entity
        did = self.did
        formatted_title = self.formatted_title
        properties = []
        if export:
            properties = [
                (_("title_label"), formatted_title),
                (_("period_label"), self.dates),
                (_("publisher_label"), remove_extension(self.publisher_export_label())),
            ]
        else:
            shortened_title = self.shortened_title()
            if shortened_title != formatted_title:
                properties = [(_("title_label"), formatted_title)]
        properties += [(_("scopecontent_label"), self.formatted_content)]
        if did.unitid:
            properties.append((_("unitid_label"), remove_extension(did.unitid)))
        properties.extend(self.pre_additional_props())
        properties.extend(self.common_props())
        properties.extend(self.post_additional_props())
        agent_types = defaultdict(list)
        for index in entity.agent_indexes().entities():
            agent_types[index.type].append(index)
        for label, itype in (
            (_("persname_index_label"), "persname"),
            (_("corpname_index_label"), "corpname"),
            (_("name_index_label"), "name"),
            (_("famname_index_label"), "famname"),
        ):
            properties.append(
                (_(label), ", ".join(e.view(self.vid) for e in agent_types.get(itype, [])))
            )
        geognames = list(entity.geo_indexes().entities()) + list(
            entity.main_indexes("geogname").entities()
        )
        properties.append((_("geo_indexes_label"), ", ".join(e.view(self.vid) for e in geognames)))
        subject_types = defaultdict(list)
        for index in entity.subject_indexes().entities():
            subject_types[index.type].append(index)
        for label, itype in (
            (_("subject_indexes_label"), "subject"),
            (_("genreform_label"), "genreform"),
            (_("function_label"), "function"),
            (_("occupation_label"), "occupation"),
        ):
            properties.append(
                (_(label), ", ".join(e.view(self.vid) for e in subject_types.get(itype, [])))
            )
        if export:
            attachment = self.attachment
            if attachment:
                properties.append(
                    (_("file_label"), attachment.cw_adapt_to("IDownloadable").download_url())
                )
        return [entry for entry in properties if entry[-1]]

    def csv_export_props(self):
        title = self._cw._("Download shelfmark")
        return {
            "url": self._cw.build_url("%s.csv" % self.entity.rest_path()),
            "title": "{} - CSV".format(title),
            "link": title,
        }

    def common_props(self):
        _ = self._cw._
        entity = self.entity
        did = self.did
        return [
            (_("bioghist_label"), self.bioghist),
            (_("acquisition_info_label"), self.formatted_acqinfo()),
            (_("description_label"), self.formatted_description()),
            (_("accessrestrict_label"), self.clean_value(entity, "accessrestrict")),
            (_("userestrict_label"), self.clean_value(entity, "userestrict")),
            (_("languages_label"), self.languages(did)),
            (_("physdesc_label"), self.formatted_physdec()),
            (_("materialspec_label"), self.clean_value(did, "materialspec")),
            (_("additional_resources_label"), self.formatted_additional_resources()),
            (_("bibliography_label"), self.bibliography()),
            (_("notes_label"), self.clean_value(entity, "notes")),
            (_("physloc_label"), self.clean_value(did, "physloc")),
            (_("repository_label"), self.clean_value(did, "repository")),
        ]

    def pre_additional_props(self):
        return []

    def post_additional_props(self):
        _ = self._cw._
        return [
            (_("note_label"), self.clean_value(self.did, "note")),
        ]


class FAComponentEntityMainPropsAdapter(AbstractFAEntityMainPropsAdapter):
    __select__ = is_instance("FAComponent")

    def pre_additional_props(self):
        _ = self._cw._
        entity = self.entity
        return [
            (
                _("digitized_versions_label"),
                ", ".join(
                    str(exturl_link(self._cw, url, label=_("consult the digitized version")))
                    for url in entity.digitized_urls
                ),
            ),
            (_("related_finding_aid_label"), entity.finding_aid[0].view(self.vid)),
        ]

    def downloadable_attachements(self):
        return [self.csv_export_props()]


class FindingEntityMainPropsAdapter(AbstractFAEntityMainPropsAdapter):
    __select__ = is_instance("FindingAid")

    @cachedproperty
    def attachment(self):
        rset = self._cw.execute(
            "Any A, D, FT, N LIMIT 1 WHERE "
            "F is FindingAid, F eid %(e)s, "
            'NOT A data_format "application/xml", '
            "F findingaid_support A, A data D, "
            "A data_format FT, A data_name N",
            {"e": self.entity.eid},
        )
        if rset:
            return rset.one()
        return None

    @cachedproperty
    def ape(self):
        rset = self._cw.execute(
            "Any A LIMIT 1 WHERE " "F is FindingAid, F eid %(e)s, " "F ape_ead_file A",
            {"e": self.entity.eid},
        )
        if rset:
            return rset.one()
        return None

    def pre_additional_props(self):
        _ = self._cw._
        entity = self.entity
        faheader = entity.fa_header[0]
        return [
            (_("eadid_label"), remove_extension(entity.eadid)),
            (_("publicationstmt_label"), self.clean_value(faheader, "publicationstmt")),
        ]

    def post_additional_props(self):
        _ = self._cw._
        entity = self.entity
        faheader = entity.fa_header[0]
        return [
            # XXX we should check xslt transform before displaying this field
            # (_('titlestmt_label'), self.clean_value(faheader, 'titlestmt')),
            (_("note_label"), self.clean_value(self.did, "note")),
            (_("changes_label"), self.clean_value(faheader, "changes")),
        ]

    def downloadable_attachements(self):
        links = []
        _ = self._cw._
        for text, attachment in (
            # NOTE: don't display (yet) the download APE link
            # (self._cw._('Download the APE'), self.ape)
            (_("Download the inventory"), self.attachment),
        ):
            if attachment is None:
                continue
            if not attachment.data:
                # file contents could not be loaded
                continue
            adapted = attachment.cw_adapt_to("IDownloadable")
            filename, extension = osp.splitext(adapted.download_file_name())
            file_infos = None
            if extension:
                file_infos = " ({}, {})".format(extension[1:].upper(), attachment.formatted_size())
            links.append(
                {
                    "url": adapted.download_url(),
                    "target_blank": True,
                    "title": "{}{}{}".format(filename, file_infos, _("- New window")),
                    "link": text,
                }
            )
        links.append(self.csv_export_props())
        return links
