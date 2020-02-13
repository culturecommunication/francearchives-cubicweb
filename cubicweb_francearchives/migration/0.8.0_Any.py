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
from cubicweb_francearchives.migration import migr_080


def fix_hero_labels(cnx):
    """Fix text source shown on the hero image"""

    with cnx.allow_all_hooks_but("es", "sync", "varnish"):
        res = rql(
            "Any X "
            'WHERE  X is CssImage, X cssid LIKE "hero-%%", '
            "       X cssid I, X copyright R"
        )

        for hero in res.entities():
            if hero.cssid == "hero-comprendre":
                hero.cw_set(copyright="Source : Archives de la Vienne")
            if hero.cssid == "hero-gerer":
                hero.cw_set(copyright="Source : Archives de la Vienne")
            if hero.cssid == "hero-decouvrir":
                hero.cw_set(copyright="Source : Archives Nationales")

        cnx.commit()


if __name__ == "__main__":
    if confirm("fix illustration url? [Y/n]"):
        migr_080.fix_illustration_urls(cnx, sql)

    if confirm("rewrite CMS content URLs ? [Y/n]"):
        migr_080.rewrite_cms_content_urls(cnx)

    if confirm("Fix hero sources ? [Y/n]"):
        fix_hero_labels(cnx)
