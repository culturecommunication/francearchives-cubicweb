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

"""cubicweb-francearchives postcreate script, executed at instance creation time or when
the cube is added to an existing instance.

You could setup site properties or a workflow here for example.
"""
import os.path as osp

from cubicweb_francearchives import SUPPORTED_LANGS
from cubicweb_francearchives import workflows, create_homepage_metadata

HERE = osp.join(osp.abspath(osp.dirname(__file__)))

workflows.oai_import_task_workflow(add_workflow)

def datapath(relpath):
    return osp.join(HERE, 'initialdata', relpath)

set_property('ui.site-title', 'FranceArchives')  # noqa
set_property(u'ui.language', u'fr')  # noqa


create_entity('ConceptScheme', title=u'siaf')

cnx.system_sql('DROP TABLE IF EXISTS executed_command')
cnx.system_sql('CREATE TABLE executed_command ('
               # name of executed command
               'name varchar(50),'
               # datetime when command started
               'start TIMESTAMP WITH TIME ZONE DEFAULT current_timestamp,'
               # datetime when command ended
               'stop TIMESTAMP WITH TIME ZONE,'
               # RAM used by process at the end of command
               'memory varchar(20))')

if cnx.vreg.config.system_source_config['db-driver'].lower() == 'postgres':
    cnx.system_sql("""
    CREATE OR REPLACE FUNCTION create_entities(etype varchar,
                                               from_table varchar,
                                               update_cweid boolean)
    RETURNS void AS $$
    DECLARE
        admin_eid integer := 0;
        source_eid integer := 0;
        etype_eid integer := 0;
        last_eid integer := 0;
        nb_new_entity integer := 0;
        t varchar;
    BEGIN
      EXECUTE 'SELECT cw_eid FROM  cw_cwsource WHERE cw_name=''system'''  INTO  source_eid;
      EXECUTE 'SELECT MIN(cw_eid) FROM  cw_cwuser'  INTO  admin_eid;
      EXECUTE format('SELECT cw_eid FROM  cw_cwetype WHERE cw_name=%L', etype)  INTO  etype_eid;


      EXECUTE format('SELECT COUNT(*) FROM %s', from_table) INTO nb_new_entity;

      IF nb_new_entity = 0 THEN
         RETURN;
      END IF;

      IF update_cweid THEN
        EXECUTE 'SELECT last FROM entities_id_seq' INTO last_eid;
        EXECUTE format('UPDATE %s SET cw_eid=cw_eid+%L', from_table, last_eid);
        EXECUTE format('SELECT MAX(cw_eid) FROM %s', from_table) INTO last_eid;
        EXECUTE format('UPDATE entities_id_seq SET last=%L', last_eid);
      END IF;

      EXECUTE format('INSERT INTO entities (eid, type) SELECT cw_eid, %L  FROM %s', etype, from_table);

      FOREACH t IN ARRAY ARRAY['created_by_relation', 'owned_by_relation'] LOOP
        EXECUTE format('INSERT INTO %s SELECT cw_eid, %L FROM %s', t, admin_eid, from_table);
      END LOOP;

      EXECUTE format('INSERT INTO cw_source_relation SELECT cw_eid, %L FROM %s', source_eid, from_table);

      FOREACH t IN ARRAY ARRAY['is_relation', 'is_instance_of_relation'] LOOP
        EXECUTE format('INSERT INTO %s SELECT cw_eid, %L FROM %s', t, etype_eid, from_table);
      END LOOP;

    END;
    $$ LANGUAGE plpgsql;
    """)

    cnx.system_sql("""
CREATE OR REPLACE FUNCTION push_entities(etype varchar,
                                         colnames varchar,
                                         query varchar)
RETURNS void AS $$
DECLARE
    tmp_table varchar := 'tmp_' || etype || floor(random() * 10000);
    etype_table varchar := 'cw_' || etype;
    eid_seqname varchar := tmp_table || '_eid';
BEGIN

  EXECUTE format('DROP TABLE IF EXISTS %s', tmp_table);
  EXECUTE format('DROP SEQUENCE IF EXISTS %s', eid_seqname);
  EXECUTE format('CREATE SEQUENCE %s', eid_seqname);
  EXECUTE format('CREATE TABLE %s AS SELECT * FROM %s LIMIT 0', tmp_table, etype_table);
  EXECUTE format('ALTER TABLE %s ALTER COLUMN cw_eid SET DEFAULT nextval(''%s'')', tmp_table, eid_seqname);
  EXECUTE format('ALTER TABLE %s ALTER COLUMN cw_cwuri SET DEFAULT ''http://francearchives.fr'' ', tmp_table); -- would require a trigger to properly set the value
  EXECUTE format('ALTER TABLE %s ALTER COLUMN cw_modification_date SET DEFAULT NOW()', tmp_table);
  EXECUTE format('ALTER TABLE %s ALTER COLUMN cw_creation_date SET DEFAULT NOW()', tmp_table);
  EXECUTE format('INSERT INTO %s (%s) %s', tmp_table, colnames, query);

  EXECUTE format('SELECT create_entities(%L, %L, TRUE)', etype, tmp_table);

  -- XXX why %s instead of %I ?
  EXECUTE format('INSERT INTO %s SELECT * FROM %s', etype_table, tmp_table);

  EXECUTE format('DROP TABLE IF EXISTS %s', tmp_table);
  EXECUTE format('DROP SEQUENCE %s', eid_seqname);

END;
$$ LANGUAGE plpgsql;
    """)

    cnx.system_sql(r"""
CREATE OR REPLACE FUNCTION normalize_entry(entry varchar)
RETURNS varchar AS $$
DECLARE
        normalized varchar;
BEGIN
 normalized := regexp_replace(entry, '\(\s*[\d.]+\s*-\s*[\d.]+\s*\)', '');
 normalized := translate(normalized, E'!"#$%&()*+,-./:;<=>?@[\\]^_`{|}~\'', '');
 normalized := btrim(unaccent(lower(normalized)));

 SELECT string_agg(T.word, ' ') INTO normalized
 FROM (SELECT unnest(string_to_array(normalized, ' ')) AS word ORDER BY 1) AS T;

 RETURN btrim(normalized);
END;
$$ LANGUAGE plpgsql;
    """)

    cnx.system_sql('''
CREATE OR REPLACE FUNCTION delete_entities(etype varchar, from_table varchar)
RETURNS void AS $$
DECLARE
  t varchar;
BEGIN
  FOREACH t IN ARRAY ARRAY['created_by_relation', 'owned_by_relation', 'cw_source_relation', 'is_relation', 'is_instance_of_relation'] LOOP
    EXECUTE format('DELETE FROM %s USING %s WHERE eid_from = %s.eid', t, from_table, from_table);
  END LOOP;
  EXECUTE format('DELETE FROM %s USING %s WHERE cw_eid = %s.eid', etype, from_table, from_table);
  EXECUTE format('DELETE FROM entities USING %s WHERE entities.eid = %s.eid', from_table, from_table);
END;
$$ LANGUAGE plpgsql;''')  # noqa

    cnx.system_sql('''
    CREATE OR REPLACE FUNCTION update_index_entries(index_entries json, oldauth int, newauth int)
    RETURNS jsonb as $$
    DECLARE
      result jsonb;
    BEGIN
      SELECT
        json_agg(
          json_build_object(
            'authority', CASE tmp.authority WHEN oldauth THEN newauth ELSE tmp.authority END,
            'label', tmp.label,
            'role', tmp.role,
            'normalized', tmp.normalized,
            'type', tmp.type
          )
        )
        INTO result
      FROM
        json_to_recordset(index_entries) as tmp(authority int, label text, role text, normalized text, authfilenumber text, type text);
      RETURN result;
    END;
    $$ language plpgsql;
    ''')


for wikiid, title in (('faq', u'Foire aux questions'),
                      ('cgu', u"Conditions générales d'utilisation"),
                      ('privacy_policy', u"Politique de confidentialité"),
                      ('legal_notices', u"Mentions légales"),
                      ('open_data', u"Open data"),
                      ('emplois', u"Offres d'emplois"),
                      ('about', u"A propos"),
                      ('tableau-circulaires', u"Tableau des circulaires"),
                      ('accessibility', u"Accessibilité")):
    for lang in SUPPORTED_LANGS:
        create_entity('Card', wikiid=u'%s-%s' % (wikiid, lang),
                      title=title,
                      content_format=u'text/html')


# create cards
cards = ((u'alert', u'Alert', False),
         (u'contact', u'Contact', True),
         (u'newsletter', (u"Lettre d'information"), True)
         )

for cid, title, has_content in cards:
    content = None
    if has_content:
        try:
            stream = open(datapath('%s.html' % cid), 'r')
            content = stream.read()
            content = content.decode('utf8')
        except Exception, err:
            print (u'\n [info] no content file "%s.html" '
                   u'found or the content file is unreadible') % cid
    create_entity('Card', title=title, content=content,
                  wikiid=cid, content_format=u'text/html')

create_homepage_metadata(cnx)
commit()
try:
    sql('create extension unaccent')
    commit()
except Exception as e:
    print('cannot create extension unaccent (%s)' % e)

sql(
    'CREATE TABLE authority_history ( '
    '  fa_stable_id varchar(64),'
    '  type varchar(20),'
    '  indexrole varchar(2048),'
    '  label varchar(2048),'
    '  autheid int,'
    '  UNIQUE (fa_stable_id, type, label, indexrole)'
    ')'
)
commit()

# create geonames table
cnx.system_sql(
    '''
    CREATE TABLE geonames (
    geonameid integer not null,
    name varchar(200),
    asciiname varchar(200),
    alternatenames varchar(10000),
    latitude double precision,
    longitude double precision,
    fclass char(1),
    fcode varchar(10),
    country_code varchar(2),
    cc2 varchar(200),
    admin1_code varchar(20),
    admin2_code varchar(80),
    admin3_code varchar(20),
    admin4_code varchar(20),
    population bigint,
    elevation int,
    dem int,
    timezone varchar(40),
    moddate date
    );
    '''
)
commit()
