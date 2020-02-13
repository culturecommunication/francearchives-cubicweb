# flake8: noqa
# -*- coding: utf-8 -*-
from cubicweb_francearchives import load_leaflet_json

add_entity_type("ExternalId", auto=True, commit=True)
add_entity_type("Caches")

drop_attribute("Service", "browser_url")
drop_attribute("Service", "organization_chart")

load_leaflet_json(cnx)

cnx.system_sql(
    """
    ALTER TABLE cw_findingaid
    ADD CONSTRAINT cw_findingaid_unique_name
    UNIQUE(cw_name);"""
)

cnx.system_sql(
    """
   ALTER TABLE published.cw_findingaid
   ADD CONSTRAINT cw_findingaid_unique_name
   UNIQUE(cw_name);"""
)

cnx.system_sql(
    """
    CREATE TABLE fa_redirects (
    old_ir_name character varying(512),
    from_stable_id character varying(64) PRIMARY KEY NOT NULL,
    to_stable_id character varying(64) not null,
    date date,
    UNIQUE (from_stable_id, to_stable_id)
    );

    CREATE INDEX fa_redirects_from_stable_id ON fa_redirects(from_stable_id);
"""
)
