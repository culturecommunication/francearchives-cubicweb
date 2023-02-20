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
"""francearchives sitemap files generator"""


# standard library imports
import logging
from io import StringIO
from datetime import date
from itertools import count

# third party imports
# CubicWeb specific imports
# library specific imports


SITEMAP_ENTRY = """ <url>
    <loc>%(loc)s</loc>
    <lastmod>%(lastmod)s</lastmod>
    <changefreq>weekly</changefreq>
 </url>
"""

LOGGER = logging.getLogger("francearchives.sitemap")


def iter_execute(req, query, chunksize=100000):
    """iterate on entities returned by ``query``

    Instead of generating all entities at once, generate resultsets
    by chunks of ``chunksize`` to limit memory consumption.

    NOTES: the function doesn't use rql syntax tree and therefore
    relies on ``X`` being the main entity variable.
    """
    selection, restrictions = query.split(" WHERE ")
    query = "{} ORDERBY X LIMIT {} WHERE {}, X eid > %(last)s".format(
        selection, chunksize, restrictions
    )
    last_eid = 0
    for loop_idx in count():
        req.drop_entity_cache()
        LOGGER.info(
            "executing %s [%s - %s]", query, loop_idx * chunksize, (loop_idx + 1) * chunksize
        )
        rset = req.execute(query, {"last": last_eid})
        if not rset:
            return
        for entity in rset.entities():
            yield entity
        last_eid = rset[-1][0]


def iter_entities(req):
    """generate all entities that should appear in the sitemap"""
    queries = [
        "Any X, S, M WHERE X is FindingAid, X stable_id S, X modification_date M",
        "Any X, S, M WHERE X is FAComponent, X stable_id S, X modification_date M",
        "Any X, I, M WHERE X is Circular, X circ_id I, X modification_date M",
        "Any X, M WHERE X is NewsContent, X modification_date M",
        "Any X, M WHERE X is BaseContent, X modification_date M",
        "Any X, Y, M WHERE X is CommemorationItem, X commemoration_year Y, X modification_date M",
        "Any X, L, D, M WHERE X is Service, X level L, X dpt_code D, X modification_date M",
        "Any X, M WHERE X is LocationAuthority, X modification_date M",
        "Any X, M WHERE X is AgentAuthority, X modification_date M",
        "Any X, M WHERE X is SubjectAuthority, X modification_date M",
    ]
    for query in queries:
        for entity in iter_execute(req, query):
            yield entity


def init_sitemap_buffer():
    buf = StringIO()
    header = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">"""
    buf.write(header)
    return buf, len(header)


def generate_sitemaps(req, size_threshold=10 * 1000 * 1000, nb_entries_threshold=50000):
    buf, size = init_sitemap_buffer()
    nb_entries = 0
    for entity in iter_entities(req):
        # encode in utf-8 here to have the exact size
        sitemap_entry = SITEMAP_ENTRY % {
            "loc": entity.absolute_url(),
            "lastmod": entity.modification_date.strftime("%Y-%m-%d"),
        }
        size += len(sitemap_entry)
        if nb_entries >= nb_entries_threshold or size >= size_threshold:
            buf.write("\n</urlset>")
            yield buf
            buf, size = init_sitemap_buffer()
            nb_entries = 0
        buf.write(sitemap_entry)
        nb_entries += 1
    if size:
        buf.write("\n</urlset>")
        yield buf


def coroutine(func):
    def start(*args, **kwargs):
        coro = func(*args, **kwargs)
        next(coro)
        return coro

    return start


@coroutine
def sitemap_index_writer(storage, output_dir, baseurl):
    sitemaps = []
    try:
        buf = StringIO()
        buf.write(
            """<?xml version="1.0" encoding="UTF-8"?>
    <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    """
        )
        while True:
            sitemap = yield
            sitemaps.append("Sitemap: {}{}".format(baseurl, sitemap))
            buf.write(
                """  <sitemap>
        <loc>%s%s</loc>
        <lastmod>%s</lastmod>
     </sitemap>
"""
                % (baseurl, sitemap, date.today().strftime("%Y-%m-%d"))
            )
    except GeneratorExit:
        buf.write("</sitemapindex>")
        index_filename = "sitemap_index.xml"
        storage.storage_write_sitemap_ini_file(index_filename, output_dir, buf)
        sitemaps.insert(0, "Sitemap: {}{}/{}".format(baseurl, output_dir, index_filename))
        rbuf = StringIO()
        rbuf.write(
            """User-agent: *
Disallow: /fr/search
Disallow: /en/
Disallow: /es/
Disallow: /de/

%s
"""
            % "\n".join(sitemaps)
        )
        storage.storage_write_sitemap_ini_file("robots.txt", output_dir, rbuf)


def dump_sitemaps(
    req, storage, output_dir, size_threshold=10 * 1000 * 1000, nb_entries_threshold=50000
):
    index_writer = sitemap_index_writer(storage, output_dir, req.base_url())
    for index, buf in enumerate(generate_sitemaps(req, size_threshold, nb_entries_threshold)):
        basename = "sitemap%s.xml.gz" % (index + 1)
        storage.storage_write_gz_file(basename, buf, output_dir)
        if storage.s3_bucket:
            index_writer.send(f"{output_dir}/{basename}")
            print(f"write {output_dir}/{basename}")
        else:
            index_writer.send(basename)


def generate(cnx):
    tmpdir = cnx.vreg.config.get("sitemap-dir")
    print("generating sitemaps in", tmpdir)
    dump_sitemaps(cnx, tmpdir)


if __name__ == "__main__":  # if used with cubicweb-ctl shell
    if "cnx" in globals():
        run(cnx)  # noqa
    else:
        print("sitemap.py must be used in cubciweb-ctl shell context")
