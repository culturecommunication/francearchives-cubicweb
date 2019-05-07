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

"""cubicweb-francearchives entity's classes"""

from collections import defaultdict

from cubicweb import _

from cubes.card.entities import Card as BaseCard
from cubicweb_file.entities import File as BaseFile
from cubes.skos.entities import Concept as BaseConcept

from cubicweb_francearchives.xy import (conjunctive_graph,
                                        add_statements_to_graph, namespaces)


ETYPE_CATEGORIES = {
    'Person': _('archives'),
    'Circular': _('circulars'),
    'Service': _('services'),
    'NewsContent': _('edito'),
    'BaseContent': _('edito'),
    'ExternRef': _('edito'),
    'Section': _('edito'),
    'Map': _('edito'),
    'Card': _('edito'),
    'CommemorationItem': _('commemorations'),
    'CommemoCollection': _('commemorations'),
    'FindingAid': _('archives'),
    'FAComponent': _('archives'),
}

DOC_CATEGORY_ETYPES = defaultdict(list)
for etype, category in ETYPE_CATEGORIES.items():
    DOC_CATEGORY_ETYPES[category].append(etype)


class Concept(BaseConcept):
    uuid_attr = 'cwuri'

    @property
    def uuid_value(self):
        return self.cwuri


class Card(BaseCard):
    uuid_attr = 'wikiid'

    def rest_path(self):
        if '-' in self.wikiid:
            return self.wikiid.split('-')[0]
        return self.wikiid

    def dc_title(self):
        """override default implementation to never consider wikiid in title"""
        return self.title

    @property
    def uuid_value(self):
        return self.wikiid


def system_source_absolute_url(self, *args, **kwargs):
    """override default absolute_url to avoid calling cw_metainformation
    """
    # use *args since we don't want first argument to be "anonymous" to
    # avoid potential clash with kwargs
    if args:
        assert len(args) == 1, 'only 0 or 1 non-named-argument expected'
        method = args[0]
    else:
        method = None
    if method in (None, 'view'):
        kwargs['_restpath'] = self.rest_path(False)
    else:
        kwargs['rql'] = 'Any X WHERE X eid %s' % self.eid
    return self._cw.build_url(method, **kwargs)


def systemsource_entity(cls):
    setattr(cls, 'absolute_url', system_source_absolute_url)
    return cls


class FAFile(BaseFile):
    rest_attr = 'data_sha1hex'

    def bfss_storage_relpath(self, attr):
        content_hash = self.cw_attr_metadata(attr, 'sha1hex')
        if content_hash is None:
            content_hash = self.compute_sha1hex()
        name = self.cw_attr_metadata(attr, 'name')
        return '{}_{}'.format(content_hash, name)

    def absolute_url(self):
        idownloadable = self.cw_adapt_to('IDownloadable')
        return idownloadable.download_url()

    def rest_path(self):
        etype = str(self.e_schema)
        path = etype.lower()
        hash = self.data_sha1hex or self.compute_sha1hex()
        return u'%s/%s' % (path, self._cw.url_quote(hash))


def entity2schemaorg(entity):
    sorg = entity.cw_adapt_to('rdf.schemaorg')
    if sorg is not None:
        graph = conjunctive_graph()
        add_statements_to_graph(graph, sorg)
        return graph.serialize(format='json-ld',
                               context=namespaces,
                               indent=2)
    return None


def entity2meta(entity):
    meta = entity.cw_adapt_to('IMeta')
    if meta is not None:
        return meta.meta_data()
    return ()


def entity2opengraph(entity):
    og = entity.cw_adapt_to('IOpenGraph')
    if og is not None:
        return og.og_data()
    return ()
