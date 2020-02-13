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

from cwtags import tag as T

from logilab.mtconverter import xml_escape

from cubicweb.view import EntityView
from cubicweb.predicates import is_instance
from cubicweb.web.component import EntityCtxComponent
from cubicweb_francearchives.utils import cut_words


class TreeOnelineView(EntityView):
    __select__ = EntityView.__select__ & is_instance("FindingAid", "FAComponent")
    __regid__ = "tree-oneline"

    def cell_call(self, row, col, selected, _class):
        entity = self.cw_rset.get_entity(row, col)
        w = self.w
        with T.div(w, Class=_class):
            full_title = entity.dc_title()
            title = cut_words(full_title, 230)
            if entity.eid == selected:
                w(T.span(xml_escape(title), Class="detailed-path-list-item-active"))
            else:
                kwargs = {"href": xml_escape(entity.absolute_url())}
                if title != full_title:
                    kwargs["title"] = xml_escape(full_title)
                with T.a(w, **kwargs):
                    w(xml_escape(title))


class AbstractFindingAidTreeComponent(EntityCtxComponent):
    __abstract__ = True
    __regid__ = "findinaid.tree"
    context = "related-top-main-content"
    order = 1

    def render(self, w, view=None):
        self.render_content(w)

    def tree_items(self, entity):
        raise NotImplementedError

    def display_service_link(self, entity, w):
        service = entity.related_service
        if service:
            service_label = service.dc_title()
            tooltip = self._cw._("Search all documents for publisher %s") % service_label
            w(
                '<a title="{}" href="{}">{}</a>'.format(
                    xml_escape(tooltip),
                    xml_escape(service.documents_url()),
                    xml_escape(service_label),
                )
            )
        else:
            w(entity.publisher)

    def render_content(self, w):
        entity = self.cw_rset.get_entity(0, 0)
        tree_items = self.tree_items(entity)
        if tree_items:
            with T.section(w, id="detailed-path"):
                with T.div(w, Class="detailed-path-root-level"):
                    with T.div(w, Class="row"):
                        with T.div(w, Class="col-md-1"):
                            w(T.span(Class="detailed-path-root-picto"))
                        with T.div(w, Class="col-md-11"):
                            self.display_service_link(entity, w)
                with T.div(w, Class="detailed-path-inner-levels"):
                    self.render_tree(w, entity, tree_items)
            w(T.div(Class="clearfix"))

    def render_tree(self, w, entity, tree_items):
        with T.ul(w, Class="detailed-path-list"):
            with T.li(w):
                w(
                    entity.view(
                        "tree-oneline", selected=entity.eid, _class="detailed-path-list-item-last"
                    )
                )
                with T.ul(w, Class="detailed-path-list"):
                    tree_items = list(tree_items)
                    total = len(tree_items)
                    item_class = "detailed-path-list-item"
                    for i, item in enumerate(tree_items, 1):
                        _class = "detailed-path-list-item-last" if total == i else item_class
                        with T.li(w):
                            # XXX FIXE here is only one level present
                            w(item.view("tree-oneline", selected=entity.eid, _class=_class))


class FindingAidTreeComponent(AbstractFindingAidTreeComponent):
    __select__ = is_instance("FindingAid")

    def tree_items(self, entity):
        return self._cw.execute(
            "Any C,CI,D,DT,DI,DS,DSF "
            "ORDERBY CO "
            "WHERE X top_components C, X eid %(x)s, "
            "C stable_id CI, C did D, D unittitle DT, "
            "D unitid DI, C description DS, "
            "C description_format DSF, C component_order CO",
            {"x": entity.eid},
        ).entities()


class FAComponentTreeComponent(AbstractFindingAidTreeComponent):
    __select__ = is_instance("FAComponent")
    order = 1

    def tree_items(self, entity):
        finding_aid = entity.finding_aid[0]
        component_chain = []
        children = entity.reverse_parent_component
        if children:
            component_chain.insert(0, children)
        component_chain.insert(0, [entity])
        parent = entity.parent_component
        while parent:
            component_chain.insert(0, parent)
            parent = parent[0].parent_component
        component_chain.insert(0, [finding_aid])
        return component_chain

    def render_tree(self, w, entity, tree_items, level=1):
        with T.ul(w, Class="detailed-path-list"):
            total = len(tree_items[0])
            for i, _entity in enumerate(tree_items[0], 1):
                with T.li(w):
                    _class = (
                        "detailed-path-list-item-last" if total == i else "detailed-path-list-item"
                    )
                    w(_entity.view("tree-oneline", selected=entity.eid, _class=_class))
            if len(tree_items) > 1:
                with T.li(w):
                    self.render_tree(w, entity, tree_items[1:], level + 1)
