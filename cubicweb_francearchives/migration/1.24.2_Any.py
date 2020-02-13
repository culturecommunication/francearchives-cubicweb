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
for old, new in rql("Any OLD, NEW WHERE REL related_authority OLD, OLD grouped_with NEW"):
    kwargs = {"old": old, "new": new}
    # redirect related ExternRefs and CommemorationItems from old authority to new authority
    cnx.execute(
        """SET E related_authority NEW WHERE NEW eid %(new)s,
        E related_authority OLD, OLD eid %(old)s""",
        kwargs,
    )
    # delete related ExternRefs and CommemorationItems from old authority
    cnx.execute("""DELETE E related_authority OLD WHERE OLD eid %(old)s""", kwargs)

cnx.system_sql(
    r"""
CREATE OR REPLACE FUNCTION normalize_entry(entry varchar)
RETURNS varchar AS $$
DECLARE
        normalized varchar;
BEGIN
 normalized := regexp_replace(entry, '\(\s*[\d.]+\s*-\s*[\d.]+\s*\)', '');
 normalized := translate(normalized, E'!"#$%&()*+,-./:;<=>?@[\\]^_`{|}~\'', '');
 normalized := translate(normalized, E'\xc2\xa0\xc2\xb0\u2026\u0300\u0301', ' _.__');
 normalized := btrim(unaccent(lower(normalized)));

 SELECT string_agg(T.word, ' ') INTO normalized
 FROM (SELECT unnest(string_to_array(normalized, ' ')) AS word ORDER BY 1) AS T;

 RETURN btrim(normalized);
END;
$$ LANGUAGE plpgsql;
"""
)
