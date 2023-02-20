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
"""cubicweb-francearchives specific hooks and operations"""

import logging
import os
from uuid import uuid4
from rql import BadRQLQuery

from cubicweb.server import hook

from cubicweb.hooks.integrity import IntegrityHook, TidyHtmlFields
from cubicweb.predicates import score_entity, is_instance, relation_possible, adaptable

from cubicweb_francearchives import (
    init_bfss,
    check_static_css_dir,
    register_auth_history,
    Authkey,
    SECTIONS,
    FranceArchivesS3Storage,
    S3_ACTIVE,
)
from cubicweb_francearchives.cssimages import HERO_SIZES

from cubicweb_francearchives.cssimages import generate_thumbnails
from cubicweb_francearchives.htmlutils import soup2xhtml
from cubicweb_francearchives.utils import populate_terms_cache
from cubicweb_francearchives.xmlutils import enhance_accessibility, handle_subtitles

from cubicweb_varnish.hooks import PurgeUrlsOnUpdate, InvalidateVarnishCacheOp


class AuthorityIntegrityError(Exception):
    """raised when attempt to delete a non-orphan Authority"""


# in cubicweb-varnish <= 0.3.0, hook class has no category.
PurgeUrlsOnUpdate.category = "varnish"


log = logging.getLogger(__name__)


class ServerStartupHook(hook.Hook):
    __regid__ = "pnia_atelier.serverstartup"
    events = ("server_startup", "server_maintenance")

    def __call__(self):
        init_bfss(self.repo)
        check_static_css_dir(self.repo)
        if not self.repo.config.creating:
            # we don't want to execute the hook when we are creating database
            with self.repo.internal_cnx() as cnx:
                rset = cnx.execute("Any X WHERE X is Section, X name 'gerer'")
                if rset:
                    SECTIONS["gerer"] = rset[0][0]


def is_css_image(entity):
    images = entity.reverse_image_file
    if images:
        return bool(images[0].cw_etype == "CssImage")
    return False


class UpdateHeroImageHook(hook.Hook):
    """ """

    __regid__ = "francearchives.update_thumbnails"
    __select__ = (
        hook.Hook.__select__ & is_instance("File") & score_entity(lambda x: is_css_image(x))
    )
    events = ("before_update_entity",)

    def __call__(self):
        entity = self.entity
        if "data" in entity.cw_edited:
            GenerateImageThumbnailsOp.get_instance(self._cw).add_data(
                (entity.eid, entity.reverse_image_file[0].cssid)
            )


class AuthorityRenameHook(hook.Hook):
    __regid__ = "francearchives.authority-rename"
    __select__ = hook.Hook.__select__ & is_instance(
        "AgentAuthority", "LocationAuthority", "SubjectAuthority"
    )
    events = ("before_update_entity",)

    def __call__(self):
        old_label, new_label = self.entity.cw_edited.oldnewvalue("label")
        if old_label != new_label:
            RegisterRenamedAuthHistoryOp.get_instance(self._cw).add_data((self.entity.eid))


class AuthorityDeleteHook(hook.Hook):
    __regid__ = "francearchives.authority-delete"
    __select__ = hook.Hook.__select__ & is_instance(
        "AgentAuthority", "LocationAuthority", "SubjectAuthority"
    )
    events = ("before_delete_entity",)

    def __call__(self):
        if not self.entity.is_orphan:
            raise AuthorityIntegrityError(
                self._cw._(
                    "Forbidden to delete a non-orphan {etype} {eid}".format(
                        etype=self.entity.cw_etype, eid=self.entity.eid
                    )
                )
            )
        if not self._cw.transaction_data.get(
            "delete-orphans"
        ) and not self._cw.transaction_data.get("blacklist"):
            self.error(f"Trying to delete authority {self.entity.cw_etype} {self.entity.eid} ")
            from traceback import print_stack

            print_stack()
            raise AuthorityIntegrityError(f"Forbidden attempt to delete an authority {self.entity}")


class RegisterRenamedAuthHistoryOp(hook.DataOperationMixIn, hook.Operation):
    def precommit_event(self):
        # XXX should we do it in postcommit ?
        for auth_eid in self.get_data():
            self.cnx.entity_from_eid(auth_eid).add_to_auth_history()


class AuthorityHistory(hook.Hook):
    __regid__ = "francearchives.authority-history"
    __select__ = hook.Hook.__select__ & hook.match_rtype("authority")
    events = ("after_add_relation",)

    def __call__(self):
        RegisterAuthHistoryOp.get_instance(self._cw).add_data((self.eidto, self.eidfrom))


class RegisterAuthHistoryOp(hook.DataOperationMixIn, hook.Operation):
    def precommit_event(self):
        cnx = self.cnx
        for eidto, eidfrom in self.get_data():
            auth = cnx.entity_from_eid(eidto)
            controlaccess = cnx.entity_from_eid(eidfrom)
            try:
                fa_or_fac = controlaccess.index[0]
                if fa_or_fac.cw_etype == "FindingAid":
                    fa_stable_id = fa_or_fac.stable_id
                else:
                    fa_stable_id = fa_or_fac.finding_aid[0].stable_id
            except IndexError:
                # no link to any findingaid so ignore history registration
                continue
            key = Authkey(fa_stable_id, controlaccess.type, controlaccess.label, controlaccess.role)
            register_auth_history(cnx, key, auth.eid)


class NewCssImageFile(hook.Hook):
    __regid__ = "francearchives.file-css-image"
    __select__ = hook.Hook.__select__ & hook.match_rtype("image_file")
    events = ("after_add_relation",)

    def __call__(self):
        image = self._cw.entity_from_eid(self.eidfrom)
        if image.cw_etype == "CssImage":
            GenerateImageThumbnailsOp.get_instance(self._cw).add_data((self.eidto, image.cssid))


class GenerateImageThumbnailsOp(hook.DataOperationMixIn, hook.Operation):
    def precommit_event(self):
        cnx = self.cnx
        for eid, cssid in self.get_data():
            if cnx.deleted_in_transaction(eid):
                continue
            entity = cnx.entity_from_eid(eid)
            generate_thumbnails(cnx, entity, "%s.jpg" % cssid, HERO_SIZES)


class UUIDHook(hook.Hook):
    __regid__ = "francearchives.uuid"
    __select__ = hook.Hook.__select__ & relation_possible("uuid")
    events = ("before_add_entity",)

    def __call__(self):
        if "uuid" not in self.entity.cw_edited:
            self.entity.cw_edited["uuid"] = str(uuid4().hex)


class PurgeUrlsOnAddOrDelete(hook.Hook):
    """an entity was deleted, purge related urls"""

    __regid__ = "francearchives.varnish.add-or-delete"
    __select__ = hook.Hook.__select__ & adaptable("IVarnish")
    events = ("before_delete_entity", "after_add_entity")

    def __call__(self):
        invalidate_cache_op = InvalidateVarnishCacheOp.get_instance(self._cw)
        ivarnish = self.entity.cw_adapt_to("IVarnish")
        for url in ivarnish.urls_to_purge():
            invalidate_cache_op.add_data(url)


class UpdateVarnishOnRelationChanges(hook.Hook):
    __regid__ = "francearchives.varnish"
    events = ("after_add_relation", "after_delete_relation")

    def __call__(self):
        rschema = self._cw.vreg.schema.rschema(self.rtype)
        if rschema.meta:
            return
        ivarnish_from = self._cw.entity_from_eid(self.eidfrom).cw_adapt_to("IVarnish")
        ivarnish_to = self._cw.entity_from_eid(self.eidto).cw_adapt_to("IVarnish")
        urls = []
        if ivarnish_from is not None:
            urls.extend(ivarnish_from.urls_to_purge())
        if ivarnish_to is not None:
            urls.extend(ivarnish_to.urls_to_purge())
        if urls:
            cache_op = InvalidateVarnishCacheOp.get_instance(self._cw)
            for url in urls:
                cache_op.add_data(url)


class DeleteSameAsAuthAgent(hook.Hook):
    """When an AuthorityRecord entity is beeing deleted, this hook
    delete the same_as relations between the AuthorityRecord and its
    AgentAuthority.
    """

    __select__ = hook.Hook.__select__ & is_instance("AuthorityRecord")
    __regid__ = "eac.delete-agent-sameas-authority"
    events = ("before_delete_entity",)

    def __call__(self):
        self._cw.execute("DELETE X same_as Y WHERE Y eid %(eid)s", {"eid": self.entity.eid})


class PniaTidyHtmlFields(IntegrityHook):
    """tidy HTML in rich text strings; applies Rgaa Rules"""

    __regid__ = "pnia_htmltidy"
    events = ("before_add_entity", "before_update_entity")
    category = "tidyhtml"

    def __call__(self):
        entity = self.entity
        cnx = self._cw
        attrs = []
        edited = entity.cw_edited
        subjrels = cnx.vreg.schema.eschema(self.entity.cw_etype).subjrels
        for rel in subjrels:
            if rel.type.endswith("_format"):
                attr = rel.type.split("_format")[0]
                if attr in subjrels and attr in edited:
                    attrs.append(
                        (rel.type, attr),
                    )
        for metaattr, attr in attrs:
            value = edited[attr]
            if isinstance(value, str):  # filter out None and Binary
                text_format = None
                if self.event == "before_add_entity":
                    try:
                        rel = self._cw.vreg.schema[metaattr].rdef(entity.cw_etype, "String")
                        if rel:
                            text_format = rel.default
                    except KeyError:
                        continue
                else:
                    text_format = getattr(entity, str(metaattr))
                if text_format == "text/html":
                    # tidy up the value
                    value = soup2xhtml(value, self._cw.encoding)
                    # applied rgaa rules
                    value = enhance_accessibility(value, cnx)
                    if attr == "content":
                        # look for subtitles
                        lang = getattr(self.entity, "language", None)
                        value = handle_subtitles(value, cnx, lang=lang)
                    edited[attr] = value


class GlossaryStartupHook(hook.Hook):
    """
    populate Glossary cache on startup
    """

    __regid__ = "francearchive.glossary"
    events = ("server_startup",)
    category = "glossary"

    def __call__(self):
        if self.repo.config.creating:
            # we don't want to execute the hook when we are creating database
            return
        with self.repo.internal_cnx() as cnx:
            self.info("Creating Glossary cache")
            try:
                populate_terms_cache(cnx)
            except BadRQLQuery:
                pass


class S3StorageStartupHook(hook.Hook):
    __regid__ = "francearchives.server-startup-hook"
    events = ("server_startup", "server_maintenance")

    def __call__(self):
        # feature flag: do not handle S3 attributes when S3 is disabled
        if S3_ACTIVE:
            storage = FranceArchivesS3Storage(os.getenv("AWS_S3_BUCKET_NAME"))
            self.repo.system_source.set_storage("File", "data", storage)


def registration_callback(vreg):
    vreg.unregister(TidyHtmlFields)
    vreg.register_all(list(globals().values()), __name__)
