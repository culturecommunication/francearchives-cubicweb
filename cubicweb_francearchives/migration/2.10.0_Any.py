# -*- coding: utf-8 -*-
#
# flake8: noqa
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2020
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


# standard library imports
import os.path as osp

# third party imports
# CubicWeb specific imports
from cubicweb import Binary

# library specific imports
from cubicweb_francearchives.migration.import_site_links import import_site_links
from cubicweb_francearchives.migration.import_glossary import import_glossary

from cubicweb_francearchives.migration.utils import (
    add_column_to_published_table,
    drop_column_from_published_table,
)

from cubicweb_francearchives.cssimages import static_css_dir

print("-> add BaseContent.content_type")

add_column_to_published_table(cnx, "basecontent", "content_type", "character varying(128)")

add_attribute("BaseContent", "content_type")

commit()

# update data : published data will be modified as well

print("-> update Articles")

with cnx.allow_all_hooks_but("on_frontpage"):
    rql(
        """SET B content_type %(p)s WHERE X is Section, X name %(n)s, NOT X children B, B is BaseContent""",
        {"n": "publication", "p": "Article"},
    )

    rql(
        """SET B content_type %(p)s WHERE X is Section, X name %(n)s, X children B, B is BaseContent""",
        {"n": "publication", "p": "Publication"},
    )
    commit()

print("-> create section Rechercher")

# Create section rechercher if it does not exist
rset = rql("Any X WHERE X is Section, X name 'rechercher'")

if len(rset) == 0:
    cnx.execute("INSERT Section X: X name 'rechercher', X title 'Rechercher', X order 3")
    cnx.commit()

print("-> create section SiteLinks")

# add and process SiteLinks

add_entity_type("SiteLink")

import_site_links(cnx)

cnx.commit()

print("-> add header, on_homepage, on_homepage_order attributes)")

# Add or update header
for etype in (
    "BaseContent",
    "BaseContentTranslation",
    "CommemorationItem",
    "CommemorationItemTranslation",
    "Section",
    "SectionTranslation",
):
    add_column_to_published_table(cnx, etype.lower(), "header", "character varying(500)")
    add_attribute(etype, "header")

sync_schema_props_perms("NewsContent")

# add on_homepage_order

sync_schema_props_perms("CommemorationItem")
sync_schema_props_perms("Section")

for etype in ("BaseContent", "NewsContent", "Section"):
    add_column_to_published_table(cnx, etype.lower(), "on_homepage_order", "integer")
    add_attribute(etype, "on_homepage_order")


ON_FRONTPAGE = []

for query in [
    "Any X  LIMIT 1 WHERE X is BaseContent, X on_homepage True",
    """Any X ORDERBY SA DESC LIMIT 7 WHERE X is NewsContent,
           X start_date SA, X on_homepage TRUE""",
    """Any X ORDERBY O LIMIT 10 WHERE
           X is CommemorationItem,
          X on_homepage True, X on_homepage_order O""",
]:
    ON_FRONTPAGE.extend([rset[0] for rset in rql(query)])

for etype in ("BaseContent", "NewsContent", "CommemorationItem"):
    drop_column_from_published_table(cnx, etype.lower(), "on_homepage")
    drop_attribute(etype, "on_homepage")
    commit()
    add_column_to_published_table(cnx, etype.lower(), "on_homepage", "character varying(11)")
    add_attribute(etype, "on_homepage")
    commit()

for etype in ("Section",):
    add_column_to_published_table(cnx, etype.lower(), "on_homepage", "character varying(11)")
    add_attribute(etype, "on_homepage")
    commit()

with cnx.allow_all_hooks_but("on_frontpage"):
    rql(
        """SET X on_homepage "onhp_hp" WHERE X eid IN (%s)"""
        % ", ".join([str(eid) for eid in ON_FRONTPAGE])
    )

commit()

print("-> Create a cssimage for rechercher section based on comprendre section")

# Create a cssimage for "rechercher" based on comprendre section
static_dir = static_css_dir(cnx.vreg.config.static_directory)
with open(osp.join(static_dir, "hero-comprendre-lg.jpg"), "rb") as stream:
    section = rql("Any X WHERE X is Section, X name 'rechercher'").one()
    fobj = cnx.create_entity(
        "File",
        data=Binary(stream.read()),
        data_name="hero-rechercher.jpg",
        data_format="image/jpg",
    )
    css_image = cnx.create_entity(
        "CssImage",
        cssid="hero-rechercher",
        order=3,
        caption="<p>image-caption</p>",
        image_file=fobj,
        cssimage_of=section,
    )
    cnx.commit()

print("-> remove CommemoCollection from es indexes")

from cubicweb_francearchives.migration.utils import delete_from_es_by_etype

delete_from_es_by_etype(cnx, "CommemoCollection")

print("-> Create translate_entity function")

TRANSLATE_ENTITY_QUERY = r"""
CREATE OR REPLACE FUNCTION translate_entity(eid int, attr varchar, lang varchar)
RETURNS varchar AS $$
DECLARE
    etype varchar;
    label varchar;
    label_lang varchar;
BEGIN
    EXECUTE format('SELECT _E.cw_name FROM cw_CWEType AS _E, is_relation AS rel_is0
                    WHERE rel_is0.eid_from=%s and rel_is0.eid_to=_E.cw_eid ', eid) INTO etype ;
    EXECUTE format('SELECT cw_%s FROM cw_%s WHERE cw_eid=%s', attr, etype, eid) INTO label ;
    IF lang = 'fr' THEN
        RETURN label;
    END IF;
    IF etype  = ANY ('{Section, BaseContent, CommemorationItem, FaqItem}'::varchar[]) THEN
        EXECUTE format('SELECT cw_%s FROM cw_%sTranslation WHERE cw_translation_of=%s AND cw_language=''%s''', attr, etype, eid, lang) INTO label_lang ;
        IF label_lang is NOT NULL THEN
           RETURN label_lang;
        END IF;
    END IF;
 RETURN label;
END;
$$ LANGUAGE plpgsql;
    """

cnx.system_sql(TRANSLATE_ENTITY_QUERY)
cnx.commit()

print("-> import GlossaryTerms")

import_glossary(cnx)

cnx.commit()
