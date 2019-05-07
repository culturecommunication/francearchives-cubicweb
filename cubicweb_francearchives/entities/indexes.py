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

from cubicweb.entities import AnyEntity, fetch_config

from cubicweb_francearchives.dataimport import es_bulk_index


class ExternalUri(AnyEntity):
    __regid__ = 'ExternalUri'
    fetch_attrs, cw_fetch_order = fetch_config(['label', 'uri', 'source', 'extid'])


class AbstractIndex(AnyEntity):
    __abstract__ = True
    fetch_attrs, cw_fetch_order = fetch_config(['label', 'role'])

    def dc_title(self):
        return self.label or self.authority[0].dc_title()

    @cachedproperty
    def findingaid(self):
        return self._cw.execute(
            '(DISTINCT Any FA WHERE X index FAC, FAC finding_aid FA, X eid %(e)s)'
            ' UNION '
            '(DISTINCT Any FA WHERE X index FA, FA is FindingAid, X eid %(e)s)',
            {'e': self.eid}
        ).one()

    @property
    def authority_url(self):
        return self.authority[0].absolute_url()

    def new_authority(self):
        req = self._cw
        auth = req.create_entity(
            self.authority_type,
            label=self.label
        )
        prevauthority = self.authority[0].eid
        self.update_es_docs(prevauthority, auth.eid)
        self.cw_set(authority=auth)
        return auth

    def update_es_docs(self, oldauth, newauth):
        # update esdocument related to FAComponent,FindingAid linked to current index
        # first update postgres db
        # TODO : this probabl- must go to the cubicweb_frarchives_edition
        self._cw.system_sql('''
UPDATE
  cw_esdocument es
SET
  cw_doc = jsonb_set(
    es.cw_doc::jsonb,
    '{index_entries}',
    update_index_entries(
      es.cw_doc -> 'index_entries',
      %(oldauth)s,
      %(newauth)s
    )
  )
FROM
  ((
     SELECT fac.cw_eid
     FROM
       cw_facomponent fac
       JOIN index_relation ir ON ir.eid_to = fac.cw_eid
     WHERE ir.eid_from = %(indexeid)s
  ) UNION (
     SELECT fa.cw_eid
     FROM
       cw_findingaid fa
       JOIN index_relation ir ON ir.eid_to = fa.cw_eid
       WHERE ir.eid_from = %(indexeid)s
  )) fa
WHERE
  fa.cw_eid = es.cw_entity
        ''', {'indexeid': self.eid, 'oldauth': oldauth, 'newauth': newauth})
        # then update elasticsearch db
        indexer = self._cw.vreg['es'].select('indexer', self._cw)
        index_name = indexer.index_name
        es = indexer.get_connection()
        published_indexer = self._cw.vreg['es'].select(
            'indexer', self._cw, published=True
        )
        docs = []
        published_docs = []
        for fa in self.index:
            serializable = fa.cw_adapt_to('IFullTextIndexSerializable')
            json = serializable.serialize()
            if not json:
                continue
            docs.append({
                '_op_type': 'index',
                '_index': index_name,
                '_type': '_doc',
                '_id': serializable.es_id,
                '_source': json
            })
            if published_indexer:
                is_published = True
                if fa.cw_etype in('FindingAid', 'FAComponent'):
                    if fa.cw_etype == 'FindingAid':
                        wf = fa.cw_adapt_to('IWorkflowable')
                    else:
                        wf = fa.finding_aid[0].cw_adapt_to('IWorkflowable')
                    is_published = wf and wf.state == 'wfs_cmsobject_published'
                if is_published:
                    published_docs.append({
                        '_op_type': 'index',
                        '_index': published_indexer.index_name,
                        '_type': '_doc',
                        '_id': serializable.es_id,
                        '_source': json
                    })
            if len(docs) > 30:
                es_bulk_index(es, docs)
                if published_docs:
                    es_bulk_index(es, published_docs)
                docs = []
                published_docs = []
        es_bulk_index(es, docs)
        if published_docs:
            es_bulk_index(es, published_docs)


class AgentName(AbstractIndex):
    __regid__ = 'AgentName'
    authority_type = 'AgentAuthority'
    fetch_attrs, cw_fetch_order = fetch_config(['label', 'type', 'role'])


class Geogname(AbstractIndex):
    __regid__ = 'Geogname'
    authority_type = 'LocationAuthority'

    @property
    def type(self):
        return self.cw_etype.lower()


class Subject(AbstractIndex):
    __regid__ = 'Subject'
    authority_type = 'SubjectAuthority'

    @property
    def type(self):
        return self.cw_etype.lower()


class AbstractAuthority(AnyEntity):
    __abstract__ = True

    def dc_title(self):
        return self.label or self._cw._(u'no label')

    def rest_path(self):
        type = self.cw_etype[:-9].lower()  # remove `Authority`
        return '{}/{}'.format(type, self.eid)

    def group(self, other_auth_eids):
        req = self._cw
        grouped_with = [e.eid for e in self.reverse_grouped_with]
        grouped_auths = [self]
        for autheid in other_auth_eids:
            try:
                autheid = int(autheid)
            except Exception:
                continue
            if autheid == self.eid:
                # do not group with itself
                continue
            if autheid in grouped_with:
                # already grouped with
                continue
            auth = req.entity_from_eid(autheid)
            grouped_auths.append(auth)
            if auth.cw_etype != self.cw_etype:
                continue
            # rewrite `index_entries` in related es docs
            for index in auth.reverse_authority:
                index.update_es_docs(oldauth=auth.eid, newauth=self.eid)
            # redirect index entities from old authority to new authority
            kwargs = {'new': self.eid, 'old': autheid}
            req.execute(
                'SET I authority NEW WHERE NEW eid %(new)s, I authority OLD, OLD eid %(old)s',
                kwargs
            )
            # set the grouped_with relation from the old authority to new
            # authority
            req.execute(
                'SET OLD grouped_with NEW WHERE OLD eid %(old)s, NEW eid %(new)s',
                kwargs)
            # remove the possible grouped_with relation from the new authority
            # to the old
            req.execute(
                'DELETE NEW grouped_with OLD WHERE OLD eid %(old)s, NEW eid %(new)s',
                kwargs)
            # update all possible grouped_with subjects of the old authority
            # to the new authority
            req.execute('SET O grouped_with NEW WHERE '
                        'O grouped_with OLD, OLD eid %(old)s, NEW eid %(new)s',
                        kwargs)
        return grouped_auths

    @cachedproperty
    def same_as_refs(self):
        urls = []
        for ref in self.same_as:
            if ref.cw_etype == 'ExternalUri':
                urls.append(ref.uri)
            else:
                urls.append(ref.absolute_url())
        return urls


class LocationAuthority(AbstractAuthority):
    __regid__ = 'LocationAuthority'


class AgentAuthority(AbstractAuthority):
    __regid__ = 'AgentAuthority'


class SubjectAuthority(AbstractAuthority):
    __regid__ = 'SubjectAuthority'
