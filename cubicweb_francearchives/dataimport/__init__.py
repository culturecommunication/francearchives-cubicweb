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
import time
import logging
import string
import csv
import hashlib
import os.path as osp
from datetime import datetime
from contextlib import contextmanager

from six.moves import range as xrange
from six import unichr, text_type

from lxml import etree

from logilab.common.textutils import unormalize
from logilab.common.decorators import cachedproperty

from elasticsearch.exceptions import ConnectionTimeout, SerializationError
from elasticsearch import helpers as es_helpers

from cubicweb import Binary
from cubicweb.dataimport.importer import ExtEntity, ExtEntitiesImporter
from cubicweb.devtools.fake import FakeRequest

from cubicweb_francearchives.dataimport.meminfo import memprint
from cubicweb_francearchives.utils import remove_html_tags
from cubicweb_francearchives.utils import pick
from cubicweb_francearchives import Authkey

LOGGER = logging.getLogger()


RELFILES_DIR = 'RELFILES'

OAIPMH_DC_PATH = 'oaipmh/dc'
OAIPMH_EAD_PATH = 'oaipmh/ead'

NO_PUNCT_MAP = dict.fromkeys(ord(c) for c in string.punctuation)


def _build_transmap():
    transmap = {}
    for i in xrange(2 ** 16 - 1):
        newc = unormalize(unichr(i), substitute='_')
        if len(newc) == 1:
            transmap[i] = ord(newc)
        else:
            transmap[i] = newc
    return transmap


TRANSMAP = _build_transmap()


def es_bulk_index(es, es_docs, max_retry=3, **kwargs):
    if not es:
        return
    numtry = 0
    while numtry < max_retry:
        try:
            es_helpers.bulk(es, es_docs, stats_only=True, **kwargs)
        except (ConnectionTimeout, SerializationError):
            LOGGER.warning('failed to bulk index in ES, will retry in 0.5sec')
            numtry += 1
            time.sleep(0.5)
        else:
            break


def log_in_db(func):
    logger = logging.getLogger('francearchives.dataimport')

    def wrapped(cnx, *args, **kwargs):
        # cnx is an internal_cnx
        if isinstance(cnx, FakeRequest):
            # Skip logging for test
            return func(cnx, *args, **kwargs)
        log_cmd_in_db(cnx, func.__name__, logger)
        res = func(cnx, *args, **kwargs)
        log_cmd_in_db(cnx, func.__name__, logger, stop=True)
        return res

    return wrapped


def log_cmd_in_db(cnx, cmd_name, logger=None, stop=False):
    try:
        sqlcnx = cnx.repo.system_source.get_connection()
        crs = sqlcnx.cursor()
        if stop:
            crs.execute('SELECT start FROM executed_command '
                        'WHERE name=%(cmd_name)s '
                        'ORDER BY start DESC', {'cmd_name': cmd_name})
            start = crs.fetchone()
            if not start and logger:
                logger.warning('no command with name "%s" in db log' % cmd_name)
                return
            crs.execute('UPDATE executed_command '
                        'SET stop=%(stop)s, memory=%(mem)s '
                        'WHERE name=%(cmdname)s AND start=%(start)s;',
                        {'stop': datetime.utcnow(),
                         'start': start[0],
                         'cmdname': cmd_name,
                         'mem': memprint(logger=logger)})
        else:
            crs.execute('INSERT INTO executed_command (name) '
                        'VALUES (%(cmd_name)s);', {'cmd_name': cmd_name})
        sqlcnx.commit()
    except Exception:
        import traceback
        traceback.print_exc()
        if logger:
            logger.exception('error when inserting log on command')
        raise


def normalize_entry(entry):
    entry = re.sub(r'\(\s*[\d.]+\s*-\s*[\d.]+\s*\)', '', entry)
    if isinstance(entry, str):
        entry = entry.translate(None, string.punctuation)
    else:  # unicode
        entry = entry.translate(NO_PUNCT_MAP).translate(TRANSMAP)
    entry = entry.lower()
    return u' '.join(sorted(entry.split()))


def remove_extension(identifier):
    basename, ext = osp.splitext(identifier)
    if ext in {'.pdf', '.csv', '.xml'}:
        return basename
    return identifier


class IndexImporterMixin(object):
    type_map = {
        'persname': ('AgentName', 'AgentAuthority'),
        'corpname': ('AgentName', 'AgentAuthority'),
        'name': ('AgentName', 'AgentAuthority'),
        'famname': ('AgentName', 'AgentAuthority'),
        'geogname': ('Geogname', 'LocationAuthority'),
        'subject': ('Subject', 'SubjectAuthority'),
    }

    def __init__(self, *args, **kwargs):
        self.indices = {}
        self._current_service = None
        self.all_authorities = {}
        super(IndexImporterMixin, self).__init__(*args, **kwargs)

    @cachedproperty
    def concepts(self):
        return {
            label.lower(): eid
            for label, eid in self.store.rql(
                'Any LL, X WHERE X is Concept, L label_of X, L label LL'
            )
        }

    def _init_auth_history(self):
        self.auth_history = {}
        sql = self.store._cnx.system_sql
        cu = sql('select fa_stable_id, type, label, indexrole, autheid from authority_history')
        for fa_stable_id, type, label, indexrole, auth in cu.fetchall():
            key = Authkey(fa_stable_id, type, label, indexrole)
            self.auth_history[key.as_tuple()] = auth

    def _init_authorities(self):
        autodedupe_authorities = self.index_policy.get('autodedupe_authorities')
        if not autodedupe_authorities:
            self.global_authorities = {}
            return
        global_or_service, should_normalize = autodedupe_authorities.split('/')
        assert global_or_service in ('global', 'service')
        assert should_normalize in ('strict', 'normalize')
        if should_normalize == 'normalize':
            label = 'NORMALIZE_ENTRY(L)'
        else:
            label = 'L'
        if global_or_service == 'global':
            rql = '''
                 DISTINCT Any A, L, T, S WITH A, L, T, S BEING (
                   (DISTINCT Any A, {label}, T, NULL WHERE
                       A is ET, ET name T,
                       A is in (SubjectAuthority, LocationAuthority, AgentAuthority),
                       NOT EXISTS(A grouped_with A1), A label L)
                   UNION
                   (DISTINCT Any A, {label}, T, NULL WHERE
                       GA is ET, ET name T,
                       A is in (SubjectAuthority, LocationAuthority, AgentAuthority),
                       GA grouped_with A, GA label L)
            )
            '''
        else:
            # 1. orphan authorities
            #    this fist query is a built UNION instead of basic rql query like:
            #       Any A WHERE A is IN (AgentAuthority, LocationAuthority, SubjectAuthority), NOT
            #       EXISTS(I authority A)
            #    because of bug in rql2sql (not so easy to reproduce in unit test)
            #
            #   eliminate grouped authorities
            rql = ' UNION '.join(
                '(Any A, {{label}}, "{0}", 0 WHERE A is {0}, A label L, '
                'NOT EXISTS(I authority A), NOT EXISTS(A grouped_with A1))'.format(auth)
                for auth in ('AgentAuthority', 'LocationAuthority', 'SubjectAuthority')
            )
            # add grouped authorities targets with source authority's label
            rql += ' UNION ' + 'UNION '.join(
                '(Any A, {{label}}, "{0}", 0 WHERE A is {0}, GA label L, '
                'GA grouped_with A, NOT EXISTS(I authority A))'.format(auth)
                for auth in ('AgentAuthority', 'LocationAuthority', 'SubjectAuthority')
            )
            rql = 'DISTINCT Any A, L, T, S WITH A, L, T, S BEING ({0})'.format(rql)
        execute = self.store._cnx.execute
        # `all_authorities` is first initialize as global_authorities then we will call
        # `update_authorities_cache` to update `all_authorities`
        self.all_authorities = self.global_authorities = {
            hash((t, l, s)): a
            for a, l, t, s in execute(rql.format(label=label), build_descr=False)
        }

    def update_authorities_cache(self, service_eid):
        """ This will update `all_authorities` attribute.

        To perform this update we use authorities linked to service (one
        with `service_eid`) through FindingAid or through FAComponent via FindingAid
        """
        if self._current_service == service_eid:
            return self.all_authorities
        self._current_service = service_eid
        autodedupe_authorities = self.index_policy.get('autodedupe_authorities')
        if not autodedupe_authorities:
            return
        global_or_service, should_normalize = autodedupe_authorities.split('/')
        if global_or_service == 'global':
            return
        if should_normalize == 'normalize':
            label = 'NORMALIZE_ENTRY(a.cw_label)'
        else:
            label = 'a.cw_label'
        template = '''
        SELECT DISTINCT a.cw_eid, {label}, '{etype}'
        FROM
          {authtable} a
          JOIN {indextable} it ON it.cw_authority = a.cw_eid
          JOIN index_relation i ON i.eid_from = it.cw_eid
          JOIN cw_findingaid fa ON fa.cw_eid = i.eid_to
        WHERE fa.cw_service = %(s)s
        UNION
        SELECT DISTINCT a.cw_eid, {label}, '{etype}'
        FROM
          {authtable} a
          JOIN {indextable} it ON it.cw_authority = a.cw_eid
          JOIN index_relation i ON i.eid_from = it.cw_eid
          JOIN cw_facomponent fac ON fac.cw_eid = i.eid_to
          JOIN cw_findingaid fa ON fa.cw_eid = fac.cw_finding_aid
        WHERE fa.cw_service = %(s)s
        UNION
        SELECT DISTINCT a.cw_eid, a1.cw_label, '{etype}'
        FROM
           {authtable} a
           JOIN grouped_with_relation ga ON a.cw_eid=ga.eid_to
           JOIN {authtable} a1 ON a1.cw_eid = ga.eid_from
           JOIN {indextable} it ON it.cw_authority = a.cw_eid
           JOIN index_relation i ON i.eid_from = it.cw_eid
           JOIN cw_findingaid fa ON fa.cw_eid = i.eid_to
        WHERE fa.cw_service = %(s)s
        UNION
        SELECT DISTINCT a.cw_eid, a1.cw_label, '{etype}'
        FROM
          {authtable} a
          JOIN grouped_with_relation ga ON a.cw_eid=ga.eid_to
          JOIN {authtable} a1 ON a1.cw_eid = ga.eid_from
          JOIN {indextable} it ON it.cw_authority = a.cw_eid
          JOIN index_relation i ON i.eid_from = it.cw_eid
          JOIN cw_facomponent fac ON fac.cw_eid = i.eid_to
          JOIN cw_findingaid fa ON fa.cw_eid = fac.cw_finding_aid
        WHERE fa.cw_service = %(s)s
         '''
        q = ' union '.join(
            template.format(etype=e, authtable=at, indextable=it, label=label)
            for e, at, it in (
                ('LocationAuthority', 'cw_locationauthority', 'cw_geogname'),
                ('SubjectAuthority', 'cw_subjectauthority', 'cw_subject'),
                ('AgentAuthority', 'cw_agentauthority', 'cw_agentname'),
            )) + ' union ' + \
            '''
            SELECT DISTINCT a.cw_eid, {label}, 'AgentAuthority'
            FROM
              cw_agentauthority a
              JOIN cw_person p ON p.cw_authority = a.cw_eid
            WHERE
              p.cw_service = %(s)s
            UNION
            SELECT DISTINCT a.cw_eid, a1.cw_label, 'AgentAuthority'
            FROM
              cw_agentauthority a
              JOIN grouped_with_relation ga ON a.cw_eid=ga.eid_to
              JOIN cw_agentauthority a1 ON a1.cw_eid = ga.eid_from
              JOIN cw_person p ON p.cw_authority = a.cw_eid
            WHERE
              p.cw_service = %(s)s
        '''.format(label=label)
        self.all_authorities = self.global_authorities.copy()
        sql = self.store._cnx.system_sql
        self.log.info('start fetching authorities for service with eid %s', service_eid)
        for autheid, authlabel, authtype in sql(q, {'s': service_eid}).fetchall():
            self.all_authorities[hash((authtype, authlabel, service_eid))] = autheid
        self.log.info('end fetching authorities %s', service_eid)

    def create_authority(self, authtype, indextype, label, service, hist_key):
        if hist_key.as_tuple() in self.auth_history:
            return self.auth_history[hist_key.as_tuple()]
        keys = self.build_authority_key(authtype, label, service)
        for key in keys:
            if key in self.all_authorities:
                return self.all_authorities[key]
        key = keys[0]  # preferred key is in first position
        self.all_authorities[key] = \
            self.global_authorities[key] = \
            auth = self.create_entity(authtype, {'label': label})['eid']
        return auth

    def build_authority_key(self, authtype, label, service):
        autodedupe_authorities = self.index_policy.get('autodedupe_authorities')
        if not autodedupe_authorities or autodedupe_authorities == 'service/strict':
            keys = [
                (authtype, label, service),
                # in service case we should also try to align on orphan authorities
                (authtype, label, 0),
            ]
        elif autodedupe_authorities == 'service/normalize':
            keys = [
                (authtype, normalize_entry(label), service),
                # in service case we should also try to align on orphan authorities
                (authtype, normalize_entry(label), 0),
            ]
        elif autodedupe_authorities == 'global/normalize':
            keys = [(authtype, normalize_entry(label), None)]
        elif autodedupe_authorities == 'global/strict':
            keys = [(authtype, label, None)]
        return [hash(key) for key in keys]

    def create_index(self, infos, target, fa_attrs):
        # key will be fields for Geogname, AgentName, Subject entities
        # and values are set of targets that will be index relations
        key = Authkey(
            fa_attrs['stable_id'],
            infos['type'],
            infos['label'],
            infos['role']
        )
        if key.as_tuple() not in self.indices:
            indextype, authtype = self.type_map[infos['type']]
            autheid = self.create_authority(authtype, infos['type'], infos['label'],
                                            fa_attrs.get('service'),
                                            hist_key=key)
            attrs = dict(pick(infos, 'role', 'label'), authority=autheid)
            if indextype == 'AgentName':
                attrs['type'] = infos['type']
            indexeid = self.create_entity(indextype, attrs)['eid']
            self.indices[key.as_tuple()] = indexeid, autheid
        else:
            indexeid, autheid = self.indices[key.as_tuple()]
        self.add_rel(indexeid, 'index', target)
        # same_as
        authfilenumber = infos['authfilenumber']
        if authfilenumber is not None:
            authinfos = self.authority_records.get(authfilenumber)
            if authinfos:
                self.add_rel(autheid, 'same_as', authinfos['eid'])
        if infos['type'] == 'subject':
            concept = self.concepts.get(infos['label'].lower())
            if concept is not None:
                self.add_rel(autheid, 'same_as', concept)
        # add authority link to infos for elasticsearch
        infos['authority'] = autheid


def first(values):
    if values:
        return next(iter(values))
    return None


def int_or_none(value):
    if isinstance(value, int):
        return value
    if value is None:
        return None
    value = value.strip()
    if value.isdigit():
        return int(value)
    return None


def clean_row(row):
    for key, value in row.items():
        if isinstance(value, str):
            row[key] = value.decode('utf-8').strip()
        row[key.lower().strip()] = row.pop(key)
    return row


class CSVIntegrityError(Exception):
    pass


def load_metadata_file(filename):
    """ expected columns are:
    ['identifiant_URI', 'date1' 'date2',
    'description', 'format', 'langue', 'index_collectivite',
    'index_lieu', 'conditions_acces', 'index_personne', 'origine',
    'conditions_utilisation', 'identifiant_fichier',
    'source_complementaire', 'titre', 'type', 'source_image', 'index_matiere']
    """
    all_metadata = {}
    csv_empty_value = 'Missing required value for column "{col}", row "{row}"'
    csv_missing_col = 'The required column "{col}" is missing'
    mandatory_columns = ('identifiant_fichier', 'titre')
    errors = []
    with open(filename) as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i == 0:
                errors.extend([csv_missing_col.format(col=col)
                               for col in mandatory_columns
                               if col not in row])
                if errors:
                    break
            errors.extend([csv_empty_value.format(row=i, col=col)
                           for col in mandatory_columns
                           if not row[col]])
            if not errors:
                row = clean_row(row)
                for indextype in ('index_matiere', 'index_collectivite',
                                  'index_personne', 'index_lieu'):
                    row[indextype] = [s.strip() for s in row[indextype].split(';')]
                all_metadata[row['identifiant_fichier'].strip()] = row
    if errors:
        raise CSVIntegrityError(' ;\n '.join(errors))
    return all_metadata


class FileExtEntity(ExtEntity):
    """Extend default ExtEntity class to bypass the auto-binary wrapping"""

    def prepare(self, *args, **kwargs):
        deferred = super(FileExtEntity, self).prepare(*args, **kwargs)
        # If we're using FileExtEntity, we don't want Binary instances, just
        # the plain string (which is supposed to a be a filepath)
        for key, value in self.values.items():
            if isinstance(value, Binary):
                self.values[key] = value.getvalue()
        return deferred


class ExtentityWithIndexImporter(IndexImporterMixin, ExtEntitiesImporter):
    """'Optimized' (CPU-wise, not memory-wise) importer

    Default importer stores "non-ready" entites in a queue
    and loops on the queue each time a new entity is added
    to see if some entities in the loop might now be ready.

    In our case, this is not a good idea since we end up looping
    and looping over manif programs (or any other non-ready
    entity). Instead, just enqueue any non-ready entity and flush
    the queue at the end. This will lead to higher memory consumption
    but will be _a lot_ faster.
    """

    def __init__(self, schema, store, extid2eid=None, existing_relations=None,
                 etypes_order_hint=(), import_log=None, raise_on_error=False,
                 index_policy=None, log=None):
        if log is None:
            self.log = LOGGER
        self.index_policy = index_policy
        # XXX, redundant with ExtEntitiesImporter's __init__ but required by
        # `_init_authorities()`
        self.store = store
        self._init_authorities()
        self._init_auth_history()
        if extid2eid is None:
            extid2eid = {}
        super(ExtentityWithIndexImporter, self).__init__(
            schema, store, extid2eid, existing_relations, etypes_order_hint,
            import_log, raise_on_error)
        service_extids = [v for k, v in extid2eid.items() if k.startswith('service-')]
        service_eid = None
        if service_extids:
            service_eid = service_extids.pop()
        self.update_authorities_cache(service_eid)
        extid2eid.update(self.all_authorities)

    def iter_ext_entities(self, ext_entities, deferred, queue):
        """override default importer method to process queue
        once and for all at the end
        """
        schema = self.schema
        extid2eid = self.extid2eid
        for ext_entity in ext_entities:
            # check data in the transitional representation and prepare it
            # for later insertion in the database
            for subj_uri, rtype, obj_uri in ext_entity.prepare(schema):
                deferred.setdefault(rtype, set()).add((subj_uri, obj_uri))
            if not ext_entity.is_ready(extid2eid):
                queue.setdefault(ext_entity.etype, []).append(ext_entity)
                continue
            yield ext_entity
        # all ready entities have been imported, now flush the queue
        for ext_entity in self.process_deferred_queue(queue):
            yield ext_entity

    def process_deferred_queue(self, queue):
        extid2eid = self.extid2eid
        order_hint = list(self.etypes_order_hint)
        # check for some entities in the queue that may now be ready. We'll have to restart
        # search for ready entities until no one is generated
        for etype in queue:
            if etype not in order_hint:
                order_hint.append(etype)
        new = True
        while new:
            new = False
            for etype in order_hint:
                if etype in queue:
                    new_queue = []
                    for ext_entity in queue[etype]:
                        if ext_entity.is_ready(extid2eid):
                            yield ext_entity
                            # may unlock entity previously handled within this loop
                            new = True
                        else:
                            new_queue.append(ext_entity)
                    if new_queue:
                        queue[etype][:] = new_queue
                    else:
                        del queue[etype]

    def complete_extentities(self, extentities):
        """process the `extentities` flow and add missing `AgentAuthority`.

        When importing nomina entities, only ``Person`` extentities are
        created, leaving the responsibility to get / create corresponding
        ``AgentAuthority`` to the extentity importer.
        """
        for e in extentities:
            if e.etype == 'Person':
                label = u' '.join([first(e.values['name']) or u'',
                                   first(e.values['forenames'])])
                authority_hist_key = (
                    u'xxx-no-stable-id-for-person-xxx',
                    'AgentAuthority',
                    label
                )
                if authority_hist_key in self.auth_history:
                    e.values['authority'] = {self.auth_history[authority_hist_key]}  # XXX
                else:
                    service_extid = first(e.values['service'])
                    service_eid = int(service_extid.split('-')[1])
                    keys = self.build_authority_key('AgentAuthority', label, service_eid)
                    for key in keys:
                        if key in self.all_authorities:
                            e.values['authority'] = {key}
                            break
                    else:
                        key = keys[0]
                        ext = ExtEntity('AgentAuthority', key, {'label': {label}})
                        e.values['authority'] = {key}
                        self.all_authorities[key] = ext.extid
                        yield ext
            yield e

    def import_entities(self, extentities):
        super(ExtentityWithIndexImporter, self).import_entities(
            self.complete_extentities(extentities)
        )


def create_ead_index_table(cnx):
    cnx.system_sql('DROP TABLE IF EXISTS dataimport_ead_index')
    cnx.system_sql('''CREATE TABLE dataimport_ead_index (
id serial,
index_type varchar(16),
label varchar(256),
role varchar(64),
targets integer[],
authority_eid integer
    )''')


@contextmanager
def sqlcursor(cnx, logger=LOGGER):
    try:
        yield cnx.cnxset.cu
    except Exception:
        logger.exception('SQL execution failed')
        cnx.rollback()
    else:
        cnx.commit()


def execute_sqlscript(cnx, script_path):
    with open(script_path) as f:
        sql = f.read()
    with sqlcursor(cnx) as crs:
        crs.execute(sql)


def strip_html(html):
    """Strip HTML tags from string"""
    if html is None:
        return None
    try:
        # Etree does not like HTML without a single root element
        # so we need to wrap it inside a div.
        tree = etree.fromstring(u'<div>{}</div>'.format(html))
    except etree.XMLSyntaxError:
        return html.strip()
    return ' '.join(tree.xpath('//text()')).strip()


def strip_nones(props, defaults=None):
    if defaults is None:
        defaults = {}
    for key, value in props.items():
        if isinstance(value, str):
            value = value.decode('utf-8')
        if value is not None and isinstance(value, text_type):
            value = value.strip() if value else None
            if not value:
                value = None
            if value is not None and not remove_html_tags(value).strip():
                value = None
        if value is None:
            if key in defaults:
                props[key] = defaults[key]
            else:
                del props[key]
    return props


def clean_values(values):
    """clean `values` attributes dict
    - convert str to unicode
    - ignore None attributes
    """
    formatted = {}
    for key, value in values.items():
        if isinstance(value, str):
            value = value.decode('utf-8')
        formatted[key] = value
    return strip_nones(formatted)


def usha1(content):
    if isinstance(content, text_type):
        content = content.encode('utf-8')
    return text_type(hashlib.sha1(content).hexdigest())


YEAR_RE = re.compile('[0-9]{4}')


def get_year(date):
    """Extract a year from a string representing a date
    """
    if not date:
        return
    year = YEAR_RE.findall(date)
    if year:
        return year[0]


def get_date(start, stop):
    chunks = []
    if start:
        chunks.append(start)
    if stop and stop != start:
        chunks.append(stop)
    if chunks:
        return u' - '.join(chunks)
    return None


def default_csv_metadata(title):
    return {'identifiant_fichier': title,  # ead
            'titre': title,
            'origine': title.split('_')[0],
            'index_matiere': None,
            'description': None,
            'index_personne': None,
            'index_collectivite': None,
            'startyear': None,
            'stopyear': None,
            'year': None,
            'type': None,
            'format': None,
            'langue': None,
            'source_complementaire': None,
            'index_lieu': None,
            'conditions_acces': None,
            'conditions_utilisation': None,
            'identifiant_uri': None,  # dao
            }


def facomponent_stable_id(identifier, fa_stable_id):
    if isinstance(identifier, text_type):
        identifier = identifier.encode('utf-8')
    return hashlib.sha1('{}{}'.format(
        fa_stable_id, identifier)).hexdigest()