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
"""ISync adapters

The ISync adapter generates put requests that can be processed
by FranceArchives to update CMS entities.

It is defined as a mean to synchronize edition and consultation
instances.
"""
import requests

from cubicweb.view import EntityAdapter
from cubicweb.predicates import relation_possible, is_instance
from cubicweb.utils import json_dumps


class ISyncAdapter(EntityAdapter):
    __regid__ = "ISync"

    def build_put_body(self, done=None, skip_relations=None):
        return {}


class ISyncUuidAdapter(ISyncAdapter):
    __select__ = relation_possible("uuid")

    skipped_relations = {
        "workflow",
        "workflow_of",
        "default_workflow",
        "custom_workflow",
        "allowed_transition",
        "in_state",
        "transition_of",
        "is",
        "is_instance_of",
        "specializes",
        "identity",
        "add_permission",
        "update_permission",
        "eid",
        "created_by",
        "owned_by",
        "cw_source",
        "previous_info",
        "has_text",
    }

    def build_put_body(self, done=None, skip_relations=None):
        if done is None:
            done = set()
        entity = self.entity
        if entity.eid in done:
            return
        done.add(entity.eid)
        eschema = entity.e_schema
        entity_data = {}
        entity_data["cw_etype"] = entity.cw_etype
        entity.complete()
        for rschema in eschema.ordered_relations():
            relname = rschema.type
            skipped = self.skipped_relations if skip_relations is None else skip_relations
            if relname in skipped:
                continue
            value = getattr(entity, relname)
            if value is None:
                continue
            if rschema.final:
                entity_data[relname] = value
            elif not rschema.meta and rschema.type not in ("has_text",):
                entity_data[relname] = []
                for target in value:
                    body = self.build_target_put_body(target, done)
                    if body is not None:
                        entity_data[relname].append(body)
        return entity_data

    @property
    def uuid_attr(self):
        return "uuid"

    @property
    def uuid_value(self):
        return self.entity.uuid

    def build_target_put_body(self, target, done=None):
        isync = target.cw_adapt_to("ISync")
        if isync is not None:
            return isync.build_put_body(done)

    def delete_entity(self):
        sync_url = self._cw.vreg.config.get("consultation-sync-url")
        if sync_url:
            entity = self.entity
            try:
                url = "{}/_update/{}/{}".format(sync_url, entity.cw_etype, self.uuid_value)
                self.debug("will delete %s", url)
                res = requests.delete(url)
                if res.status_code == 400:
                    # in ``edit.get_by_uuid`` we raise ``HTTPBadRequest`` if no entity found for
                    # this uuid
                    self.debug(
                        "%s with %s: %s does not exists on %s",
                        entity.cw_etype,
                        self.uuid_attr,
                        self.uuid_value,
                        sync_url,
                    )
                    return
                res.raise_for_status()
            except Exception:
                self.exception(
                    "failed to sync %s with %s %s", entity.cw_etype, self.uuid_attr, self.uuid_value
                )

    def put_entity(self, body=None):
        sync_url = self._cw.vreg.config.get("consultation-sync-url")
        if sync_url:
            entity = self.entity
            try:
                body = body or self.build_put_body()
                url = "{}/_update/{}/{}".format(sync_url, entity.cw_etype, self.uuid_value)
                self.debug("will put %s on %s", list(body.keys()), url)
                res = requests.put(url, data=json_dumps(body))
                res.raise_for_status()
            except Exception:
                self.exception(
                    "failed to sync %s with %s %s", entity.cw_etype, self.uuid_attr, self.uuid_value
                )


class ISyncUuidAttrAdapter(ISyncUuidAdapter):
    __select__ = is_instance("Concept")

    def build_put_body(self, done=None, skip_relations=None):
        return {"cw_etype": self.entity.cw_etype, self.entity.uuid_attr: self.entity.uuid_value}


class ISyncCarddAdapter(ISyncUuidAdapter):
    __select__ = is_instance("Card")

    @property
    def uuid_attr(self):
        return self.entity.uuid_attr

    @property
    def uuid_value(self):
        return self.entity.uuid_value


class ISyncSectionAdapter(ISyncUuidAdapter):
    """custom ISync adapter that prevent children sections to recurse"""

    __select__ = ISyncUuidAdapter.__select__ & is_instance("Section", "CommemoCollection")

    def build_target_put_body(self, target, done=None):
        if target.cw_etype in {"Section", "CommemoCollection"}:
            # don't recurse on children for subsections
            skip_relations = self.skipped_relations | {"children"}
            return target.cw_adapt_to("ISync").build_put_body(done, skip_relations=skip_relations)
        else:
            return super(ISyncSectionAdapter, self).build_target_put_body(target, done)


class ISyncCommemorationItemAdapter(ISyncUuidAdapter):
    """custom ISync adapter that prevent recursion on parent collection
    through ``collection_top`` relation.
    """

    __select__ = ISyncUuidAdapter.__select__ & is_instance("CommemorationItem")
    skipped_relations = ISyncUuidAdapter.skipped_relations | {"collection_top"}

    def build_put_body(self, done=None, skip_relations=None):
        r = super(ISyncCommemorationItemAdapter, self).build_put_body()
        r["collection_top"] = [
            {"uuid": self.entity.collection_top[0].uuid, "cw_etype": "CommemoCollection"}
        ]
        return r
