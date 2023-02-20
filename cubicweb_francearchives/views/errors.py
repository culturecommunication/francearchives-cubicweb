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
from logilab.common.decorators import cachedproperty

from cubicweb.view import StartupView
from cubicweb.web.views.error import FourOhFour

from cubicweb_francearchives.views import JinjaViewMixin, top_sections_desc, get_template


class NotFoundView(JinjaViewMixin, StartupView):
    __regid__ = "404"
    template = get_template("notfound.jinja2")

    @cachedproperty
    def xiti_chapters(self):
        return ["404", self._cw.relative_path(False)]

    def call(self):
        section_descs = []
        for title, label, name, cssclass, desc, subsections in top_sections_desc(self._cw):
            section_descs.append(
                {
                    "url": self._cw.build_url(name),
                    "cssclass": cssclass,
                    "title": self._cw._(title),
                    "label": self._cw._(label),
                }
            )
        self.call_template(
            section_descs=section_descs,
            notfound_msg=self._cw._("notfound-msg"),
            notfound_picture=self._cw.data_url("images/notfound.png"),
        )


def registration_callback(vreg):
    vreg.register_and_replace(NotFoundView, FourOhFour)
