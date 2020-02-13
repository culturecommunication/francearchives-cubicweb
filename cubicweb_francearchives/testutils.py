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

import mock

from sickle import Sickle
from sickle.response import OAIResponse

import shutil
import os
import os.path as osp

from cubicweb.cwconfig import CubicWebConfiguration

# library specific imports
from cubicweb_francearchives.dataimport import ead, load_services_map, service_infos_from_filepath
from cubicweb_francearchives.dataimport.sqlutil import (
    disable_triggers,
    enable_triggers,
    sudocnx,
    ead_foreign_key_tables,
)
from cubicweb_francearchives.dataimport.stores import create_massive_store
from cubicweb_francearchives.dataimport import create_ead_index_table

# third party imports
from cubicweb.devtools import PostgresApptestConfiguration


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


class EADImportMixin(object):

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

    def tearDown(self):
        super(EADImportMixin, self).tearDown()
        import_dir = self.datapath("tmp")
        if osp.exists(import_dir):
            shutil.rmtree(import_dir)

    def import_filepath(self, cnx, filepath, service_infos=None, **custom_settings):
        if isinstance(filepath, bytes):
            filepath = filepath.decode("utf-8")
        if service_infos is None:
            services_map = load_services_map(cnx)
            service_infos = service_infos_from_filepath(filepath, services_map)
        if not self.readerconfig["nodrop"]:
            fk_tables = ead_foreign_key_tables(cnx.vreg.schema)
            with sudocnx(cnx, interactive=False) as su_cnx:
                disable_triggers(su_cnx, fk_tables)
        store = create_massive_store(cnx, nodrop=self.readerconfig["nodrop"])
        create_ead_index_table(cnx)
        settings = self.readerconfig.copy()
        settings["appfiles-dir"] = self.config["appfiles-dir"]
        settings.update(custom_settings)
        self.reader = ead.Reader(settings, store)
        es_doc = self.reader.import_filepath(filepath, service_infos)
        store.flush()
        store.finish()
        store.commit()
        if not self.readerconfig["nodrop"]:
            with sudocnx(cnx, interactive=False) as su_cnx:
                enable_triggers(su_cnx, fk_tables)
        return es_doc


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


class HashMixIn(object):
    def setUp(self):
        super(HashMixIn, self).setUp()
        self.config.global_set_option("compute-hash", True)
        self.config.global_set_option("hash-algorithm", "sha1")


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
        self.patch = mock.patch("sickle.app.Sickle.harvest", self.mock_harvest)
        self.filename = None
        super(OaiSickleMixin, self).__init__(*args, **kwargs)

    def setUp(self):
        super(OaiSickleMixin, self).setUp()
        self.patch.start()
        self.sickle = Sickle("http://localhost")

    def tearDown(self):
        """Tear down test cases."""
        super(OaiSickleMixin, self).tearDown()
        self.patch.stop()

    def mock_harvest(self, *args, **kwargs):
        assert self.filename is not None
        with open(self.filepath(), "r") as fp:
            response = MockOaiSickleResponse(fp.read())
            return OAIResponse(response, kwargs)
