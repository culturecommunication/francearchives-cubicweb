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

import datetime as dt
import shutil
import os
import os.path as osp
from uuid import uuid4

import boto3
import mock
from moto import mock_s3
from botocore.exceptions import ClientError

from logilab.common.date import ustrftime

from cubicweb import Binary
from cubicweb.cwconfig import CubicWebConfiguration


# library specific imports
from cubicweb_francearchives import S3_ACTIVE, FranceArchivesS3Storage
from cubicweb_francearchives.dataimport import ead, load_services_map, service_infos_from_filepath
from cubicweb_francearchives.dataimport.oai_utils import PniaOAIResponse, PniaSickle
from cubicweb_francearchives.dataimport.sqlutil import (
    no_trigger,
    disable_triggers,
    enable_triggers,
    sudocnx,
    ead_foreign_key_tables,
    nomina_foreign_key_tables,
)
from cubicweb_francearchives.dataimport.stores import create_massive_store
from cubicweb_francearchives.dataimport.csv_nomina import CSVNominaReader


# third party imports
from cubicweb.devtools import PostgresApptestConfiguration


def create_findingaid(cnx, eadid, service):
    return cnx.create_entity(
        "FindingAid",
        name=eadid,
        stable_id="stable_id{}".format(eadid),
        eadid=eadid,
        publisher="publisher",
        did=cnx.create_entity(
            "Did", unitid="unitid {}".format(eadid), unittitle="title {}".format(eadid)
        ),
        fa_header=cnx.create_entity("FAHeader"),
        service=service,
    )


class PostgresTextMixin(object):
    """unittest mixin for postgresql-based tests

    - define configcls
    - setup postgresql extensions
    """

    configcls = PostgresApptestConfiguration

    def setUp(self):
        super(PostgresTextMixin, self).setUp()
        with self.admin_access.cnx() as cnx:
            # unaccent will already be added in production
            cnx.system_sql("CREATE EXTENSION IF NOT EXISTS unaccent")
            cnx.commit()


class HashMixIn(object):
    @classmethod
    def init_config(cls, config):
        super(HashMixIn, cls).init_config(config)
        config.set_option("compute-hash", True)
        config.set_option("hash-algorithm", "sha1")


class S3BfssStorageTestMixin(HashMixIn):
    s3_endpoint = os.environ.get("AWS_S3_ENDPOINT_URL", "")

    def s3_test_with_mock(self):
        return S3_ACTIVE and "9000" not in self.s3_endpoint

    def s3_test_with_minio(self):
        return S3_ACTIVE and "9000" in self.s3_endpoint

    def setUp(self):
        self.fkeyfunc = "STKEY"
        self.s3_bucket_name = "siaf-tests-{}".format(uuid4()) if S3_ACTIVE else None
        if self.s3_test_with_mock():
            s3_mock = mock_s3()
            s3_mock.start()
            resource = boto3.resource("s3", region_name="us-east-1")
            self.s3_bucket = resource.create_bucket(Bucket=self.s3_bucket_name)
            patched_storage_s3_client = mock.patch(
                "cubicweb_s3storage.storages.S3Storage._s3_client",
                return_value=boto3.client("es3"),
            )
            patched_storage_s3_client.start()
            self._mocks = [
                s3_mock,
                patched_storage_s3_client,
            ]
            # TODO mock pyramid s3 cnx too
            print("S3 Storage activated")
        elif self.s3_test_with_minio():
            os.environ["AWS_S3_BUCKET_NAME"] = self.s3_bucket_name
            storage = FranceArchivesS3Storage(self.s3_bucket_name)
            try:
                storage.s3cnx.create_bucket(Bucket=self.s3_bucket_name)
            except ClientError:
                print("Bucket {} already exists".format(self.s3_bucket_name))
            print("S3 Storage activated with minio")
        else:
            # we are not on S3Storage
            self.fkeyfunc = "FSPATH"
            print("BFSS Storage activated")
        super(S3BfssStorageTestMixin, self).setUp()

    def tearDown(self):
        super(S3BfssStorageTestMixin, self).tearDown()
        if self.s3_test_with_mock():
            while self._mocks:
                self._mocks.pop().stop()
        elif self.s3_test_with_minio():
            try:
                s3 = boto3.resource("s3", endpoint_url=os.environ.get("AWS_S3_ENDPOINT_URL"))
                bucket = s3.Bucket(self.s3_bucket_name)
                bucket.objects.all().delete()
                bucket.delete()
            except ClientError as exc:
                print(exc)
                print("[test.treaDown] Failed to delete bucket {}".format(self.s3_bucket_name))

    def fileExists(self, fkey):
        """
        Returns boolean
        """
        if not self.s3_bucket_name:
            return osp.exists(fkey)

        if isinstance(fkey, bytes):
            fkey = fkey.decode()
        if self.s3_test_with_mock():
            s3 = boto3.resource("s3")
            s3_object = s3.Object(self.s3_bucket_name, fkey)
            try:
                return s3_object.get()["Body"]
            except s3.meta.client.exceptions.NoSuchKey:
                print(f"[test.fileExists] no {fkey} key found in bucket")
                return False
        elif self.s3_test_with_minio():
            storage = FranceArchivesS3Storage(self.s3_bucket_name)
            try:
                head = storage.s3cnx.head_object(Key=fkey, Bucket=self.s3_bucket_name)
                return head["ResponseMetadata"].get("HTTPStatusCode") == 200
            except ClientError:
                print(f"[test.fileExists] no {fkey} key found in bucket")
                return False

    def getFileContent(self, fkey):
        """
        Returns file contents or None if no file is found
        """
        if not self.s3_bucket_name:
            with open(fkey, "rb") as fp:
                return fp.read()

        if isinstance(fkey, bytes):
            fkey = fkey.decode()
        if self.s3_test_with_mock():
            s3 = boto3.resource("s3")
            s3_object = s3.Object(self.s3_bucket_name, fkey)
            try:
                return s3_object.get()["Body"].read()
            except s3.meta.client.exceptions.NoSuchKey:
                print(f"[test.fileExists] no {fkey} key found in bucket")
                return False
        elif self.s3_test_with_minio():
            storage = FranceArchivesS3Storage(self.s3_bucket_name)
            try:
                result = storage.s3cnx.get_object(Bucket=self.s3_bucket_name, Key=fkey)
                return result["Body"].read()
            except ClientError:
                print(f"[test.getFileContent] no {fkey} key found in bucket")

    def isFile(self, fkey):
        if self.s3_bucket_name:
            return self.fileExists(fkey)
        else:
            return osp.isfile(fkey)

    def get_filepath_by_storage(self, filepath):
        """
        Compute the filepath for test.

        :create: if true, upload imported files in s3
        :filepath: imported filepath

        :returns: filepath
        :rtype: str
        """
        if self.s3_bucket_name:
            return filepath.lstrip("/")
        else:
            return self.datapath(filepath)

    def storage_write_file(self, filepath, content):
        """
        Write a file with the give content
        """
        if self.s3_bucket_name:
            if self.fileExists(filepath):
                return filepath
            storage = FranceArchivesS3Storage(self.s3_bucket_name)
            storage.temporary_import_upload(Binary(content.encode("utf8")), filepath)
        else:
            dirs, basename = os.path.split(filepath)
            if not osp.exists(dirs):
                os.makedirs(dirs)
            with open(filepath, "w+") as fp:
                fp.write(content)

    def get_or_create_imported_filepath(self, filepath):
        """
        Compute the filepath for test.

        :create: if true, upload ead test files in s3
        :filepath: imported filepath

        :returns: filepath
        :rtype: str
        """

        if self.s3_bucket_name:
            storage = FranceArchivesS3Storage(self.s3_bucket_name)
            if storage.file_exists(filepath):
                # we are probably testing file reimports
                return filepath
            fs_filepath = self.datapath(filepath)
            with open(fs_filepath, "rb") as stream:
                storage.temporary_import_upload(Binary(stream.read()), filepath)
            # also upload "RELFILES" if exist
            relfiles_dir = f"{osp.dirname(fs_filepath)}/RELFILES"
            for root, dirs, files in os.walk(relfiles_dir):
                for relfname in files:
                    relkey = storage.ensure_key(f"{osp.dirname(filepath)}/RELFILES/{relfname}")
                    with open(osp.join(root, relfname), "rb") as stream:
                        storage.temporary_import_upload(Binary(stream.read()), relkey)
            # also upload metadata file if exists
            metadata_file = f"{osp.dirname(fs_filepath)}/metadata.csv"
            if osp.isfile(metadata_file):
                with open(metadata_file, "rb") as stream:
                    metadata_key = storage.ensure_key(f"{osp.dirname(filepath)}/metadata.csv")
                    storage.temporary_import_upload(Binary(stream.read()), metadata_key)

        else:
            filepath = self.datapath(filepath)
        return filepath

    def load_directory_folder(self, fs_folderpath, prefix):
        """
        Compute the filepath for test.

        :fs_folderpath: file system folder path to import
        :filepath: imported filepath
        """

        if self.s3_bucket_name:
            storage = FranceArchivesS3Storage(self.s3_bucket_name)
            for root, dirs, files in os.walk(fs_folderpath):
                for filename in files:
                    fs_filepath = osp.join(root, filename)
                    fkey = storage.ensure_key(fs_filepath.replace(fs_folderpath, prefix))
                    with open(fs_filepath, "rb") as stream:
                        storage.temporary_import_upload(Binary(stream.read()), fkey)


class EADImportMixin(S3BfssStorageTestMixin):
    readerconfig = {
        "esonly": False,
        "index-name": "dummy",
        "appid": "data",
        "nodrop": False,
    }

    def setUp(self):
        super(EADImportMixin, self).setUp()
        import_dir = self.datapath("tmp")
        self.config.set_option("appfiles-dir", import_dir)
        if not osp.isdir(import_dir):
            os.mkdir(import_dir)
        self.imported_filepath = None

    def tearDown(self):
        super(EADImportMixin, self).tearDown()
        import_dir = self.datapath("tmp")
        if osp.exists(import_dir):
            shutil.rmtree(import_dir)

    def import_filepath(self, cnx, filepath, service_infos=None, **custom_settings):
        filepath = self.get_or_create_imported_filepath(filepath)
        if isinstance(filepath, bytes):
            filepath = filepath.decode("utf-8")
        self.imported_filepath = filepath
        if service_infos is None:
            services_map = load_services_map(cnx)
            service_infos = service_infos_from_filepath(filepath, services_map)
        if not self.readerconfig["nodrop"]:
            fk_tables = ead_foreign_key_tables(cnx.vreg.schema)
            with sudocnx(cnx, interactive=False) as su_cnx:
                disable_triggers(su_cnx, fk_tables)
        store = create_massive_store(cnx, nodrop=self.readerconfig["nodrop"])
        settings = self.readerconfig.copy()
        settings["appfiles-dir"] = self.config["appfiles-dir"]
        settings.update(custom_settings)
        self.reader = ead.Reader(settings, store)
        es_docs = self.reader.import_filepath(filepath, service_infos)
        store.flush()
        store.finish()
        if not self.readerconfig["nodrop"]:
            with sudocnx(cnx, interactive=False) as su_cnx:
                enable_triggers(su_cnx, fk_tables)
        return es_docs


class NominaImportMixin(S3BfssStorageTestMixin):
    def setUp(self):
        super(NominaImportMixin, self).setUp()
        import_dir = self.datapath("tmp")
        self.config.set_option("appfiles-dir", import_dir)
        if not osp.isdir(import_dir):
            os.mkdir(import_dir)

    readerconfig = {
        "nomina-index-name": "dummy_nomina",
    }

    @classmethod
    def init_config(cls, config):
        super(NominaImportMixin, cls).init_config(config)
        config.set_option("nomina-services-dir", "/tmp")

    def tearDown(self):
        super(NominaImportMixin, self).tearDown()
        import_dir = self.datapath("tmp")
        if osp.exists(import_dir):
            shutil.rmtree(import_dir)

    def import_filepath(self, cnx, filepath, doctype, delimiter=";"):
        store = create_massive_store(cnx, nodrop=True)
        reader = CSVNominaReader(self.readerconfig, store, self.service.code)
        notrigger_tables = nomina_foreign_key_tables(cnx.vreg.schema)
        with no_trigger(cnx, notrigger_tables, interactive=False):
            es_docs = reader.import_records(filepath, delimiter=delimiter, doctype=doctype)
            store.flush()
            store.finish()
            store.commit()
        return es_docs


class XMLCompMixin(object):
    def assertXMLEqual(self, etree0, etree1):
        """Assert element tree equivalence.

        :param Element etree0: element tree element
        :param Element etree1: element tree element
        """
        self.assertEqual(etree0.attrib, etree1.attrib)
        self.assertEqual(etree0.tag, etree1.tag)
        self.assertEqual(etree0.tail, etree1.tail)
        self.assertEqual(etree0.text, etree1.text)
        for child0, child1 in zip(etree0.getchildren(), etree1.getchildren()):
            self.assertXMLEqual(child0, child1)


class EsSerializableMixIn(object):
    def setUp(self):
        super(EsSerializableMixIn, self).setUp()
        if "PIFPAF_ES_ELASTICSEARCH_URL" in os.environ:
            self.config.global_set_option(
                "elasticsearch-locations", os.environ["PIFPAF_ES_ELASTICSEARCH_URL"]
            )
        else:
            self.config.global_set_option(
                "elasticsearch-locations", "http://nonexistant.elastic.search:9200"
            )
        self.index_name = "unittest_index_name"
        self.config.global_set_option("index-name", self.index_name)

    def setup_database(self):
        super(EsSerializableMixIn, self).setup_database()
        self.orig_config_for = CubicWebConfiguration.config_for
        config_for = lambda appid: self.config  # noqa
        CubicWebConfiguration.config_for = staticmethod(config_for)


class MockOaiSickleResponse(object):
    """Mimics the response object returned by HTTP requests."""

    def __init__(self, text):
        # request's response object carry an attribute 'text' which contains
        # the server's response data encoded as unicode.
        self.text = text
        self.content = text.encode("utf-8")


class OaiSickleMixin(object):
    def filepath(self, filepath):
        raise NotImplementedError

    def __init__(self, *args, **kwargs):
        self.patch = mock.patch(
            "cubicweb_francearchives.dataimport.oai_utils.PniaSickle.harvest", self.mock_harvest
        )
        self.filename = None
        super(OaiSickleMixin, self).__init__(*args, **kwargs)

    def setUp(self):
        super(OaiSickleMixin, self).setUp()
        self.patch.start()
        self.sickle = PniaSickle("http://localhost")

    def tearDown(self):
        """Tear down test cases."""
        super(OaiSickleMixin, self).tearDown()
        self.patch.stop()

    def mock_harvest(self, *args, **kwargs):
        assert self.filename is not None
        with open(self.filepath(), "r") as fp:
            response = MockOaiSickleResponse(fp.read())
            return PniaOAIResponse(response, kwargs)


def format_date(date, fmt="%Y-%m-%d"):
    return ustrftime(date, fmt)


def create_authority_record(cnx):
    service = cnx.create_entity(
        "Service", category="other", name="Service", code="CODE", short_name="ADP"
    )
    name = "Jean Cocotte"
    subject = cnx.create_entity(
        "AgentAuthority",
        label=name,
        reverse_authority=cnx.create_entity(
            "AgentName",
            role="person",
            label="name",
        ),
    )
    kind_eid = cnx.find("AgentKind", name="person")[0][0]
    record = cnx.create_entity(
        "AuthorityRecord",
        record_id="FRAN_NP_006883",
        agent_kind=kind_eid,
        maintainer=service.eid,
        reverse_name_entry_for=cnx.create_entity(
            "NameEntry", parts=name, form_variant="authorized"
        ),
        xml_support="foo",
        start_date=dt.datetime(1940, 1, 1),
        end_date=dt.datetime(2000, 5, 1),
        reverse_occupation_agent=cnx.create_entity("Occupation", term="éleveur de poules"),
        reverse_history_agent=cnx.create_entity("History", text="<p>Il aimait les poules</p>"),
        same_as=subject,
    )
    return record
