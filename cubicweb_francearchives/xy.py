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
from rdflib import URIRef, Literal, Namespace, ConjunctiveGraph
from rdflib import term

from cubicweb.xy import xy

# try to register jsonld plugin
try:
    import rdflib_jsonld  # noqa
    from rdflib.plugin import register, Serializer

    register("jsonld", Serializer, "rdflib_jsonld.serializer", "JsonLDSerializer")
except ImportError:
    pass

namespaces = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "dcmitype": "http://purl.org/dc/dcmitype/",
    "dcterms": "http://purl.org/dc/terms/",
    "owl": "http://www.w3.org/2002/07/owl#",
    "schema": "http://schema.org/",
    "edm": "http://www.europeana.eu/schemas/edm/",
    "ore": "http://www.openarchives.org/ore/terms/",
    "rdaGr2": "http://rdvocab.info/ElementsGr2",
    "crm": "http://www.cidoc-crm.org/rdfs/cidoc_crm_v5.0.2_english_label.rdfs#",
}


NS_VARS = {ns: Namespace(uri) for ns, uri in list(namespaces.items())}


class VocabAdapter(object):
    def __init__(self):
        self.adapter_cache = {}

    def adapt(self, entity, vocab):
        adapter = None
        cache_key = (entity.__regid__, vocab)
        if cache_key in self.adapter_cache:
            adaptercls = self.adapter_cache[cache_key]
            # adaptercls = None means no adapter for this vocabulary
            if adaptercls is not None:
                adapter = adaptercls(entity._cw, entity=entity)
        else:
            adapter = entity.cw_adapt_to(vocab)
            adaptercls = adapter.__class__ if adapter is not None else None
            self.adapter_cache[cache_key] = adaptercls
        return adapter


def conjunctive_graph():
    """factory to build a ``ConjunctiveGraph`` and bind all namespaces
    """
    graph = ConjunctiveGraph()
    for vocab, rdfns in list(NS_VARS.items()):
        graph.bind(vocab, rdfns)
    return graph


def register_prefixes():
    for prefix, uri in list(namespaces.items()):
        xy.register_prefix(prefix, uri, overwrite=True)


def add_statements_to_graph(graph, rdf_adapter):
    add = graph.add
    for subj, rvocab, propname, obj, prop_props in rdf_adapter.statements():
        if prop_props is None:  # XXX this means it's a relation
            # safety belt around malformed uris that might be found
            # in catalogues / dlweb / etc. (cf. #3072330)
            if term._is_valid_uri(obj):
                add((URIRef(subj), getattr(NS_VARS[rvocab], propname), URIRef(obj)))
        else:
            # Don't generate rdf statement with unspecified value
            if obj is not None and obj != "":
                add((URIRef(subj), getattr(NS_VARS[rvocab], propname), Literal(obj, **prop_props)))
