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
from __future__ import print_function
import glob
import logging
import os
import os.path as osp
import re
from itertools import chain
import multiprocessing as mp
from uuid import uuid4
import mimetypes
from copy import deepcopy

from six import text_type as unicode

from glamconv.cli.commands import ead2_to_ape

import json

from logilab.mtconverter import xml_escape

from cubicweb.utils import json_dumps
from cubicweb.dataimport.stores import RQLObjectStore

from cubicweb_francearchives import admincnx, init_bfss
from cubicweb_francearchives.utils import merge_dicts, pick
from cubicweb_francearchives.entities import ETYPE_CATEGORIES
from cubicweb_francearchives.dataimport import (IndexImporterMixin, pdf,
                                                load_metadata_file,
                                                default_csv_metadata,
                                                strip_html,
                                                es_bulk_index, log_in_db,
                                                create_ead_index_table,
                                                strip_nones,
                                                get_year, clean_values,
                                                normalize_entry, remove_extension,
                                                sqlutil, usha1, RELFILES_DIR,
                                                OAIPMH_DC_PATH, OAIPMH_EAD_PATH)
from cubicweb_francearchives.dataimport.stores import create_massive_store
from cubicweb_francearchives.dataimport.sqlutil import delete_from_filename
from cubicweb_francearchives.dataimport.eadreader import (
    EADXMLReader, preprocess_ead, unique_indices)
from cubicweb_francearchives.dataimport.ape_ead import register_ead_actions


LOGGER = logging.getLogger()

IGNORED_NODES = frozenset(['altformavail', 'arc', 'archdescgrp',
                           'bibseries', 'blockquote',
                           'chronitem', 'chronlist'])

RAVEN_CLIENT = {}

IN_RELFILES_RE = re.compile(r'(.*)/{}/(.*)'.format(RELFILES_DIR))


def file_from_oaipmh(filepath):
    return (OAIPMH_DC_PATH in filepath
            or OAIPMH_EAD_PATH in filepath)


def ead2_to_ape_settings():
    """load default ead2 -> ape transformation settings"""
    settings_filepath = osp.join(osp.dirname(__file__),
                                 'francearchives-ead2-to-ape-settings.json')
    with open(settings_filepath) as inputf:
        return json.load(inputf)


def transform_ape_ead_file(fa_url, tree, ape_filepath):
    register_ead_actions()
    settings = ead2_to_ape_settings()
    for step in settings['steps']:
        if step['id'] == 'francearchives-eadid-transformer':
            step['params']['eadid_url'] = fa_url
    ead2_to_ape(deepcopy(tree), ape_filepath,
                settings=settings)


def generate_ape_ead_file_from_xml(cnx, tree, service_infos,
                                   fa_stable_id, ape_filepath):
    fa_url = u'{}/findingaid/{}'.format(
        cnx.vreg.config.get('consultation-base-url'),
        fa_stable_id)
    transform_ape_ead_file(fa_url, tree, ape_filepath)


def capture_exception(config, filepath):
    if config.get('sentry-dsn'):
        extra = {
            'filepath': filepath
        }
        ident = RAVEN_CLIENT['default'].captureException(extra=extra)
        msg = "Exception caught; reference is %s" % ident
        LOGGER.error(msg)


def init_sentry_client(config):
    sentry_dsn = config.get('sentry-dsn')
    if sentry_dsn:
        from raven import Client
        from raven.transport.http import HTTPTransport
        RAVEN_CLIENT['default'] = Client(sentry_dsn, transport=HTTPTransport)


ES_INDICES_LIMIT = 10000


def year_value(year, ignore_3_digits=False):
    if year is None:
        return None
    if ignore_3_digits and year < 1000:
        # hack to avoid noise from AN
        return None
    if year >= 10000:  # bad formatted date / date range in the finding aid
        return int(str(year)[:4])
    if year < 2050:
        return year
    return None  # very suspcious date, ignore it


def load_services_map(cnx):
    services = {}
    rset = cnx.execute(
        'Any X, C, N, N2, SN WHERE X is Service, '
        'X code C, X name N, X name2 N2, X short_name SN')
    for service in rset.entities():
        code = service.code
        if code is not None:
            code = code.upper()
        services[code] = service
    return services


def component_stable_id(fa_id, comp_path):
    return usha1('{}{}'.format(fa_id, '-'.join(str(i) for i in comp_path)))


def readerconfig(cwconfig, appid, esonly, nodrop=False, **kwargs):
    config = {
        'base-url': cwconfig['base-url'],
        'index-name': cwconfig['index-name'],
        'sentry-dsn': cwconfig.get('sentry-dsn'),
        'appid': appid,
        'elasticsearch-locations': cwconfig['elasticsearch-locations'],
        'esonly': esonly,
        'appfiles-dir': cwconfig['appfiles-dir'],
        'nodrop': nodrop,
        'force_delete': False,
        # compare authorities grouped by service without calling normalize_entry
        'autodedupe_authorities': 'service/strict',
        # should we push es documents into elasticsearch index
        'noes': False,
    }
    config.update(kwargs)
    return config


def decode_filepath(filepath):
    if isinstance(filepath, unicode):
        return filepath
    try:
        return filepath.decode('utf-8')
    except UnicodeDecodeError:
        return filepath.decode('iso-8859-15')


def findingaid_eids(cnx, fa_stable_id):
    return dict(cnx.execute(
        '(Any S,X WHERE X is FindingAid, X stable_id %(id)s, X stable_id S)'
        ' UNION '
        '(Any S,X WHERE F stable_id %(id)s, X finding_aid F, X stable_id S)',
        {'id': fa_stable_id}
    ))


def compute_ape_relpath(filepath_or_eadid, service_infos=None):
    basename = osp.basename(filepath_or_eadid)
    if not basename.endswith('.xml'):
        # can happen when basename comes from the <eadid> tag content
        basename += '.xml'
    publisher_code = None
    if service_infos is not None:
        publisher_code = service_infos.get('code')
    if publisher_code is None:
        publisher_code = basename.split('_', 1)[0]
    # make sure relpath will be an str
    if isinstance(basename, unicode):
        basename = basename.encode('utf-8', 'replace')
    # XXX make sure to provide a different basename than the original EAD file
    # or else the importer will believe the file has already been imported.
    return 'ape-ead/{}/ape-{}'.format(publisher_code, basename)


def get_basepath(filepath):
    ufilepath = osp.abspath(decode_filepath(filepath))
    return osp.basename(ufilepath)


class MetadataReaderMixIn(object):
    """a collection of methods used in csv, pdf and oai_dc import"""
    richstring_template = u'''
<div class="ead-section ead-{attr}">
  <div class="ead-wrapper">
    <div class="ead-p">{data}</div>
  </div>
</div>'''

    def richstring_html(self, data, attr):
        if data:
            data = xml_escape(data).replace('\n', '<br />')
            return self.richstring_template.format(
                data=data, attr=attr)
        return None

    def index_entries(self, entry, target_eid, fa_attrs):
        index_entries = {}  # create a map to keep unique index entries only
        for index_name, index_type in (
                ('index_personne', 'persname'),
                ('index_collectivite', 'corpname'),
                ('index_lieu', 'geogname'),
                ('index_matiere', 'subject')):
            index_labels = entry.get(index_name) or ()
            if not isinstance(index_labels, (list, tuple)):
                index_labels = [s.strip() for s in index_labels.split(';')]
            for index_label in index_labels:
                if not index_label:
                    # ignore empty string
                    continue
                index_label = index_label[:256].strip()
                index_infos = {
                    'type': index_type,
                    'label': index_label,
                    'normalized': normalize_entry(index_label),
                    'role': u'index',
                    'authfilenumber': None,
                }
                self.create_index(index_infos, target_eid, fa_attrs)
                index_entries[(index_type, index_infos['normalized'])] = index_infos
        return index_entries

    def import_findingaid(self, service_infos, filepath, metadata,
                          fa_support, **fa_es_attrs):
        file_identifier = metadata['identifiant_fichier']
        unittitle = metadata['titre']
        did_attrs = {
            'unittitle': unittitle,
            'startyear': get_year(metadata.get('date1')),
            'stopyear': get_year(metadata.get('date2')),
            'physdesc': self.richstring_html(metadata.get('format'),
                                             'physdesc'),
            'physdesc_format': u'text/html',
            'lang_description': metadata.get('langue'),
            'origination': metadata.get('origine'),
            'extptr': metadata.get('identifiant_uri')
        }
        did_data = self.create_entity('Did', clean_values(did_attrs))
        header_attrs = self.create_entity('FAHeader',
                                          {'titleproper': unittitle})
        # cwuri = unicode(did_data['eid'])
        basepath = get_basepath(filepath)
        if file_identifier and file_identifier != basepath:
            self.log.warning(
                '`file_identifier` "{0}" is different from the imported file name "{1}"'.format(
                    file_identifier, basepath))
        service_code = basepath.split('_')[0].upper()
        publisher = service_infos.get('name', service_code)
        fa_attrs = {
            'name': file_identifier,
            'eadid': remove_extension(file_identifier),
            'fatype': metadata.get('type'),
            'did': did_data['eid'],
            'scopecontent': self.richstring_html(
                metadata.get('description'), 'scopecontent'),
            'scopecontent_format': u'text/html',
            'additional_resources': self.richstring_html(
                metadata.get('source_complementaire'), 'additional_resources'),
            'additional_resources_format': u'text/html',
            'accessrestrict': self.richstring_html(metadata.get('conditions_acces'),
                                                   'accessrestrict'),
            'accessrestrict_format': u'text/html',
            'userestrict': self.richstring_html(metadata.get('conditions_utilisation'),
                                                'userestrict'),
            'userestrict_format': u'text/html',
            'stable_id': usha1(file_identifier),
            'publisher': unicode(publisher),
            'service': service_infos.get('eid'),
            'fa_header': header_attrs['eid'],
        }
        if fa_support is not None:
            fa_attrs['findingaid_support'] = fa_support['eid']
        fa_data = self.create_entity('FindingAid', clean_values(fa_attrs))
        fa_es_attrs.update({
            'name': fa_data['name'],
            'fatype': fa_data.get('fatype'),
            'fa_stable_id': fa_data['stable_id'],
            'scopecontent': strip_html(fa_attrs.get('scopecontent'))})
        es_doc = self.build_complete_es_doc(
            u'FindingAid', fa_data, did_data,
            self.index_entries(metadata, fa_data['eid'], fa_data), **fa_es_attrs)
        self.create_entity('EsDocument', {'doc': json_dumps(es_doc['_source']),
                                          'entity': fa_data['eid']})
        return es_doc

    def build_complete_es_doc(self, etype, attrs, did_attrs, index_entries, **kwargs):
        es_did_attrs = es_dict(did_attrs, ['unittitle', 'unitid'])
        year = did_attrs.get('startyear') or did_attrs.get('stopyear')
        es_doc = {
            'escategory': ETYPE_CATEGORIES[etype],
            'publisher': attrs.get('publisher'),
            'cw_etype': etype,
            'did': es_did_attrs,
            'year': int(year) if year else None,
            'eadid': attrs.get('eadid'),
            'eid': attrs['eid'],
            'stable_id': attrs['stable_id'],
            'index_entries': unique_indices(index_entries.values())
        }
        es_doc.update(kwargs)
        return self.build_es_doc(
            attrs['stable_id'],
            es_doc,
            index_name=self.config['index-name'] + '_all'
        )


class Reader(MetadataReaderMixIn,
             IndexImporterMixin):

    def __init__(self, config, store):
        super(Reader, self).__init__()
        self.config = config
        self.index_policy = {
            'autodedupe_authorities': self.config.get('autodedupe_authorities', 'service/strict'),
        }
        self.log = config.get('log')
        if self.log is None:
            self.log = LOGGER
        self.store = store
        if self.config['esonly']:
            self.add_rel = lambda *a, **k: None
            self.authority_records = {}
            self.known_fa_ids = set()
            for rqlpath in ('I index FA', 'I index FAC, FAC finding_aid FA'):
                for typevar, rqlpath2 in (('T', 'I is AgentName, I type T'),
                                          ("'geogname'", 'I is Geogname'),
                                          ("'subject'", 'I is Subject')):
                    self.indices.update({
                        (s, t, l, r): (i, a)
                        for t, l, r, i, a, s in store.rql(
                            'Any {}, L, R, I, A, S WHERE '
                            'FA is FindingAid, FA stable_id S, {}, '
                            'I label L, I authority A, I role R, '
                            '{}'.format(typevar, rqlpath, rqlpath2)
                        )
                    })
        else:
            self.add_rel = self.store.prepare_insert_relation
            self.authority_records = {r: {'eid': x, 'label': l}
                                      for x, r, l in store.rql('Any X, R, L WHERE '
                                                               'X is AuthorityRecord, '
                                                               'X record_id R, '
                                                               'X name L')}
            self.known_fa_ids = {
                stable_id for stable_id, in store.rql('Any S WHERE X is FindingAid, X stable_id S')
            }
        self.delete_existing_findingaid = False
        self.deferred = {}
        self._pdf_metadata_cache = {}
        self._files = {}
        self._stable_id_map = None
        self._richstring_cache = {}
        self.imported_findingaids = []
        self._init_authorities()
        self._init_auth_history()

    def etype_richstring_attrs(self, etype):
        if etype in self._richstring_cache:
            return self._richstring_cache[etype]
        # NOTE: RQLObjectStore doesn't have a ``schema`` attribute
        # unlike MassiveObjectStore
        eschema = self.store._cnx.vreg.schema.eschema(etype)
        meta_attributes = eschema.meta_attributes()
        rich_attrs = [(attr, rschema.type)
                      for rschema, (meta, attr) in meta_attributes.items()
                      if meta == 'format']
        self._richstring_cache[etype] = rich_attrs
        return rich_attrs

    @property
    def files(self):
        if not self._files:
            rset = self.store.rql(
                'Any FSPATH(D), X, S WHERE X is File, X data D, X data_sha1hex S, '
                'FA findingaid_support X'
            )
            self._files = {osp.basename(d.read()): (x, s) for d, x, s in rset}
        return self._files

    def build_url(self, *restpath):
        base_url = self.config['base-url'].rstrip('/')
        return '%s/%s' % (base_url, '/'.join(str(r) for r in restpath))

    def stable_id_to_eid(self, stable_id):
        if self._stable_id_map is None:
            # safety belt, should not happen: we should always have created the
            # FindingAid before trying to create the FAComponent
            self._stable_id_map = findingaid_eids(self.store._cnx, stable_id)
        return self._stable_id_map.get(stable_id)

    def create_entity(self, etype, attrs):
        attrs = strip_nones(attrs)
        for attr, fmt_attr in self.etype_richstring_attrs(etype):
            if attr in attrs and fmt_attr not in attrs:
                attrs[fmt_attr] = u'text/html'
        if self.config['esonly']:
            eid = None
            # try to get FindingAid / FAComponent eid in esonly mode
            if 'stable_id' in attrs:
                eid = self.stable_id_to_eid(attrs['stable_id'])
        else:
            eid = self.store.prepare_insert_entity(etype, **attrs)
        attrs['eid'] = eid
        if etype == 'FindingAid':
            self.imported_findingaids.append(eid)
        return attrs

    def create_did(self, attrs):
        return self.create_entity('Did', strip_nones(attrs))

    def create_file(self, filepath, title=None, sha1=None):
        sha1 = sha1 or usha1(open(filepath).read())
        if not self.config['esonly'] and self.ignore_filepath(filepath, sha1):
            return None
        f = self.create_cwfile(filepath, title, sha1)
        basepath = osp.basename(osp.abspath(decode_filepath(filepath)))
        self._files[basepath] = (f['eid'], sha1)
        return f

    def create_cwfile(self, filepath, title=None, sha1=None):
        ufilepath = osp.abspath(decode_filepath(filepath))
        basepath = osp.basename(ufilepath)
        return self.create_entity('File', {
            'title': title or basepath,
            'data': ufilepath,
            'data_format': unicode(mimetypes.guess_type(filepath)[0]),
            'data_name': basepath,
            'data_sha1hex': sha1,
            'uuid': unicode(uuid4().hex),
        })

    def import_component(self, comp_props, findingaid_attrs, parent_component):
        did_attrs = self.create_did(comp_props['did'])
        referenced_files = comp_props.pop('referenced_files')
        comp_attrs = merge_dicts({
            'did': did_attrs['eid'],
            'finding_aid': findingaid_attrs['eid'],
            'stable_id': component_stable_id(findingaid_attrs['stable_id'],
                                             comp_props['path']),
            'parent_component': parent_component,
            'component_order': comp_props['path'][-1],
        }, pick(comp_props, 'fatype',
                *chain(*((p, p + '_format')
                         for p in ('description', 'bibliography',
                                   'bioghist', 'notes',
                                   'genreform', 'function', 'occupation',
                                   'acquisition_info', 'scopecontent',
                                   'accessrestrict', 'userestrict',
                                   'additional_resources'))))
        )
        comp_attrs = self.create_entity('FAComponent', strip_nones(comp_attrs))
        self.create_referenced_files(comp_attrs['eid'], referenced_files)
        # uniquify index entries but only on labels (instead of normalized)
        # to keep variants
        index_entries = unique_indices(chain(comp_props['origination'],
                                             comp_props['index_entries']),
                                       keys=('type', 'label'))
        for infos in index_entries:
            self.create_index(infos, target=comp_attrs['eid'], fa_attrs=findingaid_attrs)

        for daodef in comp_props['daos']:
            digit_ver_attrs = self.create_entity('DigitizedVersion',
                                                 strip_nones(daodef))
            self.add_rel(comp_attrs['eid'], 'digitized_versions',
                         digit_ver_attrs['eid'])

        year = (year_value(did_attrs.get('startyear'), True)
                or year_value(did_attrs.get('stopyear')))
        es_doc = es_dict(comp_attrs, ['name', 'eadid', 'fatype', 'stable_id',
                                      'description', 'acquisition_info',
                                      'genreform', 'function', 'occupation',
                                      'scopecontent'],
                         did=es_dict(did_attrs,
                                     ['unittitle', 'unitid', 'note', 'abstract']),
                         year=year,
                         publisher=findingaid_attrs['publisher'],
                         digitized=bool(comp_props['daos']),
                         index_entries=unique_indices(index_entries),
                         originators=findingaid_attrs['originators'],
                         fa_stable_id=findingaid_attrs['stable_id'],
                         cw_etype='FAComponent')
        complete_es_doc = self.build_es_doc(comp_attrs['stable_id'], es_doc,
                                            index_name=self.config['index-name'] + '_all')
        self.create_entity('EsDocument', {'doc': json_dumps(es_doc),
                                          'entity': comp_attrs['eid']})
        return complete_es_doc

    def ignore_filepath(self, filepath, sha1):
        basepath = osp.basename(filepath)
        if basepath in self.files:
            # a file with same filepath (i.e. same stable_id) was already imported
            if self.config.get('update_imported'):
                return False
            if not self.config.get('reimport'):
                self.log.info('ignore already imported file %s', basepath)
                return True
            prevsha1 = self.files[basepath][1]
            if prevsha1 == sha1 and not self.config.get('force_delete'):
                self.log.info('ignore already imported file %s (because of identical sha1)',
                              basepath)
                return True
            self.log.info('delete entities related to already imported file %s',
                          basepath)
            self.delete_existing_findingaid = True
        return False

    def delete_from_filename(self, filepath):
        if self.delete_existing_findingaid:
            delete_from_filename(
                self.store._cnx, filepath,
                interactive=False, esonly=self.config['esonly'])

    def make_symlink(self, filepath, sha1):
        if self.config.get('appfiles-dir'):
            destpath = osp.join(self.config['appfiles-dir'],
                                '{}_{}'.format(str(sha1), osp.basename(filepath)))
            if osp.lexists(destpath):
                os.unlink(destpath)
            os.symlink(filepath, destpath)

    def import_filepath(self, filepath, service_infos=None):
        entities = []
        if IN_RELFILES_RE.match(filepath):
            return entities
        # do not reimport harvesting files for now
        if file_from_oaipmh(filepath):
            return entities
        self._stable_id_map = None
        file_ext = osp.splitext(filepath)[1].lower()
        if service_infos is None:
            service_infos = {}
        if file_ext in ('.xml', '.pdf'):
            sha1 = usha1(open(filepath).read())
            f = self.create_file(filepath, sha1=sha1)
            if f is None:
                return entities
            self.update_authorities_cache(service_infos.get('eid'))
            if file_ext == '.xml':
                relfiles_dir = '{}/RELFILES'.format(osp.dirname(filepath))
                if osp.isdir(relfiles_dir):
                    relfiles = dict((osp.basename(f), f) for
                                    f in glob.glob('{}/*.pdf'.format(relfiles_dir)))
                else:
                    relfiles = None
                entities = self.import_ead_xml(filepath, service_infos,
                                               fa_support=f, relfiles=relfiles)
            elif file_ext == '.pdf':
                if not self.config['esonly']:
                    self.make_symlink(filepath, sha1)
                    self.delete_from_filename(filepath)
                entities = self.import_pdf(filepath, service_infos, fa_support=f)
        else:
            self.log.debug('ignoring unknown extension %s',
                           osp.splitext(filepath)[-1])
            return []
        return entities

    def import_ead_xml(self, filepath, service_infos, fa_support=None, relfiles=None):
        """
        Parameters:
        -----------

        filepath      : filepath of the XML EAD
        service_infos : a map of properties {name, code, eid}
        fa_support    : CW File object hosting the finding aid content (XXX attr_cache)
        """
        try:
            tree = preprocess_ead(filepath)
        except Exception:
            self.log.exception('invalid xml %r', filepath)
            capture_exception(self.config, filepath)
            return []
        self.delete_from_filename(filepath)
        return self.import_ead_xmltree(tree, service_infos, fa_support,
                                       relfiles)

    def import_ead_xmltree(self, tree, service_infos,
                           fa_support=None, relfiles=None):
        """

        Parameters:
        -----------

        tree          : the lxml ead tree object to process
        service_infos : a map of properties {name, code, eid}
        fa_support    : CW File object hosting the finding aid content (XXX attr_cache)
        """
        ead_reader = EADXMLReader(tree, relfiles, log=self.log)
        header_props = ead_reader.fa_headerprops()
        fa_properties = ead_reader.fa_properties
        eadid = header_props.pop('eadid')
        if not eadid:
            if not fa_support['data_name']:
                raise Exception('findingaid with neither file nor eadid')
            eadid = osp.splitext(fa_support['data_name'])[0]
        if fa_support is None or file_from_oaipmh(fa_support['data']):
            # Before we stored oaipmph harvested files on the filesystem their eadid
            # was not based on the fa_support['data_name']. We must thus
            # maintain the compliance with thoses old cases.
            ir_name = eadid
        else:
            ir_name = fa_support['data_name']
        stable_id = usha1(ir_name)
        # if stable_id is already imported and we're in "reimport" mode,
        # delete findingaid and facomonents before reimporting them
        if stable_id in self.known_fa_ids and self.config.get('reimport'):
            delete_from_filename(
                self.store._cnx, stable_id, interactive=False,
                esonly=self.config['esonly'], is_filename=False)

        header_attrs = self.create_entity('FAHeader', strip_nones(header_props))
        did_props = fa_properties['did']
        did_attrs = self.create_did(did_props)
        # XXX if stable_id in already_imported and not self.config.get('reimport'): continue
        ape_filepath = osp.join(self.config['appfiles-dir'],
                                compute_ape_relpath(ir_name, service_infos))
        generate_ape_ead_file_from_xml(self.store._cnx, tree,
                                       service_infos, stable_id, ape_filepath)
        ape_file = self.create_file(ape_filepath)
        referenced_files = fa_properties.pop('referenced_files')
        findingaid_attrs = merge_dicts(
            {
                'stable_id': stable_id,
                'eadid': eadid,
                'name': ir_name,
                'fa_header': header_attrs['eid'],
                'did': did_attrs['eid'],
                'findingaid_support': fa_support['eid'] if fa_support else None,
                'ape_ead_file': ape_file['eid'] if ape_file else None,
                'service': service_infos.get('eid'),
                'publisher': service_infos.get('name', eadid.split('_')[0]),
            },
            pick(fa_properties, 'fatype',
                 *chain(*((p, p + '_format')
                          for p in ('description', 'bibliography', 'bioghist',
                                    'acquisition_info', 'scopecontent',
                                    'accessrestrict', 'userestrict',
                                    'additional_resources', 'notes',
                                    'genreform', 'function', 'occupation',
                                    'website_url'))))
        )
        findingaid_attrs = self.create_entity('FindingAid',
                                              strip_nones(findingaid_attrs))
        self.create_referenced_files(findingaid_attrs['eid'], referenced_files)
        index_entries = unique_indices(chain(fa_properties['origination'],
                                             fa_properties['index_entries']))
        for infos in index_entries:
            self.create_index(infos, target=findingaid_attrs['eid'], fa_attrs=findingaid_attrs)
        fa_es_doc = es_dict(findingaid_attrs, ['name', 'eadid', 'fatype',
                                               'description', 'acquisition_info',
                                               'genreform', 'function', 'occupation',
                                               'index_entries', 'stable_id',
                                               'publisher', 'scopecontent',
                                               'originators'],
                            cw_etype='FindingAid',
                            titleproper=header_attrs.get('titleproper'),
                            author=header_attrs.get('author'),
                            fa_stable_id=findingaid_attrs['stable_id'],
                            did=es_dict(did_attrs,
                                        ['unittitle', 'unitid', 'note', 'abstract']),
                            index_entries=index_entries,
                            originators=ead_reader.originators())
        fa_es_doc['year'] = (year_value(did_attrs.get('startyear'), True)
                             or year_value(did_attrs.get('stopyear')))
        es_documents = [self.build_es_doc(findingaid_attrs['stable_id'], fa_es_doc,
                                          index_name=self.config['index-name'] + '_all')]
        self.create_entity('EsDocument', {'doc': json_dumps(fa_es_doc),
                                          'entity': findingaid_attrs['eid']})
        path2eid = {(): None}
        # update findingaid_attrs['originators'] from es_doc
        # we do not use findingaid_attrs further
        findingaid_attrs['originators'] = fa_es_doc['originators']
        for comp_node, comp_attrs in ead_reader.walk():
            parent_component = path2eid[comp_attrs['path'][:-1]]
            es_doc = self.import_component(comp_attrs, findingaid_attrs,
                                           parent_component=parent_component)
            path2eid[comp_attrs['path']] = es_doc['_source']['eid']
            es_documents.append(es_doc)
        return es_documents

    def create_referenced_files(self, fa_eid, referenced_files):
        """always create a new file"""
        for file_info in referenced_files:
            feid = self.create_cwfile(**file_info)['eid']
            self.add_rel(fa_eid, 'fa_referenced_files', feid)
            self.make_symlink(file_info['filepath'], file_info['sha1'])

    def import_pdf(self, filepath, service_infos,
                   fa_support, metadata=None):
        infos = pdf.pdf_infos(filepath)
        if metadata is None:
            metadata = self.pdf_metadata(filepath)
        fa_es_attrs = {'text': infos['text']}
        return [self.import_findingaid(service_infos, filepath, metadata,
                                       fa_support=fa_support, **fa_es_attrs)]

    def pdf_metadata(self, filepath):
        directory = osp.dirname(filepath)
        metadata_file = osp.join(directory, 'metadata.csv')
        if not osp.isfile(metadata_file):
            self.log.warning('ignoring PDF directory %s because metadata.csv file is missing',
                             directory)
            all_metadata = {}
        elif metadata_file not in self._pdf_metadata_cache:
            all_metadata = load_metadata_file(metadata_file)
            self._pdf_metadata_cache[metadata_file] = all_metadata
        else:
            all_metadata = self._pdf_metadata_cache[metadata_file]
        filename = osp.basename(filepath)
        if filename not in all_metadata:
            self.log.info('using dummy metadata for %s', filename)
            filename = osp.basename(filepath)
            return default_csv_metadata(remove_extension(filename))
        return all_metadata[filename]

    def build_es_doc(self, _id, _source, index_name=None):
        doc = {
            '_op_type': 'index',
            '_index': self.config['index-name'],
            '_type': '_doc',
            '_id': _id,
            '_source': _source
        }
        _source['escategory'] = ETYPE_CATEGORIES[_source['cw_etype']]
        if index_name:
            doc['_index'] = index_name
        return doc


def es_dict(entity_attrs, props, **kwargs):
    d = {}
    for propname in props:
        value = entity_attrs.get(propname)
        fmt = entity_attrs.get('%s_format' % propname)
        if fmt == 'text/html' and value:
            value = strip_html(value)
        d[propname] = value
    for k, v in kwargs.items():
        d[k] = v
    d['eid'] = entity_attrs['eid']
    return d


def service_infos_from_filepath(filepath, services_map):
    service_code = osp.basename(filepath).split('_')[0].upper()
    infos = {
        'code': service_code,
        'name': service_code,
        'eid': None,
    }
    if service_code in services_map:
        service = services_map[service_code]
        infos.update({
            'eid': service.eid,
            'name': service.publisher(),
        })
    return infos


def findingaid_importer(appid, filepath_queue, config):
    init_sentry_client(config)
    with admincnx(appid) as cnx:
        _findingaid_importer(cnx, filepath_queue, config)


def _findingaid_importer(cnx, filepath_queue, config):
    services_map = load_services_map(cnx)
    # bfss should be initialized to enable `FSPATH` in rql
    init_bfss(cnx.repo)
    if not config['esonly']:
        store = create_massive_store(cnx, slave_mode=True)
    else:
        store = RQLObjectStore(cnx)
    readercls = config.get('readercls', Reader)
    r = readercls(config, store)
    indexer = cnx.vreg['es'].select('indexer', cnx)
    es = indexer.get_connection()
    es_docs = []
    while True:
        next_job = filepath_queue.get()
        # worker got None in the queue, job is finished
        if next_job is None:
            break
        filepath = next_job
        try:
            service_infos = service_infos_from_filepath(filepath,
                                                        services_map)
            es_docs = r.import_filepath(filepath, service_infos)
        except Exception:
            import traceback
            traceback.print_exc()
            print('failed to import', repr(filepath))
            LOGGER.exception('failed to import %r', filepath)
            capture_exception(config, filepath)
            continue
        if not config['esonly']:
            store.flush()
            store.commit()
        if es_docs and not config['noes']:
            es_bulk_index(es, es_docs)
    if not config['esonly']:
        cnx.commit()


class FakeQueue(list):

    def get(self, *args):
        return self.pop(*args)


def _import_filepaths(cnx, filepaths, config):
    indexer = cnx.vreg['es'].select('indexer', cnx)
    indexer.create_index(index_name=u'{}_all'.format(indexer._cw.vreg.config['index-name']))
    # leave at least one process available
    nb_processes = config.get('nb_processes', max(mp.cpu_count() - 1, 1))
    if cnx.vreg.config.mode == 'test':
        fake_queue = FakeQueue([None] + filepaths)
        _findingaid_importer(cnx, fake_queue, config)
    elif nb_processes == 1:
        fake_queue = FakeQueue([None] + filepaths)
        findingaid_importer(config['appid'], fake_queue, config)
    else:
        queue = mp.Queue(2 * nb_processes)
        workers = []
        for i in range(nb_processes):
            # findingaid_importer(appid, filepath_queue, config):
            workers.append(mp.Process(target=findingaid_importer,
                                      args=(config['appid'],
                                            queue,
                                            config)))
        for w in workers:
            w.start()
        nb_files = len(filepaths)
        for idx, job in enumerate(chain(filepaths, (None,) * nb_processes)):
            if job is not None:
                if not osp.isfile(job):
                    LOGGER.warning('ignoring unknown file %r', job)
                    continue
                print('pushing %s/%s job in queue - %s' % (idx + 1, nb_files,
                                                           osp.basename(job)))
            queue.put(job)
        for w in workers:
            w.join()


def ead_foreign_key_tables(schema):
    etypes = {
        'FindingAid', 'FAComponent', 'File',
        'Did', 'FAHeader', 'DigitizedVersion',
        'Subject', 'Geogname',
        'AgentName', 'AgentAuthority',
        'LocationAuthority', 'SubjectAuthority',
        'Person', 'EsDocument',
    }
    tables = {'entities', 'cw_source_relation',
              'is_relation', 'is_instance_of_relation'}
    for etype in etypes:
        eschema = schema.eschema(etype)
        for rschema, tschemas, role in eschema.relation_definitions():
            # exclude relations with no actual existence in the database
            if rschema.type == 'identity' or rschema.rule:
                continue
            if rschema.inlined:
                tables.add('cw_{}'.format(eschema.type.lower()))
            else:
                tables.add('{}_relation'.format(rschema.type.lower()))
                if len(tschemas) == 1:
                    tables.add('cw_{}'.format(tschemas[0].type.lower()))
    return tables


@log_in_db
def import_filepaths(cnx, filepaths, config, store=None):
    foreign_key_tables = ead_foreign_key_tables(cnx.vreg.schema)
    if not config['esonly']:
        store = store or create_massive_store(cnx, nodrop=config['nodrop'])
        store.master_init()
        create_ead_index_table(cnx)
        if config['nodrop']:
            with sqlutil.sudocnx(cnx, interactive=False) as su_cnx:
                sqlutil.disable_triggers(su_cnx, foreign_key_tables)
        cnx.commit()
    _import_filepaths(cnx, filepaths, config)
    if not config['esonly']:
        store.finish()
        store.commit()
    if config['nodrop']:
        with sqlutil.sudocnx(cnx, interactive=False) as su_cnx:
            sqlutil.enable_triggers(su_cnx, foreign_key_tables)
