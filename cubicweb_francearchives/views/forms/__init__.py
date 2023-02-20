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

import re

from cwtags import tag as T

from cubicweb.view import StartupView
from cubicweb.web.views.formrenderers import FormRenderer

from cubicweb_francearchives.utils import find_card

EMAIL_REGEX = re.compile(r"[^@|\s]+@[^@|\s]+\.[^@|\s]+")


class AbstractStaticFormView(StartupView):
    __abstract__ = True

    def call(self, **kwargs):
        submitted_values = self._cw.form.get("_ctrl")
        card = find_card(self._cw, self.__regid__)
        if card is not None:
            self.wview("primary", entity=card)
        form = self._cw.vreg["forms"].select(self.__regid__, self._cw)
        form.render(w=self.w, display_progress_div=False, submitted=submitted_values)


class AbstractPniaStaticFormRenderer(FormRenderer):
    __abstract__ = True

    def render_content(self, w, form, values):
        """pnia customization: rgaa remove useless fieldset without label"""
        if self.display_progress_div:
            w('<div id="progress">%s</div>' % self._cw._("validating..."))
        with T.div(w, klass="document-view"):
            self.render_fields(w, form, values)
            self.render_buttons(w, form)

    def render_fields(self, w, form, values):
        form.ctl_errors = {}
        submitted = values.get("submitted")
        if submitted:
            msg = submitted.get("msg")
            errors = submitted.get("errors", {})
            form.ctl_errors = errors
            if msg:
                klass = "alert alert-danger" if errors else "alert alert-success"
                w(T.div(msg, klass=klass))
        super(AbstractPniaStaticFormRenderer, self).render_fields(w, form, values)

    def _render_fields(self, fields, w, form):
        ctx = self.template_attrs()
        ctx["action"] = form.form_action()
        ctx.update(self.process_errors(form))
        for field in fields:
            value = self._cw.form.get(field.name, "")
            ctx["%s_value" % field.name] = value
        w(self.template.render(ctx))

    def error_message(self, form):
        return ""

    def process_errors(self, form):
        processed = {}
        _ = self._cw._
        for key, value in form.ctl_errors.items():
            if form.field_by_name(key).required:
                processed["contact_%s_error" % key] = _(value)
        return processed
