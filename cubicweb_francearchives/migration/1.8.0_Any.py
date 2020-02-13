# flake8: noqa
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
from cubicweb_francearchives.workflows import oai_import_task_workflow
from cubicweb_francearchives import create_homepage_metadata

create_homepage_metadata(cnx)
commit()

add_entity_type("Json")
add_entity_type("EsDocument")

add_attribute("CommemorationItem", "on_homepage_order")

drop_entity_type("FAChange")
drop_entity_type("IndexEntry")
drop_entity_type("Alignment")

add_entity_type("OAIRepository")
add_entity_type("OAIImportTask")
oai_import_task_workflow(add_workflow)
commit()

sync_schema_props_perms("collection_top")

cnx.system_sql(
    """
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
$$ LANGUAGE plpgsql;"""
)  # noqa

commit()
