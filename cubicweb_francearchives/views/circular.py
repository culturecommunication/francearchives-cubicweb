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

from cubicweb.web.views.primary import PrimaryView
from cubicweb.utils import json_dumps
from cubicweb.predicates import score_entity, is_instance

from cubicweb_francearchives.views import JinjaViewMixin, get_template


class CircularTable(JinjaViewMixin, PrimaryView):
    __select__ = (
        PrimaryView.__select__
        & is_instance('Card')
        & score_entity(lambda x: x.wikiid.startswith('tableau-circulaires'))
    )
    template = get_template('circular-table.jinja2')

    def entity_call(self, entity):
        req = self._cw
        req.add_css('react-bootstrap-table-all.min.css')
        req.add_js('bundle-circular-table.js')
        rset = req.execute('''
Any X, K, DK, N, DC, C, S, DS, T, ST, CI, JSON_AGG(L)
GROUPBY X, K, DK, N, DC, C, S, DS, T, ST, CI
WHERE
  X is Circular,
  X kind K, X siaf_daf_kind DK,
  X nor N, X siaf_daf_code DC, X code C,
  X signing_date S, X siaf_daf_signing_date DS,
  X title T, X status ST, X circ_id CI,
  X business_field B, B preferred_label PL, PL label L
''')
        rows = []
        for idx, rsetrow in enumerate(rset):
            business_fields = rsetrow[-1]
            e = rset.get_entity(idx, 0)
            if e.signing_date is not None:
                date = e.signing_date.isoformat()
            elif e.siaf_daf_signing_date is not None:
                date = e.siaf_daf_signing_date.isoformat()
            else:
                date = None
            row = {
                'eid': e.eid,
                'kind': e.siaf_daf_kind,
                'code': e.siaf_daf_code or e.code or e.nor,
                'date': date,
                'title': (e.title, e.absolute_url()),
                'status': (req._(e.status), e.status),
                'business_fields': business_fields,
            }
            rows.append(row)
        self.call_template(data=json_dumps(rows), entity=entity)
