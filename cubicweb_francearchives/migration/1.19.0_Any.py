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

change_attribute_type("Service", "zip_code", "String")

for eid, zip_code in rql("Any X, Z WHERE X is Service, X zip_code Z"):
    rql(
        "SET X zip_code %(z)s WHERE X eid %(e)s",
        {"e": eid, "z": "%05d" % int(zip_code) if zip_code else ""},
    )

# csv for circulars
add_attribute("Circular", "json_values")


def update_published_circulars_schema(cnx):
    sql = cnx.system_sql
    sql("ALTER TABLE published.cw_circular ADD cw_json_values JSON")
    cnx.commit()


update_published_circulars_schema(cnx)

rset = rql(
    "Any S, SK, SC, NOR, STAT, SLINK, SALU, "
    "SDSD, SD, SDK, SDC, SPD, SPDC, "
    "SMD, SAD, SAT, SAF, "
    "LHC, LBF, LDT, LAC, "
    "HC, HCL, DT, DTL, BF, BFL, AC, ACL, "
    "SMTT, SMYTT, SRTT, SRTN, SMTN, SMYTN "
    "ORDERBY SDSD, SD "
    "WHERE S is Circular, S circ_id CI, S kind SK, "
    "S code SC, S nor NOR, S status STAT, S link SLINK, "
    "S additional_link SAL?, SAL url SALU, "
    "S siaf_daf_signing_date SDSD, S signing_date SD, "
    "S siaf_daf_kind SDK, S siaf_daf_code SDC, "
    "S producer SPD, S producer_acronym SPDC, "
    "S circular_modification_date SMD, "
    "S abrogation_date SAD, S abrogation_text SAT, "
    "S archival_field SAF, "
    'S historical_context HC?, HCL? label_of HC, HCL kind "preferred", HCL label LHC, HCL language_code "fr", '
    'S business_field BF?, BFL? label_of BF, BFL kind "preferred", BFL label LBF, BFL language_code "fr", '
    'S document_type DT?, DTL? label_of DT, DTL kind "preferred", DTL label LDT, DTL language_code "fr", '
    'S action AC?, ACL? label_of AC, ACL kind "preferred", ACL label LAC, ACL  language_code "fr", '
    "S modified_text SMT?, SMT code SMTT, SMT name SMTN, "
    "S modifying_text SMYT?, SMYT code SMYTT, SMYT name SMYTN, "
    "S revoked_text SRT?, SRT code SRTT, SRT name SRTN"
)

print("update Circular.json_values")

done = []
i = 0

with cnx.deny_all_hooks_but():
    for circular in rset.entities():
        if not circular.eid in done:
            i += 1
            done.append(circular.eid)
            circular.cw_set(json_values=circular.values_as_json)
            cnx.commit()

print(rql("Any X WHERE X is Circular").rowcount, i)

# update instagram value on SocialNetwork
sync_schema_props_perms("SocialNetwork")

# remove unused entity RelatedFindingAid
drop_entity_type("RelatedFindingAid")

cnx.system_sql("""drop table published.related_finding_aid_relation;""")
cnx.commit()

# regenerate published.related_finding_aid_relation function
from cubicweb_frarchives_edition.mviews import (
    setup_published_triggers,
    formatted_ignored_cwproperties,
)

from jinja2 import Environment, PackageLoader


def get_published_tables(cnx, skipped_etypes=(), skipped_relations=()):
    etypes = ["FindingAid"]
    rtypes = {}
    rnames = set()
    skipped_relations = ("in_state",)  # in_state is handled separately
    for etype in etypes:
        if etype in skipped_etypes:
            continue
        eschema = cnx.repo.schema[etype]
        rtypes[etype] = {}
        for rschema, targetschemas, role in eschema.relation_definitions():
            # r.rule is not None for computed relations
            if (
                rschema.final
                or rschema.inlined
                or rschema.meta
                or rschema.rule is not None
                or rschema.type in skipped_relations
            ):
                continue
            rtypes[etype].setdefault(rschema.type, []).append(role)
            rnames.add(rschema.type)
    return etypes, rtypes, rnames


def setup_published_triggers(cnx, sql=None, sqlschema="published", bootstrap=True):
    """Create (or replace) SQL triggers to handle filtered copied of CMS
    entities postgresql tables (and the resuired relations) that are
    in the wfs_cmsobject_published WF state.
    """
    if sql is None:
        sql = cnx.system_sql
    skipped_etypes = ("CWProperty", "CWUser")  # idem
    skipped_relations = ("in_state",)  # in_state is handled separately
    etypes, rtypes, rnames = get_published_tables(cnx, skipped_etypes, skipped_relations)
    env = Environment(
        loader=PackageLoader("cubicweb_frarchives_edition", "templates"),
    )
    env.filters["sqlstr"] = lambda x: "'{}'".format(x)
    template = env.get_template("published.sql")
    sqlcode = template.render(
        schema=sqlschema,
        etypes=etypes,
        rtypes=rtypes,
        rnames=rnames,
        ignored_cwproperties=formatted_ignored_cwproperties(cnx),
    )
    if sql:
        print(sqlcode)
        sql(sqlcode)


setup_published_triggers(cnx)
cnx.commit()

# sync EsDocument.entity permissions
sync_schema_props_perms("entity")

add_relation_type("fa_referenced_files")
cnx.system_sql(
    """create table published.fa_referenced_files_relation as
                  select * from public.fa_referenced_files_relation where null;"""
)
cnx.commit()

# add publication name in the right Section
rql(
    "SET X name %(n)s WHERE X is Section, X title %(e)s",
    {"e": "Publications des services d'archives", "n": "publication"},
)

# add new FA attributes

from cubicweb_francearchives.dataimport import sqlutil
from cubicweb_francearchives.dataimport.ead import ead_foreign_key_tables


def alter_published_table(table, column, attrtype):
    cnx.system_sql(
        str("ALTER TABLE published.cw_%s ADD cw_%s %s" % (table, column, attrtype)),
        rollback_on_failure=False,
    )


with sqlutil.sudocnx(cnx, interactive=False) as su_cnx:
    foreign_key_tables = ead_foreign_key_tables(cnx.vreg.schema)
    sqlutil.disable_triggers(su_cnx, foreign_key_tables)
    new_attrs = ("bioghist", "notes")
    for etype, attrs in (
        ("FindingAid", new_attrs),
        ("FAComponent", new_attrs),
    ):
        for attr in attrs:
            print("add attr %s" % attr)
            attr_fmt = "{}_format".format(attr)
            add_attribute(etype, attr)
            add_attribute(etype, attr_fmt)
            alter_published_table(etype, attr, "text")
            alter_published_table(etype, attr_fmt, "character varying(50)")
    # add string_attributes
    string_attributes = ("genreform", "function", "occupation")
    for etype, attrs in (
        ("FindingAid", string_attributes),
        ("FAComponent", string_attributes),
    ):
        for attr in attrs:
            print("add attr %s" % attr)
            add_attribute(etype, attr)
            alter_published_table(etype, attr, "text")
    cnx.commit()
    sqlutil.enable_triggers(su_cnx, foreign_key_tables)

# create `index_relation` table in `published` schema

cnx.system_sql(
    """
CREATE TABLE published.index_relation (
    eid_from integer NOT NULL,
    eid_to integer NOT NULL
);

ALTER TABLE ONLY published.index_relation
    ADD CONSTRAINT index_relation_pkey PRIMARY KEY (eid_from, eid_to);

CREATE INDEX index_eid_from_idx ON published.index_relation USING btree (eid_from);
CREATE INDEX index_eid_to_idx ON published.index_relation USING btree (eid_to);

"""
)

cnx.commit()
