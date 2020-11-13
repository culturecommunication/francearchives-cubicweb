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

"""cubicweb-pnia-content entity's classes"""
import re
from collections import OrderedDict
import csv
import urllib.request
import urllib.parse
import urllib.error

from babel.dates import format_date

import json
from io import StringIO

from logilab.common.decorators import cachedproperty

from rql import TypeResolverException

from cubicweb import NoResultError, MultipleResultsError
from cubicweb.predicates import is_instance, score_entity, has_related_entities
from cubicweb.entities import AnyEntity, fetch_config
from cubicweb.entity import _marker

from cubicweb_francearchives import CMS_I18N_OBJECTS
from cubicweb_francearchives.entities import ETYPE_CATEGORIES
from cubicweb_francearchives.entities.es import (
    PniaIFullTextIndexSerializable,
    TranslatableIndexSerializableMixin,
)
from cubicweb_francearchives.entities.ead import IndexableMixin
from cubicweb_francearchives.dataimport import normalize_entry
from cubicweb_francearchives.dataimport.pdf import pdf_infos
from cubicweb_francearchives.dataimport.eadreader import unique_indices
from cubicweb_francearchives.utils import safe_cut, id_for_anchor

from cubicweb_francearchives.xmlutils import process_html_as_xml, add_title_on_external_links
from cubicweb_francearchives.utils import remove_html_tags


class RelatedAutorityIndexableMixin(IndexableMixin):
    def agent_indexes(self):
        return self._cw.execute(
            "DISTINCT Any X, XP WHERE E eid %(e)s, "
            "E related_authority X, X is AgentAuthority, "
            "X label XP",
            {"e": self.eid},
        )

    def subject_indexes(self):
        return self._cw.execute(
            "DISTINCT Any X, XP WHERE E eid %(e)s, "
            "E related_authority X, X is SubjectAuthority, "
            "X label XP",
            {"e": self.eid},
        )

    def geo_indexes(self):
        return self._cw.execute(
            "DISTINCT Any X, XP WHERE E eid %(e)s, "
            "E related_authority X, X is LocationAuthority, "
            "X label XP",
            {"e": self.eid},
        )

    def es_indexes(self):
        """method used in AbstractCMSIFTIAdapter"""
        return self._cw.execute(
            "Any L, NORMALIZE_ENTRY(L), A WHERE X related_authority A, A label L, X eid %(e)s",
            {"e": self.eid},
        )

    def main_indexes(self, itype):
        # itype is only here for compatibility with IndexableMixin
        return self._cw.execute(
            "DISTINCT Any X, XP WHERE E eid %(e)s, "
            "E related_authority X, X is AgentAuthority, "
            "X label XP",
            {"e": self.eid},
        )


@process_html_as_xml
def enhance_rgaa(root, cnx, labels=None):
    """take html as first argument `root`. This argument is then transformed
    in etree root by process_html_as_xml
    """
    for node in root.xpath("//*[@href]"):
        add_title_on_external_links(cnx, node, node.attrib["href"])


class ImageMixIn(object):
    image_rel_name = None

    @cachedproperty
    def image(self):
        if self.image_rel_name:
            images = self.related(self.image_rel_name)
            if images:
                return images.get_entity(0, 0)

    @property
    def illustration_url(self):
        if self.image:
            return self.image.image_file[0].cw_adapt_to("IDownloadable").download_url()

    @cachedproperty
    def illustration_alt(self):
        if self.image:
            return self.image.alt
        return ""


class HTMLMixIn(object):
    @cachedproperty
    def richstring_attrs(self):
        attrs = []
        subjrels = self._cw.vreg.schema.eschema(self.cw_etype).subjrels
        for rel in subjrels:
            if rel.type.endswith("_format"):
                attr = rel.type.split("_format")[0]
                if attr in subjrels:
                    attrs.append(attr)
        return attrs

    def printable_value(
        self, attr, value=_marker, attrtype=None, format="text/html", displaytime=True
    ):
        """return a displayable value (i.e. unicode string) which may contains
        html tags. ̀enhance_rgaa`  may retrun None
        """
        value = super(HTMLMixIn, self).printable_value(attr, value, attrtype, format, displaytime)
        if value and attr in self.richstring_attrs:
            return enhance_rgaa(value, self._cw) or ""
        return value


class CmsObject(ImageMixIn, HTMLMixIn, AnyEntity):
    __abstract__ = True

    @cachedproperty
    def img(self):
        pass

    @cachedproperty
    def fmt_creation_date(self):
        return format_date(self.creation_date, "d MMMM y", locale=self._cw.lang)

    def dc_authors(self):
        if self.metadata:
            return self.metadata[0].creator
        return super(CmsObject, self).dc_authors()


class TranslatableCmsObject(CmsObject):
    def i18n_query(self, *args, **kwargs):
        attrs, fvars = [], []
        for i, field in enumerate(self.i18nfields):
            attrs.append("X {field} F{i}".format(i=i, field=field))
            fvars.append("F{i}".format(i=i))
        query = """Any X, {fvars}, L ORDERBY L WHERE X translation_of E,
          {attrs}, X language L, E eid %(e)s""".format(
            fvars=", ".join(fvars), attrs=", ".join(attrs)
        )
        return query

    def i18n_rset(self, *args, **kwargs):
        query = self.i18n_query(*args, **kwargs)
        return self._cw.execute(query, {"e": self.eid})

    def translations(self, *args, **kwargs):
        values = {}
        for res in self.i18n_rset(*args, **kwargs).iter_rows_with_entities():
            entity = res[0]
            values[entity.language] = {attr: getattr(entity, attr) for attr in self.i18nfields}
        return values

    def translations_in_lang(self, lang=None):
        lang = lang or self._cw.lang
        if lang == "fr":
            return {}
        attrs, fvars = [], []
        for i, field in enumerate(self.i18nfields):
            attrs.append("X {field} F{i}".format(i=i, field=field))
            fvars.append("F{i}".format(i=i))
        query = """Any X, {fvars} WHERE X translation_of E,
        {attrs},
        X language %(lang)s, E eid %(e)s""".format(
            fvars=", ".join(fvars), attrs=", ".join(attrs)
        )
        rset = self._cw.execute(query, {"lang": lang, "e": self.eid})
        if rset:
            entity = rset.one()
            return {attr: getattr(entity, attr) for attr in self.i18nfields}
        return {}


class BaseContent(RelatedAutorityIndexableMixin, TranslatableCmsObject):
    __regid__ = "BaseContent"
    image_rel_name = "basecontent_image"
    i18nfields = ("title", "content", "summary")

    def dc_title(self):
        if self._cw.lang == "fr":
            return self.title
        return self.cw_adapt_to("ITemplatable").entity_param().title

    def rest_path(self):
        return "article/{}".format(self.eid)

    @property
    def service(self):
        if self.basecontent_service:
            return self.basecontent_service[0]

    @property
    def is_a_publication(self):
        return bool(
            self._cw.execute(
                ("Any X WHERE X is Section, X name %(n)s, " "X children B, B eid %(e)s"),
                {"n": "publication", "e": self.eid},
            )
        )


class TranslationMixin(object):
    def rest_path(self):
        return "{}/{}".format(self.cw_etype.lower(), self.eid)

    @cachedproperty
    def original_entity(self):
        if self.translation_of:
            return self.translation_of[0]


class BaseContentTranslation(TranslationMixin, CmsObject):
    __regid__ = "BaseContentTranslation"

    @property
    def summary_policy(self):
        return self.original_entity.summary_policy


class NewsContent(CmsObject):
    __regid__ = "NewsContent"
    image_rel_name = "news_image"

    def rest_path(self):
        return "actualite/{}".format(self.eid)

    @property
    def keywords(self):
        pass


class Circular(AnyEntity):
    __regid__ = "Circular"
    rest_attr = "circ_id"

    def rest_path(self):
        return "circulaire/{}".format(self.circ_id)

    def dc_title(self):
        return self.title

    def sort_date(self):
        return self.siaf_daf_signing_date or self.signing_date

    @property
    def values_as_json(self):
        old_lang = self._cw.lang
        if old_lang != "fr":
            # export Concepts in french
            self._cw.set_lang("fr")
        # install i18n configuration for `lang` translation.
        # as self._cw._ is an unicode string
        self._cw.set_language(self._cw.lang)
        values = self.cw_adapt_to("csv-props").csv_row()
        if old_lang != "fr":
            self._cw.set_lang(old_lang)
            self._cw.set_language(old_lang)
        return values

    @property
    def values_from_json(self):
        return json.loads(self.json_values)


class Service(ImageMixIn, HTMLMixIn, AnyEntity):
    fetch_attrs, cw_fetch_order = fetch_config(
        [
            "category",
            "name",
            "name2",
            "city",
            "address",
            "short_name",
            "thumbnail_url",
            "thumbnail_dest",
        ]
    )
    __regid__ = "Service"
    image_rel_name = "service_image"

    @staticmethod
    def from_code(req, code):
        try:
            if code.startswith("c-"):
                if not code[2:].isdigit():
                    return None
                return req.find("Service", eid=(int(code[2:]))).one()
            return req.find("Service", code=code).one()
        except (TypeResolverException, NoResultError, MultipleResultsError):
            return None

    def documents_url(self):
        if self.code:
            code = self.code
        else:
            code = "c-{}".format(self.eid)
        return self._cw.build_url("inventaires/{}".format(code))

    def dc_title(self):
        if self.level == "level-D":
            return self.name2 or self.name
        else:
            terms = [self.name, self.name2]
            return " - ".join(t for t in terms if t)

    def bounce_url(self, attrs):
        if self.search_form_url:
            terms = re.search(r"\{(\w+)\}", self.search_form_url)
            if terms:
                attrs = {
                    k: urllib.parse.quote_plus(v.encode("utf-8"))
                    for k, v in list(attrs.items())
                    if v
                }
                try:
                    return self.search_form_url.format(**attrs)
                except Exception:
                    # could not replace placeholder
                    # see https://extranet.logilab.fr/ticket/69111700
                    return self.website_url
        return self.search_form_url or self.website_url

    def rest_path(self):
        if self.level in ("level-D", "level-C") and self.dpt_code:
            return "annuaire/departements?dpt=%s" % self.dpt_code
        else:
            return "service/{}".format(self.eid)

    def physical_address(self):
        terms = [self.address, self.zip_code, self.city]
        return ", ".join(str(t) for t in terms if t)

    def publisher(self):
        publisher = self.short_name or self.name2 or self.name
        if not publisher and self.code:
            return self.code.upper()
        return publisher

    @property
    def url_anchor(self):
        return "{}#{}".format(self.absolute_url(), id_for_anchor(self.dc_title()))


class Person(AnyEntity):
    __regid__ = "Person"

    def dc_title(self):
        return "{} {}".format(self.forenames, self.name)

    @property
    def label(self):
        """property to ease compatibility with AgentName entities"""
        return self.dc_title()

    def agent_indexes(self):
        return self._cw.execute(
            """
            DISTINCT Any A, L ORDERBY L WHERE P eid %(e)s,
            P authority A, A label L""",
            {"e": self.eid},
        )


# XXX duplicated from cubes.frarchives_edition.views.primary
def get_ancestors(entity, result=None):
    if result is None:
        result = []
    if not hasattr(entity, "reverse_children"):
        return []
    parent = entity.reverse_children
    while parent:
        result.append(parent[0].eid)
        parent = parent[0].reverse_children
    result.reverse()
    return result


class ExternRef(RelatedAutorityIndexableMixin, CmsObject):
    __regid__ = "ExternRef"
    fetch_attrs, cw_fetch_order = fetch_config(["title", "reftype", "content"])
    image_rel_name = "externref_image"

    @property
    def years(self):
        years = [self.start_year, self.stop_year]
        return " - ".join(str(e) for e in years if e)

    @property
    def service(self):
        if self.exref_service:
            return self.exref_service[0]


class MapCSVReader(object):
    fieldnames = OrderedDict(
        [("Code_insee", "code"), ("URL", "url"), ("Couleur", "color"), ("Legende", "legend")]
    )
    delimiter = ","
    # required_fiels is used in cubicweb_frarchives_edition hooks to build error message
    required_fields = ("Code_insee", "Couleur", "Legende")

    def csv_reader(self, csvfile):
        return csv.DictReader(
            csvfile, delimiter=self.delimiter, fieldnames=list(self.fieldnames.keys())
        )

    def csv_headers(self, csvfile):
        return next(csv.reader(csvfile, delimiter=self.delimiter))


class Map(MapCSVReader, ImageMixIn, HTMLMixIn, AnyEntity):
    __regid__ = "Map"
    fetch_attrs = ("title", "map_title", "top_content", "bottom_content")
    image_rel_name = "map_image"

    def dc_title(self):
        return self.title

    def data(self):
        data = []
        fp = StringIO(self.map_file.getvalue().decode("utf-8"))
        reader = self.csv_reader(fp)
        for line in reader:
            entry = {self.fieldnames[key]: value if value else "" for key, value in line.items()}
            if "code" in entry:
                entry["code"] = entry["code"].lower()
            data.append(entry)
        return data


class OfficialText(AnyEntity):
    __regid__ = "OfficialText"
    fetch_attrs, cw_fetch_order = fetch_config(["code", "name"])

    def dc_title(self):
        return self.code

    def dc_description(self):
        return self.name


class CMSI18NIFTIAdapter(PniaIFullTextIndexSerializable):
    __select__ = is_instance(*CMS_I18N_OBJECTS) & has_related_entities("translation_of")

    @cachedproperty
    def original_entity(self):
        return self.entity.original_entity

    @cachedproperty
    def ift_original(self):
        if self.original_entity:
            return self.original_entity.cw_adapt_to("IFullTextIndexSerializable")

    @property
    def es_id(self):
        if self.entity.original_entity:
            return self.ift_original.es_id

    def serialize(self, complete=True):
        if self.entity.original_entity:
            return self.ift_original.serialize(complete)


class AbstractCMSIFTIAdapter(PniaIFullTextIndexSerializable):
    __abstract__ = True

    def serialize(self, complete=True):
        data = super(AbstractCMSIFTIAdapter, self).serialize(complete)
        data["escategory"] = ETYPE_CATEGORIES[self.entity.cw_etype]
        data["ancestors"] = get_ancestors(self.entity)
        return data


class CommemoCollectionIFTIAdapter(AbstractCMSIFTIAdapter):
    __select__ = AbstractCMSIFTIAdapter.__select__ & is_instance("CommemoCollection")


class CardIFTIAdapter(AbstractCMSIFTIAdapter):
    __select__ = AbstractCMSIFTIAdapter.__select__ & is_instance("Card")

    def serialize(self, complete=True):
        if not self.entity.do_index:
            return {}
        return super().serialize(complete=complete)


class NewsContentIFTIAdapter(AbstractCMSIFTIAdapter):
    __select__ = AbstractCMSIFTIAdapter.__select__ & is_instance("NewsContent")
    custom_indexable_attributes = ("start_date", "stop_date")


class MapIFTIAdapter(AbstractCMSIFTIAdapter):
    __select__ = AbstractCMSIFTIAdapter.__select__ & is_instance("Map")

    def serialize(self, complete=True):
        data = super(MapIFTIAdapter, self).serialize(complete)
        data.pop("map_file", None)
        return data


class BaseContentMixIn(TranslatableIndexSerializableMixin):
    def serialize(self, complete=True, **kwargs):
        data = super(BaseContentMixIn, self).serialize(complete)
        services = self.entity.basecontent_service
        if services:
            data["publisher"] = [s.short_name or s.dc_title() for s in services]
        if self.entity.is_a_publication:
            data["cw_etype"] = self._cw._("Publication")
        data["index_entries"] = [
            {"label": label, "normalized": normalized, "authority": auth}
            for label, normalized, auth in self.entity.es_indexes()
        ]
        data.update(self.add_translations(complete=complete, **kwargs))
        return data


class BaseContentWithoutManifProgIFTIAdapter(BaseContentMixIn, AbstractCMSIFTIAdapter):
    __select__ = (
        AbstractCMSIFTIAdapter.__select__
        & is_instance("BaseContent")
        & ~score_entity(lambda bc: bc.reverse_manif_prog)
    )


class BaseContentManifProgIFTIAdapter(BaseContentMixIn, AbstractCMSIFTIAdapter):
    __select__ = (
        AbstractCMSIFTIAdapter.__select__
        & is_instance("BaseContent")
        & score_entity(lambda bc: bc.reverse_manif_prog)
    )

    @cachedproperty
    def ift_commemo(self):
        commemo_item = self.entity.reverse_manif_prog
        return commemo_item[0].cw_adapt_to("IFullTextIndexSerializable")

    @property
    def es_id(self):
        return self.ift_commemo.es_id

    def serialize(self, complete=True):
        return self.ift_commemo.serialize(complete)


class FileAttachmentIFTIAdapter(AbstractCMSIFTIAdapter):
    __select__ = (
        AbstractCMSIFTIAdapter.__select__
        & is_instance("File")
        & score_entity(lambda f: f.reverse_attachment or f.reverse_additional_attachment)
    )

    @cachedproperty
    def ift_circular(self):
        if self.entity.reverse_attachment:
            circular = self.entity.reverse_attachment[0]
        else:
            # predicates guarantees that we either have and attachment or an additional attachment
            circular = self.entity.reverse_additional_attachment[0]
        return circular.cw_adapt_to("IFullTextIndexSerializable")

    @property
    def es_id(self):
        return self.ift_circular.es_id

    def serialize(self, complete=True):
        return self.ift_circular.serialize(complete)


class CommemorationItemIFTIAdapter(TranslatableIndexSerializableMixin, AbstractCMSIFTIAdapter):
    __select__ = AbstractCMSIFTIAdapter.__select__ & is_instance("CommemorationItem")
    i18nfields = ("title", "subtitle", "content")

    def serialize(self, complete=True, **kwargs):
        data = super(CommemorationItemIFTIAdapter, self).serialize(complete)
        data["index_entries"] = [
            {"label": label, "normalized": normalized, "authority": auth}
            for label, normalized, auth in self.entity.es_indexes()
        ]
        prog = [bc.content for bc in self.entity.manif_prog if bc.content]
        if prog:
            data["manif_prog"] = remove_html_tags(" ".join(prog))
        data.update(self.add_translations(complete=complete, **kwargs))
        return data


def get_preflabel(concept):
    for preflabel in concept.preferred_label:
        if preflabel.language_code and preflabel.language_code.lower()[:2] == "fr":
            return preflabel.label
    if concept.preferred_label:
        return concept.preferred_label[0].label


class CircularIFTIAdapter(AbstractCMSIFTIAdapter):
    __select__ = AbstractCMSIFTIAdapter.__select__ & is_instance("Circular")
    custom_indexable_attributes = ("signing_date", "siaf_daf_signing_date")

    def _index_subjects_authorities(self, concept):
        """Add Subject entities to ElasticSearch index Concept entity
        is related to.

        :param Concept concept: Concept entity
        """
        # find related SubjectAuthority entities
        subject_authorities = self._cw.execute(
            "Any X WHERE X is SubjectAuthority, X same_as %(eid)s", {"eid": concept.eid}
        )
        return [{"authority": r[0]} for r in subject_authorities]

    def serialize(self, complete=True):
        data = super(CircularIFTIAdapter, self).serialize(complete)
        signing_date = self.entity.sort_date()
        index_entries = []
        if signing_date:
            data["sort_date"] = signing_date
            data["siaf_daf_signing_year"] = signing_date.year
        for attr in ("siaf_daf_signing_date", "signing_date"):
            if attr in data:
                del data[attr]
        if self.entity.business_field:
            data["business_field"] = bfields = []
            for field in self.entity.business_field:
                bfield = get_preflabel(field)
                if bfield:
                    bfields.append(bfield)
                index_entries += self._index_subjects_authorities(field)
        if self.entity.archival_field:
            data["archival_field"] = self.entity.archival_field
        if self.entity.historical_context:
            data["historical_context"] = get_preflabel(self.entity.historical_context[0])
            index_entries += self._index_subjects_authorities(self.entity.historical_context[0])
        if self.entity.document_type:
            data["document_type"] = get_preflabel(self.entity.document_type[0])
            index_entries += self._index_subjects_authorities(self.entity.document_type[0])
        if self.entity.action:
            data["action"] = get_preflabel(self.entity.action[0])
            index_entries += self._index_subjects_authorities(self.entity.action[0])
        attachments = list(self.entity.attachment) + list(self.entity.additional_attachment)
        if attachments:
            afields = []
            for a in attachments:
                if a.data_format == "application/pdf":
                    # XXX else: try a.printable_value('data',
                    # format='text/plain')
                    fpath = self._cw.execute(
                        "Any fspath(D) WHERE F eid %(e)s, F data D", {"e": a.eid}
                    )[0][0].getvalue()
                    try:
                        text = pdf_infos(fpath).get("text")
                        if text:
                            afields.append(text)
                    except Exception:
                        continue
            data["attachment"] = " ".join(afields)
        if index_entries:
            data["index_entries"] = unique_indices(index_entries, keys=("authority",))
        return data


class ExternRefIFTIAdapter(AbstractCMSIFTIAdapter):
    __select__ = AbstractCMSIFTIAdapter.__select__ & is_instance("ExternRef")

    def serialize(self, complete=True):
        data = super(ExternRefIFTIAdapter, self).serialize(complete)
        data["cw_etype"] = self.entity.reftype.capitalize()
        data["reftype"] = self.entity.reftype.lower()
        data["index_entries"] = [
            {"label": label, "normalized": normalized, "authority": auth}
            for label, normalized, auth in self.entity.es_indexes()
        ]
        services = self.entity.exref_service
        if services:
            data["publisher"] = [s.short_name or s.dc_title() for s in services]
        return data


class PersonIFTIAdapter(AbstractCMSIFTIAdapter):
    __select__ = AbstractCMSIFTIAdapter.__select__ & is_instance("Person")

    def serialize(self, complete=True):
        data = super(PersonIFTIAdapter, self).serialize(complete)
        data["index_entries"] = [
            {"label": label, "normalized": normalize_entry(label), "type": "persname"}
            for __, label, __ in self.entity.agent_indexes()
        ]
        return data


class ServiceIFTIAdapter(AbstractCMSIFTIAdapter):
    __select__ = AbstractCMSIFTIAdapter.__select__ & is_instance("Service")

    def serialize(self, complete=True):
        data = super(ServiceIFTIAdapter, self).serialize(complete)
        data["sort_name"] = self.entity.name
        return data


class ImageMixIn(object):
    @cachedproperty
    def alt(self):
        """use as value of alt attribute in <img>"""
        return safe_cut(self.description, 77, remove_html=True)


class Image(ImageMixIn, HTMLMixIn, AnyEntity):
    __regid__ = "Image"
    fetch_attrs, cw_fetch_order = fetch_config(["description", "caption", "uri"])


class CssImage(ImageMixIn, HTMLMixIn, AnyEntity):
    __regid__ = "CssImage"
    fetch_attrs, cw_fetch_order = fetch_config(["cssid", "description", "caption"])


class GlossaryTerm(AnyEntity):
    __regid__ = "GlossaryTerm"
    fetch_attrs, cw_fetch_order = fetch_config(
        ["term", "term_plural", "short_description", "description"]
    )

    def rest_path(self):
        return "glossaryterm/{}".format(self.eid)

    @cachedproperty
    def fmt_creation_date(self):
        return format_date(self.creation_date, "d MMMM y", locale=self._cw.lang)


class FaqItem(TranslatableCmsObject):
    __regid__ = "FaqItem"
    fetch_attrs, cw_fetch_order = fetch_config(["order", "answer", "question", "category"])
    i18nfields = ("question", "answer")

    def dc_title(self):
        if self._cw.lang == "fr":
            return self.question
        return self.cw_adapt_to("ITemplatable").entity_param().question


class FaqItemTranslation(TranslationMixin, AnyEntity):
    __regid__ = "FaqItemTranslation"
    fetch_attrs, cw_fetch_order = fetch_config(["answer", "question"])
