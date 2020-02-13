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


from itertools import chain
from datetime import datetime
import os.path
import tarfile

from logilab.common.shellutils import progress

from cubicweb_francearchives.xy import add_statements_to_graph, conjunctive_graph


ETYPES_ADAPTERS = {
    "FindingAid": ("rdf.schemaorg", "rdf.em"),
    "FAComponent": ("rdf.schemaorg", "rdf.em"),
    "BaseContent": ("rdf.schemaorg",),
    "NewsContent": ("rdf.schemaorg",),
    "CommemoCollection": ("rdf.schemaorg",),
    "CommemorationItem": ("rdf.schemaorg",),
    "Service": ("rdf.schemaorg",),
}


def iter_rdf_adapters(entity):
    for adapter_id in ETYPES_ADAPTERS.get(entity.__regid__):
        adapter = entity.cw_adapt_to(adapter_id)
        if adapter:
            yield adapter


def add_entity_to_graph(graph, entity, build_dump=False, adapter_cache=None):
    rdf_adapters = [iter_rdf_adapters(entity)]
    for adapter in chain(*rdf_adapters):
        add_statements_to_graph(graph, adapter)


def _add_etype_to_graph(cnx, graph, etype, limit, offset, pb=None):
    rql = "Any X ORDERBY X LIMIT %s OFFSET %s WHERE X is %s" % (limit, offset, etype)
    rset = cnx.execute(rql)
    # Construct graph
    for entity in rset.entities():
        add_entity_to_graph(graph, entity, build_dump=True)
        if pb:
            pb.update()


def create_dumps_etype(cnx, output_dir, etype, formats, chunksize=2000):
    nb_entities = cnx.execute("Any COUNT(X) WHERE X is %s" % etype)[0][0]
    filenames = []
    with progress(nb_entities, title="found %s %s" % (nb_entities, etype)) as pb:
        pb.refresh()
        for offset in range(0, nb_entities, chunksize):
            graph = conjunctive_graph()
            _add_etype_to_graph(cnx, graph, etype, chunksize, offset, pb)
            for _format in formats:
                filename = "%s_%06d.%s" % (etype.lower(), offset, _format)
                filepath = os.path.join(output_dir, filename)
                with open(filepath, "ab") as dump_file:
                    dump_file.write(graph.serialize(format=_format))
                filenames.append(filepath)
            # clean as much as possible to avoid memory exhaustion
            cnx.drop_entity_cache()
    return filenames


def make_archive(output_dir, label, filenames, formats):
    for _format in formats:
        archive_name = "%s_%s.tar.gz" % (label, _format)
        with tarfile.open(os.path.join(output_dir, archive_name), "w:gz") as tar:
            for filename in filenames:
                # add file but specify basename as the alternative filename
                # to avoid nested directory structure in the archive
                tar.add(filename, arcname=os.path.basename(filename))
                # os.remove(filename)


def create_dumps(cnx, config):
    output_dir = config.get("output-dir")
    formats = config.get("formats")
    etypes = config.get("etypes")
    date = datetime.now().strftime("%Y%m%d")
    output_dir = os.path.join(output_dir, date)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    for etype in etypes:
        filenames = create_dumps_etype(cnx, output_dir, etype, formats)
        make_archive(output_dir, etype.lower(), filenames, formats)
