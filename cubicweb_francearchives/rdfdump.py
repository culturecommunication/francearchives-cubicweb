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

import boto3
from collections import defaultdict
from datetime import datetime
from itertools import chain
import logging
import multiprocessing as mp
from optparse import OptionParser
import os
import os.path
import tarfile
import sys

from logilab.common.decorators import timed
from rdflib.graph import ConjunctiveGraph

from cubicweb.entity import Relation

from cubicweb_francearchives import admincnx
from cubicweb_francearchives.xy import add_statements_to_graph
from cubicweb_francearchives.storage import S3BfssStorageMixIn


AWS_S3_RDF_BUCKET_NAME = os.environ.get("AWS_S3_RDF_BUCKET_NAME")
if AWS_S3_RDF_BUCKET_NAME is None:
    AWS_S3_RDF_BUCKET_NAME = "rdf"

ETYPES_ADAPTERS = {
    "FindingAid": ("rdf",),
    "FAComponent": ("rdf",),
    "AgentAuthority": ("rdf",),
    "LocationAuthority": ("rdf",),
    "SubjectAuthority": ("rdf",),
    "AuthorityRecord": ("rdf",),
    "Service": ("rdf",),
}


class FSRDFStorge:
    def __init__(self, output_dir, logger):
        self.output_dir = output_dir
        self.logger = logger
        self.storage = S3BfssStorageMixIn(log=self.logger)
        # force bfss
        self.storage.s3_bucket = False
        self.backuped_name = None

    def prepare_storage(self, options):
        if not os.path.exists(self.output_dir):
            self.logger.info(f"[fs_storage]: Create {self.output_dir}")
            os.makedirs(self.output_dir)
        self.logger.info(f"[fs_storage]: Rdf dumps will be stored in '{self.output_dir}'")

    def get_filepath(self, etype, offset, _format):
        filepath = "%s_%06d.%s" % (etype.lower(), offset, _format)
        filepath = os.path.join(self.output_dir, filepath)
        self.logger.info(f"[fs_storage]: Write {filepath}")
        return filepath


class S3RDFStorge:
    def __init__(self, logger):
        self.logger = logger
        self.s3_bucket = AWS_S3_RDF_BUCKET_NAME
        self._s3_resource = None
        self.storage = S3BfssStorageMixIn(bucket_name=self.s3_bucket, log=self.logger)
        self.backuped_name = None

    @property
    def s3_resource(self):
        if self._s3_resource is None:
            endpoint_url = os.environ.get("AWS_S3_ENDPOINT_URL")
            if endpoint_url:
                self.logger.debug(
                    "[s3_resource]: Using custom S3 endpoint url {}".format(endpoint_url)
                )
            self._s3_resource = boto3.resource("s3", endpoint_url=endpoint_url)
        return self._s3_resource

    def get_buckets_list(self):
        response = self.storage.s3.s3cnx.list_buckets()
        if response["ResponseMetadata"]["HTTPStatusCode"] == 200:
            if "Buckets" not in response:
                self.logger.error(
                    "[get_buckets_list]: No information about existing s3 buckets "
                    "could be retrieved"
                )
                sys.exit(1)
        list_buckets = [obj["Name"] for obj in response["Buckets"]]
        return list_buckets

    def delete_bucket(self, bucket_name):
        self.logger.info(f'[delete_bucket]: Delete "{bucket_name}" bucket')
        self.empty_bucket(bucket_name)
        bucket = self.s3_resource.Bucket(bucket_name)
        bucket.delete()

    def empty_bucket(self, bucket_name):
        self.logger.info(f'[empty_bucket]: Empty "{bucket_name}" bucket')
        response = self.storage.s3.s3cnx.list_objects(Bucket=bucket_name)
        if "Contents" in response:
            for key in self.storage.s3.s3cnx.list_objects(Bucket=bucket_name)["Contents"]:
                self.storage.s3.s3cnx.delete_object(Bucket=bucket_name, Key=key["Key"])

    def rename_bucket(self, bucket_name, new_bucket_name=None, create=True):
        """Is there a simplier way to do this ?"""
        bucket = self.s3_resource.Bucket(bucket_name)
        date = bucket.creation_date.strftime("%Y%m%d%H%M")
        new_bucket_name = new_bucket_name or f"{bucket_name}-{date}"
        if new_bucket_name in self.get_buckets_list():
            self.logger.warning(
                f'[rename_bucket]: The new "{new_bucket_name}" bucket already exists, delete it'
            )
            self.delete_bucket(new_bucket_name)
        self.logger.info(f'(rename_bucket]: Rename "{bucket_name}" into "{new_bucket_name}"')
        is_old = bucket_name in self.get_buckets_list()
        if is_old:
            self.logger.info(
                f'[rename_bucket]: The "{bucket_name}" bucket already exists, '
                f'rename it into "{new_bucket_name}"'
            )
        else:
            self.logger.info(f'[rename_bucket]: "{bucket_name}" bucket doesn\'t exist')
        self.logger.info(f'[rename_bucket]: Create the new "{new_bucket_name}"')
        self.storage.s3.s3cnx.create_bucket(Bucket=new_bucket_name)
        result = self.storage.s3.s3cnx.list_objects(Bucket=bucket_name)
        if "Contents" in result:
            for key in self.storage.s3.s3cnx.list_objects(Bucket=bucket_name)["Contents"]:
                key_name = key["Key"]
                self.storage.s3.s3cnx.copy_object(
                    Bucket=new_bucket_name, CopySource=f"{bucket_name}/{key_name}", Key=key_name
                )
                self.storage.s3.s3cnx.delete_object(Bucket=bucket_name, Key=key_name)
        if is_old:
            # delete the old bucket
            self.logger.info(f'[rename_bucket]: Delete the empty old "{bucket_name}"')
            bucket.delete()
        return new_bucket_name

    def prepare_storage(self, options):
        self.storage = S3BfssStorageMixIn(bucket_name=self.s3_bucket, log=self.logger)
        if self.storage.s3_bucket in self.get_buckets_list():
            if options.get("s3db"):
                try:
                    self.delete_bucket(self.storage.s3_bucket)
                except Exception as ex:
                    self.logger.error(f"[s3 storage]: Abort: {ex}")
                    sys.exit(1)
            if options.get("s3rb"):
                try:
                    new_bucket_name = self.rename_bucket(self.storage.s3_bucket)
                    self.backuped_name = new_bucket_name
                except Exception as ex:
                    self.logger.error(f"[s3 storage]: Abort: {ex}")
                    sys.exit(1)
        if self.storage.s3_bucket not in self.get_buckets_list():
            self.logger.info(f"[s3 storage]: Creating {self.storage.s3_bucket} bucket")
            self.storage.s3.s3cnx.create_bucket(Bucket=self.storage.s3_bucket)
        self.logger.info(f"[s3 storage]: Generating dumps in '{self.storage.s3_bucket}' bucket")

    def get_filepath(self, etype, offset, _format):
        filepath = "%s_%06d.%s" % (etype.lower(), offset, _format)
        self.logger.info(f"[s3 storage]: Write {filepath} in '{self.storage.s3_bucket}' bucket")
        return filepath


class BaseRDFCacher:
    etype = None
    fetch_all_rql = None

    def build_query(self, query=None):
        query = query or self.fetch_all_rql
        if query is None:
            raise NotImplementedError()
        selection, restrictions = query.split("WHERE")
        query = query or self.fetch_all_rql
        selection, restrictions = query.split("WHERE")
        query = "%s ORDERBY X LIMIT %%s OFFSET %%s WHERE %s" % (
            selection,
            restrictions,
        )
        return query

    def setup_iteration_cache(self, cnx, rset):
        pass


class ArchivesRDFCacher(BaseRDFCacher):
    def digitized_versions_cache(self, cnx, entities):
        set_entity_cache(
            cnx,
            self.etype,
            entities,
            "Any X, E, IU, U WHERE E is DigitizedVersion, E url U, "
            "E illustration_url IU, X digitized_versions E",
            "digitized_versions",
        )

    def did_cache(self, cnx, entities):
        set_entity_cache(
            cnx,
            self.etype,
            entities,
            "Any X, E, T, U, S, P, O, PHL, PHD  WHERE X did E, E is Did, "
            "E unitid U, E unittitle T, E startyear S, E stopyear P, "
            "E origination O, E physloc PHL, E physdesc PHD",
            "did",
        )


class FindinAidRDFCacher(ArchivesRDFCacher):
    # XXX remove description, all_format, notes
    etype = "FindingAid"
    fetch_all_rql = (
        "Any X,B,C,D,E,F,G,H,I,J,K,L,M,N,O,P,Q,R,S,T,U,V,W,Y,Z,AA,AB,AC,AD,AE,AF,AG,AH,AI "
        "WHERE X is FindingAid,X name B,X eadid C,X publisher D,X fatype E, "
        "X description F,X description_format G,X accessrestrict H, "
        "X accessrestrict_format I,X userestrict J,X userestrict_format K, "
        "X acquisition_info L,X acquisition_info_format M,X additional_resources N, "
        "X additional_resources_format O,X bibliography P,X bibliography_format Q, "
        "X keywords R,X bioghist S,X bioghist_format T,X notes U,X notes_format V, "
        "X scopecontent W,X scopecontent_format Y,X stable_id Z,X website_url AA, "
        "X cwuri AB,X modification_date AC,X creation_date AD,X fa_header AE?, "
        "X service AF?,X did AG?,X findingaid_support AH?,X ape_ead_file AI?"
    )

    def service_cache(self, cnx, entities):
        set_entity_cache(
            cnx,
            self.etype,
            entities,
            "Any X, E, C WHERE X service E, E is Service, E code C",
            "related_service",
            first_entity_factory,
        )

    def faheader_cache(self, cnx, entities):
        set_entity_cache(
            cnx,
            self.etype,
            entities,
            "Any X, E, T, U WHERE X fa_header E, E is FAHeader, " "E lang_code U, E titleproper T",
            "fa_header",
        )

    def setup_iteration_cache(self, cnx, rset):
        entities = dict((e.eid, e) for e in rset.entities())
        self.digitized_versions_cache(cnx, entities)
        self.did_cache(cnx, entities)
        self.faheader_cache(cnx, entities)
        self.service_cache(cnx, entities)


class FAComponentRDFCacher(ArchivesRDFCacher):
    # XXX remove description, all_format, notes
    etype = "FAComponent"
    fetch_all_rql = (
        "Any X,B,C,D,E,F,G,H,I,J,K,L,M,N,O,P,Q,R,S,T,U,V,W,MD,Y,Z,AA "
        "WHERE X is FAComponent, X description B, X description_format C, "
        "X bibliography D, X bibliography_format E, X accessrestrict F, "
        "X accessrestrict_format G, X userestrict H, X userestrict_format I, "
        "X acquisition_info J, X acquisition_info_format K, X additional_resources L, "
        "X additional_resources_format M, X bioghist N, X bioghist_format O, "
        "X notes P, X notes_format Q, X scopecontent R, X scopecontent_format S, "
        "X stable_id T, X component_order U, X creation_date V, X cwuri W, "
        "X modification_date MD, X did Y?, X parent_component Z?, X finding_aid AA?"
    )

    def service_cache(self, cnx, entities):
        set_entity_cache(
            cnx,
            self.etype,
            entities,
            "Any X, E, C WHERE X finding_aid F, F service E, E is Service, E code C",
            "related_service",
            first_entity_factory,
        )

    def findingaid_cache(self, cnx, entities):
        set_entity_cache(
            cnx,
            self.etype,
            entities,
            "Any X, E, C WHERE  X finding_aid E, E stable_id C",
            "finding_aid",
        )

    def parent_cache(self, cnx, entities):
        set_entity_cache(
            cnx,
            self.etype,
            entities,
            "Any X, E, C WHERE X parent_component E, E stable_id C",
            "parent_component",
        )

    def setup_iteration_cache(self, cnx, rset):
        entities = dict((e.eid, e) for e in rset.entities())
        self.digitized_versions_cache(cnx, entities)
        self.did_cache(cnx, entities)
        self.service_cache(cnx, entities)
        self.findingaid_cache(cnx, entities)
        self.parent_cache(cnx, entities)


class AuthorityRecordRDFCacher(BaseRDFCacher):
    etype = "AuthorityRecord"
    fetch_all_rql = (
        "Any X,B,C,D,E,F,G,H,I,J,K,L WHERE X is AuthorityRecord, X record_id B, "
        "X isni C, X start_date D, X languages E, X end_date F, X xml_support G, "
        "X cwuri H, X modification_date I, X creation_date J, "
        "X maintainer K?, X agent_kind L? "
    )

    def same_as_agent_cache(self, cnx, entities):
        set_entity_cache(
            cnx,
            self.etype,
            entities,
            "Any X, A, L, B, C, Q, MD, CD, E LIMIT 1 WHERE X is AuthorityRecord, "
            "A same_as X, A is AgentAuthority, A quality True, A quality Q, "
            "A label L, A birthyear B, A deathyear C, "
            "A modification_date MD, A creation_date CD,A cwuri E",
            "qualified_authority",
        )

    def activity_cache(self, cnx, entities):
        set_entity_cache(
            cnx,
            self.etype,
            entities,
            "Any X, A, TYPE, START, END, AGENTTYPE, AGENT, DESCR, B, C, D, E, F WHERE"
            "A is Activity, A generated X, X is AuthorityRecord, "
            "A type TYPE, A start START, A end END, A agent_type AGENTTYPE,"
            "A agent AGENT, A description DESCR, A description_format B, "
            "A cwuri C, A modification_date D, A creation_date E, A used F?",
            "activities",
        )

    def sources_cache(self, cnx, entities):
        set_entity_cache(
            cnx,
            self.etype,
            entities,
            "Any X, S, T, U WHERE"
            "S is EACSource, S source_agent X, X is AuthorityRecord, "
            "S title T, S url U",
            "sources",
        )

    def setup_iteration_cache(self, cnx, rset):
        entities = dict((e.eid, e) for e in rset.entities())
        self.same_as_agent_cache(cnx, entities)
        self.activity_cache(cnx, entities)
        self.sources_cache(cnx, entities)


class AuthorityRDFCacher(BaseRDFCacher):
    fetch_all_rql = None

    def same_as_external_cache(self, cnx, entities):
        set_entity_cache(
            cnx,
            self.etype,
            entities,
            "Any X, E, U WHERE X same_as E, E is ExternalUri, E uri U",
            "same_as",
        )

    def same_as_concept_cache(self, cnx, entities):
        set_entity_cache(
            cnx,
            self.etype,
            entities,
            "Any X, E, U WHERE X same_as E, E is Concept, E cwuri U",
            "same_as",
        )

    def setup_iteration_cache(self, cnx, rset):
        entities = dict((e.eid, e) for e in rset.entities())
        query = """DISTINCT Any X, TYPE WHERE X is AgentAuthority,
                   I is AgentName, I authority X, I type TYPE"""
        _cache_index_types_info(cnx, "AgentAuthority", entities, query)
        self.same_as_external_cache(cnx, entities)


class AgentAuthorityRDFCacher(AuthorityRDFCacher):
    etype = "AgentAuthority"
    fetch_all_rql = (
        "Any X,B,C,D,E,F,G,H WHERE X is AgentAuthority, X birthyear B, "
        "X deathyear C,X quality D, X quality True, X label E, "
        "X modification_date F,X creation_date G,X cwuri H"
    )

    def same_as_agent_cache(self, cnx, entities):
        set_entity_cache(
            cnx,
            self.etype,
            entities,
            "Any X, E, R WHERE X same_as E, E is AuthorityRecord, E record_id R",
            "same_as",
        )

    def setup_iteration_cache(self, cnx, rset):
        entities = dict((e.eid, e) for e in rset.entities())
        query = """DISTINCT Any X, TYPE WHERE X is AgentAuthority,
                   I is AgentName, I authority X, I type TYPE"""
        _cache_index_types_info(cnx, "AgentAuthority", entities, query)
        self.same_as_external_cache(cnx, entities)
        self.same_as_agent_cache(cnx, entities)


class SubjectAuthorityRDFCacher(AuthorityRDFCacher):
    etype = "SubjectAuthority"
    fetch_all_rql = (
        "Any X,D,E,F,G,H WHERE X is SubjectAuthority, X quality D, "
        "X quality True, X label E,X modification_date F, "
        "X creation_date G,X cwuri H"
    )


class LocationAuthorityRDFCacher(AuthorityRDFCacher):
    etype = "LocationAuthority"
    fetch_all_rql = (
        "Any X,D,E,LO,LA,F,G,H WHERE X is LocationAuthority, X quality D, "
        "X quality True, X label E, X longitude LO, X latitude LA, "
        "X modification_date F, X creation_date G,X cwuri H"
    )

    def setup_iteration_cache(self, cnx, rset):
        entities = dict((e.eid, e) for e in rset.entities())
        query = """DISTINCT Any X, TYPE WHERE X is AgentAuthority,
                   I is AgentName, I authority X, I type TYPE"""
        _cache_index_types_info(cnx, "AgentAuthority", entities, query)
        self.same_as_external_cache(cnx, entities)


class ServiceRDFCacher(BaseRDFCacher):
    etype = "Service"
    fetch_all_rql = (
        "Any X,B,C,D,E,F,G,H,I,J,K,L,M,N,O,P,Q,R,S,T,U,V,W,XX,Y,Z,AA,AB,AC,AD WHERE "
        "X is Service, X category B, X name C, X name2 D, X short_name E, "
        "X phone_number F, X code_insee_commune G, X email H, X address I, "
        "X mailing_address J, X zip_code K, X city L, X website_url M, "
        "X search_form_url N, X thumbnail_url O, X thumbnail_dest P, X annual_closure Q,"
        "X opening_period R, X contact_name S, X level T, X code U, "
        "X longitude V, X latitude W, X dpt_code XX, X other Y, X other_format Z, "
        "X uuid AA, X cwuri AB, X creation_date AC, X modification_date AD"
        ""
    )


CACHER_CLASSES = {
    "findingaid": FindinAidRDFCacher,
    "facomponent": FAComponentRDFCacher,
    "agentauthority": AgentAuthorityRDFCacher,
    "subjectauthority": SubjectAuthorityRDFCacher,
    "locationauthority": LocationAuthorityRDFCacher,
    "authorityrecord": AuthorityRecordRDFCacher,
    "service": ServiceRDFCacher,
}


def _ecache_factory(rset, rows):
    return [rset.get_entity(rowidx, 1) for rowidx, row in rows]


def _grouped_rset(entities, rset):
    no_relation_eids = set(entities)
    related = defaultdict(list)
    for rowidx, row in enumerate(rset):
        related[row[0]].append((rowidx, row))
    no_relation_eids -= set(related)
    return related, no_relation_eids


def _unbind_orm_relation(eclass, rtype):
    # rtype descriptor might have been removed in a previous iteration
    if isinstance(eclass.__dict__.get(rtype), Relation):
        delattr(eclass, rtype)


def _cache_index_types_info(cnx, etype, entities, query):
    with_being = (
        ", X identity X2 WITH X2 BEING "
        "(Any X ORDERBY X LIMIT {0} WHERE X is {1}, "
        "X eid >= %(x)s)".format(len(entities), etype)
    )
    rset = cnx.execute(query + with_being, {"x": min(entities)})
    related, no_relation_eids = _grouped_rset(entities, rset)
    cachekey = "index_types"
    for main_entity_eid, rows in related.items():
        entity = cnx.entity_from_eid(main_entity_eid)
        entity.__dict__[cachekey] = tuple(set([row[1] for rowidx, row in rows]))
    for main_entity_eid in no_relation_eids:
        entity = cnx.entity_from_eid(main_entity_eid)
        entity.__dict__[cachekey] = ()


def first_entity_factory(rset, rows):
    assert len(rows) == 1, "service relations are not supposed to be multivalued"
    return rset.get_entity(0, 1)


def set_entity_cache(
    cnx, etype, entities, query, cachekey, cache_factory=_ecache_factory, empty_value=()
):
    with_being = (
        ", X identity X2 WITH X2 BEING "
        "(Any X ORDERBY X LIMIT {0} WHERE X is {1}, "
        "X eid >= %(x)s)".format(len(entities), etype)
    )
    etype_class = cnx.vreg["etypes"].etype_class(etype)
    _unbind_orm_relation(etype_class, cachekey)
    rset = cnx.execute(query + with_being, {"x": min(entities)})
    related, no_relation_eids = _grouped_rset(entities, rset)
    for main_entity_eid, rows in related.items():
        entity = cnx.entity_from_eid(main_entity_eid)
        entity.__dict__[cachekey] = cache_factory(rset, rows)
    for main_entity_eid in no_relation_eids:
        entity = cnx.entity_from_eid(main_entity_eid)
        entity.__dict__[cachekey] = empty_value


def iter_rdf_adapters(entity):
    for adapter_id in ETYPES_ADAPTERS.get(entity.__regid__):
        adapter = entity.cw_adapt_to(adapter_id)
        if adapter:
            yield adapter


def add_entity_to_graph(graph, entity):
    rdf_adapters = [iter_rdf_adapters(entity)]
    for adapter in chain(*rdf_adapters):
        add_statements_to_graph(graph, adapter)


def _add_etype_to_graph(cnx, graph, etype, limit, offset, logger):
    # create
    cacher = CACHER_CLASSES[etype.lower()]()
    query = cacher.build_query()
    rset = cnx.execute(query % (limit, offset), build_descr=True)
    logger.info(f"Write {rset.rowcount} {etype}")
    cacher.setup_iteration_cache(cnx, rset)
    # Construct graph
    for entity in rset.entities():
        add_entity_to_graph(graph, entity)
    cnx.drop_entity_cache()


def write_graph(appid, schema, s3, output_dir, formats, etype, limit, offset, chunksize, logger):
    filenames = []
    with admincnx(appid) as cnx:
        if schema == "published":
            set_published_schema(cnx)
        if s3:
            st = S3RDFStorge(logger)
        else:
            st = FSRDFStorge(output_dir, logger)
        graph = ConjunctiveGraph()
        limit = limit if limit and limit < chunksize else chunksize
        _add_etype_to_graph(cnx, graph, etype, limit, offset, logger)
        for _format in formats:
            filepath = st.get_filepath(etype, offset, _format)
            st.storage.storage_write_file(
                filepath, graph.serialize(format=_format).encode("utf-8")
            )  # noqa
            filenames.append(filepath)
            # clean as much as possible to avoid memory exhaustion
    return filenames


def set_published_schema(cnx):
    cnx.system_sql("SET search_path TO published, public;")


class RDFDumper:
    def __init__(
        self,
        schema,
        etype,
        formats,
        output_dir,
        logger,
    ):
        self.etype = etype
        self.output_dir = output_dir
        self.formats = formats
        self.schema = schema
        self.logger = logger

    def teardown_cache(self, cnx, rset=None):
        cnx.drop_entity_cache()

    @timed
    def dump_entities(self, appid, nb_processes, options):
        limit = options.get("limit")
        with admincnx(appid) as cnx:
            if self.schema == "published":
                self.logger.info("Search in published schema")
                set_published_schema(cnx)
            if not limit:
                if self.etype in ("LocationAuthority", "AgentAuthority", "SubjectAuthority"):
                    nb_entities = cnx.execute(
                        f"Any COUNT(X) WHERE X is {self.etype}, X quality True"
                    )[0][0]
                else:
                    nb_entities = cnx.execute(f"Any COUNT(X) WHERE X is {self.etype}")[0][0]
            else:
                nb_entities = int(limit)
        self.logger.info
        (f"[dump_entities]: Process {nb_entities} {self.etype} with {nb_processes} process")
        filenames = []
        pool = mp.Pool(nb_processes)
        s3storage = options.get("s3")
        chunksize = options.get("chunksize")
        results = pool.starmap(
            write_graph,
            [
                (
                    appid,
                    self.schema,
                    s3storage,
                    self.output_dir,
                    self.formats,
                    self.etype,
                    limit,
                    offset,
                    chunksize,
                    self.logger,
                )
                for offset in range(0, nb_entities, chunksize)
            ],
        )
        for res in results:
            filenames.extend(res)
        return filenames

    def dump(self, appid, nb_processes, options):
        filenames = self.dump_entities(appid, nb_processes, options)
        self.logger.info(f"[dump] {self.etype}: RDF generation finished")
        if not options.get("s3"):
            self.fs_make_archive(filenames)

    def fs_make_archive(self, filenames):
        for _format in self.formats:
            archive_name = "%s_%s.tar.gz" % (self.etype.lower(), _format)
            archive_path = os.path.join(self.output_dir, archive_name)
            self.logger.info(f"[dump] {self.etype}: Write archives {archive_path}")
            with tarfile.open(archive_path, "w:gz") as tar:
                for filename in filenames:
                    # add file but specify basename as the alternative filename
                    # to avoid nested directory structure in the archive
                    tar.add(filename, arcname=os.path.basename(filename))
                    # os.remove(filename)


def create_dumps(appid, config, etype, output_dir, logger):
    if etype not in ETYPES_ADAPTERS:
        logger.error(
            f"No RDF adapter is available for {etype}. "
            f"RDF adapters are available for: {', '.join(ETYPES_ADAPTERS)}"
        )
        return
    formats = config.get("formats")
    if not isinstance(formats, (list, tuple)):
        formats = formats.split(",")
    schema = "published" if config.get("published") else "public"
    dumper = RDFDumper(
        schema,
        etype,
        formats,
        output_dir,
        logger,
    )

    if config.get("rqllog"):
        from cubicweb import server

        server.set_debug("DBG_RQL")
    if config.get("profile"):
        logger.info("Start generating and profiling dump", etype)
        import cProfile

        proffile = "/tmp/rdfdump_{}.prof".format(etype.lower())
        cProfile.runctx("run([dumper], cnx)", globals(), locals(), proffile)
        logger.info("\ncheck profile ", proffile)
    else:
        try:
            logger.info("Start generating dump %s", etype)
            run([dumper], appid, config, logger)
        except Exception as exc:
            import traceback

            traceback.print_exc()
            logger.error("Failed to generate dump %s %s", etype, exc)
            raise Exception(exc)


def run(dumpers, appid, options, logger):
    try:
        mp.cpu_count()
    except Exception as ex:
        logger.error(ex)
    nb_processes = options.get("nbprocesses")
    if nb_processes is None:
        nb_processes = max(mp.cpu_count() - 1, 1)
    if nb_processes > 1:
        logger.info("\n%s CPU availables, use %s processes\n", mp.cpu_count(), nb_processes)
    else:
        logger.info("\n%s CPU availables, use 1 process\n", mp.cpu_count())
    for dumper in dumpers:
        dumper.dump(appid, nb_processes, options)


def rdfdumps(appid, options):
    if options.get("published"):
        os.environ["RDFDUMP_PUBLISHED"] = "1"
    # init logger
    logfile = options.get("logfile")
    logger = logging.getLogger("francearchives.rdfdump")
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(logfile)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s -- %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    date = datetime.now().strftime("%Y%m%d")
    output_dir = os.path.join(options["output-dir"], date)
    if options.get("s3"):
        if not AWS_S3_RDF_BUCKET_NAME:
            logger.error("[rdfdumps]: No bucket name (no AWS_S3_RDF_BUCKET_NAME found)")
            sys.exit()
        st = S3RDFStorge(logger=logger)
    else:
        st = FSRDFStorge(output_dir, logger=logger)
    st.prepare_storage(options)
    etypes = options.get("etypes")
    if not isinstance(etypes, (list, tuple)):
        etypes = etypes.split(",")
    try:
        for etype in etypes:
            create_dumps(appid, options, etype, output_dir, logger)
    except Exception:
        if hasattr(st, "s3_bucket") and st.backuped_name:
            st.delete_bucket(st.s3_bucket)
            st.rename_bucket(st.backuped_name, st.s3_bucket)
            return
    # delete the backuped bucket
    if st.backuped_name:
        logger.info(f'[rdfdumps]: Start deleting the backuped bucket "{st.backuped_name}"')
        st.delete_bucket(st.backuped_name)
        logger.info(f'[rdfdumps]: The backuped bucket "{st.backuped_name}" is deleted')


if __name__ == "__main__":  # if used with cubicweb-ctl shell
    parser = OptionParser("usage: %prog [options] <instanceid>")
    parser.add_option(
        "--etypes",
        dest="etypes",
        default=list(ETYPES_ADAPTERS),
        help=("comma separated list of cwetypes to be exported: %s" % list(ETYPES_ADAPTERS)),
    ),
    parser.add_option(
        "--p",
        dest="published",
        action="store_true",
        default=True,
        help="execute on published schema",
    )

    parser.add_option(
        "--output-dir",
        dest="output-dir",
        type="string",
        default="/tmp",
        help=("directory where the rdf dumps are stored on the filesystem or " "S3 name bucket"),
    ),
    parser.add_option(
        "--formats",
        dest="formats",
        default=("nt",),
        help=(
            "comma separated list of formats you want to generate: 'nt', 'n3', 'xml' "
            "(default to nt)"
        ),
    ),
    parser.add_option(
        "--chunksize", dest="chunksize", type="int", default=2000, help="chunksize size"
    )
    parser.add_option("--limit", dest="limit", type="int", help="max number of entities generated")
    parser.add_option("--offset", dest="offset", default=0, type="int", help="Offset of entities")
    parser.add_option(
        "--s3",
        dest="s3",
        action="store_true",
        default=False,
        help="store in s3 from AWS_S3_RDF_BUCKET_NAME",
    )
    parser.add_option(
        "--s3db",
        dest="s3db",
        action="store_true",
        default=False,
        help="delete existing s3 AWS_S3_RDF_BUCKET_NAME bucket",
    )
    parser.add_option(
        "--s3rb",
        dest="s3rb",
        action="store_true",
        default=False,
        help="rename existing s3 AWS_S3_RDF_BUCKET_NAME bucket",
    )
    parser.add_option(
        "--nbprocesses",
        type="int",
        dest="nbprocesses",
        default=None,
        help="number of subprocesses to spawn to generate RDF dumps",
    )
    parser.add_option(
        "--logfile",
        dest="logfile",
        type="string",
        help="rdfdump logfile",
        default="/tmp/rdfdump.log",
    )
    parser.add_option(
        "--rqllog",
        dest="rqllog",
        action="store_true",
        default=False,
        help="dump rql queries on stdout",
    )
    parser.add_option(
        "--profile",
        dest="profile",
        action="store_true",
        default=False,
        help="use cProfile to monitor execution (dump in /tmp/rdfdump.prof)",
    )

    (options, args) = parser.parse_args()
    if not args:
        parser.error("<instanceid> argument missing")
    appid = args[0]
    options = vars(options)
    rdfdumps(appid, options)
