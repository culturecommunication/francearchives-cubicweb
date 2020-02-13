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
"""cubicweb-ctl plugin providing additional commands

:organization: Logilab
:copyright: 2016 LOGILAB S.A. (Paris, FRANCE), all rights reserved.
:contact: http://www.logilab.fr/ -- mailto:contact@logilab.fr
"""


import os
import os.path as osp
import sys
import shutil
from glob import glob
from datetime import datetime
from itertools import chain
import csv

import yaml

from urllib.parse import urlparse

from elasticsearch.helpers import scan, parallel_bulk

from logilab.database import get_connection
from logilab.common.decorators import monkeypatch

from cubicweb import ConfigurationError
from cubicweb.cwctl import CWCTL
from cubicweb.cwconfig import CubicWebConfiguration as cwcfg
from cubicweb.toolsutils import Command, underline_title
from cubicweb.server.serverconfig import ServerConfiguration


from cubicweb_elasticsearch import es as cwes
from cubicweb_elasticsearch.ccplugin import IndexInES
from cubicweb_elasticsearch.es import indexable_entities

from cubicweb_francearchives import admincnx, i18n, sitemap, init_bfss, utils, rdfdump
from cubicweb_francearchives.dataimport.dc import import_filepath as dc_import_filepath
from cubicweb_francearchives.dataimport.directories import import_directory
from cubicweb_francearchives.dataimport.ead import readerconfig
from cubicweb_francearchives.dataimport.importer import import_filepaths
from cubicweb_francearchives.dataimport import oai, es_bulk_index, log_in_db, strip_html
from cubicweb_francearchives.entities.es import SUGGEST_ETYPES
from cubicweb_francearchives.dataimport.eac import eac_import_files
from cubicweb_francearchives.dataimport.maps import import_maps
from cubicweb_francearchives.dataimport.newsletter import import_subscribers
from cubicweb_francearchives.utils import init_repository
from cubicweb_francearchives.xmlutils import enhance_accessibility
from cubicweb_francearchives import CMS_OBJECTS
from cubicweb_francearchives.dataimport.scripts.generate_ape_ead import generate_ape_ead_files
from cubicweb_francearchives.scripts.nginx_confs_from_faredirects import write_nginx_confs
from cubicweb_francearchives.scripts.reindex_authority import reindex_authority


HERE = osp.dirname(osp.abspath(__file__))


def get_indexable_fa(cnx, etype, chunksize=100000):
    lasteid = 0
    rql = (
        "Any X, E, D, U, S ORDERBY X LIMIT {} WHERE "
        "X is {}, E is EsDocument, E entity X, E doc D, "
        "X cwuri U, X stable_id S, "
        "X eid > %(l)s"
    ).format(chunksize, etype)
    while True:
        rset = cnx.execute(rql, {"l": lasteid})
        if not rset:
            break
        for e in rset.entities():
            yield e
        cnx.drop_entity_cache()
        lasteid = rset[-1][0]


class PniaIndexInEs(IndexInES):
    """Index content in ElasticSearch.

    <instance id>
      identifier of the instance

    """

    def bulk_actions(self, etypes, cnx, index_name=None, dry_run=False):
        etypes = set(etypes) & set(cwes.indexable_types(cnx.vreg.schema))
        index_name = index_name or "%s_all" % cnx.vreg.config["index-name"]
        init_bfss(cnx.repo)
        for etype in etypes:
            if etype in ("FAComponent", "FindingAid"):
                gen = get_indexable_fa(cnx, etype, self.config.chunksize)
            else:
                gen = indexable_entities(cnx, etype, chunksize=self.config.chunksize)
            for idx, entity in enumerate(gen, 1):
                try:
                    serializer = entity.cw_adapt_to("IFullTextIndexSerializable")
                    json = serializer.serialize(complete=False)
                except Exception:
                    cnx.error(
                        "[{}] Failed to serialize entity {} ({})".format(
                            index_name, entity.eid, etype
                        )
                    )
                    continue
                if not dry_run and json:
                    # Entities with
                    # fulltext_containers relations return their container
                    # IFullTextIndex serializer , therefor the "id" and
                    # "doc_type" in kwargs bellow must be container data.
                    data = {
                        "_op_type": "index",
                        "_index": index_name or cnx.vreg.config["index-name"],
                        "_type": "_doc",
                        "_id": serializer.es_id,
                        "_source": json,
                    }
                    self.customize_data(data)
                    yield data
            cnx.info("[{}] indexed {} {} entities".format(index_name, idx, etype))

    def customize_data(self, data):
        self.strip_html_from_es_data(data)
        # XXX hack: with fulltext_container handling, indexation ignores
        # the actual entity type and relies only on the 'cw_etype' key
        # found in the ES document.
        if data["_type"] in ("Virtual_exhibit", "Blog", "Other"):
            data["_type"] = "_doc"

    @staticmethod
    def strip_html_from_es_data(data):
        """Remove HTML tags from the data that will be sent to ElasticSearch"""
        # FIXME: get the attribute list from schema introspection
        attributes_to_strip = ["content", "manif_prog"]

        for attr in attributes_to_strip:
            if attr in data["_source"] and data["_source"][attr]:
                data["_source"][attr] = strip_html(data["_source"][attr])

        return data


class ImportAll(Command):
    """call all import command"""

    arguments = "<instance>"
    name = "import-all"
    min_args = max_args = 1
    options = [
        (
            "config",
            {
                "short": "c",
                "type": "string",
                "default": osp.expanduser("~/.config/francearchives.yaml"),
                "help": ("fichier contenant les paramètres de toutes les " "commandes"),
            },
        ),
        (
            "skip",
            {
                "short": "S",
                "type": "csv",
                "default": (),
                "help": ("Liste des commandes d'import à ignorer " "(séparées par des virgules)"),
            },
        ),
        (
            "import-from",
            {
                "short": "F",
                "type": "string",
                "default": (),
                "help": ("Commande d'import à partir de laquelle reprendre " "l'import"),
            },
        ),
    ]

    def _build_cmd(self, cmd):
        cmd_line = [cmd, self.appid]
        if cmd not in self.yamlconfig:
            return cmd_line
        for k, v in list(self.yamlconfig[cmd].get("opts", {}).items()):
            opt_name = "--%s" % k
            if isinstance(v, bool) and v:
                cmd_line.append(opt_name)
            else:
                cmd_line.append(opt_name)
                cmd_line.append(v)
        for arg in self.yamlconfig[cmd].get("args", []):
            if "*" in arg:
                cmd_line += glob(arg)
            else:
                cmd_line.append(arg)
        return cmd_line

    def run(self, args):
        self.appid = args.pop(0)
        configpath = self.config.config
        if not osp.exists(configpath):
            print("path to config file does not exist", file=sys.stderr)
            self.help()
            sys.exit(1)
        with open(self.config.config) as f:
            self.yamlconfig = yaml.load(f)
        toskip = self.config.skip or ()
        fromcmd = self.config.import_from
        for cmdname in self.yamlconfig["commands"]:
            if fromcmd:
                if fromcmd != cmdname:
                    print("[import-all] skipping {}".format(cmdname))
                    continue
                fromcmd = None
            if cmdname in toskip:
                print("[import-all] skipping {}".format(cmdname))
                continue
            print("[import-all] {}".format(cmdname))
            try:
                CWCTL.run(self._build_cmd(cmdname))
            except SystemExit as exc:
                # if something went wrong, exit now
                if exc.code != 0:
                    raise


class ImportEAD(Command):
    """Import EAD files"""

    arguments = "<instance> <xmlfiles>"
    name = "import-ead"
    min_args = 1
    options = [
        (
            "esonly",
            {
                "action": "store_true",
                "default": False,
                "help": (
                    "contruit seulement les documents elasticsearch "
                    "(n'exécute aucune transaction sur la base postgres)"
                ),
            },
        ),
        (
            "fromfile",
            {
                "type": "string",
                "help": (
                    "lit la liste des fichiers depuis le fichier plutôt "
                    "que la ligne de commande. Le fichier lu doit contenir "
                    "un chemin de fichier par ligne"
                ),
            },
        ),
        (
            "noes",
            {
                "action": "store_true",
                "default": False,
                "help": ("ne pousse pas les documents dans elasticsearch"),
            },
        ),
        (
            "nodrop",
            {
                "action": "store_true",
                "default": False,
                "help": ("ne détruit pas les index / contraintes PG durant l'import"),
            },
        ),
        (
            "dedupe-authorities",
            {
                "type": "string",
                "default": "service/normalize",
                "help": "which mode of autodedupe algorithme we want to use",
            },
        ),
    ]

    def run(self, args):
        """call import_filepaths from dataimport.ead"""
        appid = args.pop(0)
        with admincnx(appid) as cnx:
            if self.config.fromfile:
                if args:
                    print(
                        "si --fromfile est utilisé, aucun " "fichier ne doit être passé en argument"
                    )
                    sys.exit(1)
                with open(self.config.fromfile) as inputf:
                    filepaths = (line.strip() for line in inputf)
                    filepaths = [fpath for fpath in filepaths if fpath and fpath[0] != "#"]
            else:
                filepaths = args
            import_filepaths(
                cnx,
                filepaths,
                readerconfig(
                    cnx.vreg.config,
                    appid,
                    self.config.esonly,
                    self.config.nodrop,
                    autodedupe_authorities=self.config.dedupe_authorities,
                    noes=self.config.noes,
                ),
            )


class ImportDirectories(Command):
    """Import service directories.

    <instance id>
      identifier of the instance
    <services-directory>
      services-directory csv file
    <services-departements>
      services-departements csv file
    <services-logos-directory>
      directory containing services logos
    """

    arguments = "<instance> <directory> <departements> <logo-directory>"
    name = "import-directories"
    min_args = max_args = 4

    def run(self, args):
        """call import_directory from dataimport.directories"""
        appid, directory, departement, logos_directory = args
        with admincnx(appid) as cnx:
            import_directory(cnx, directory, departement, logos_directory)


class ImportEAC(Command):
    """Import EAC files"""

    arguments = "<instance> <xmlfiles>"
    name = "import-eac"
    min_args = 2

    def run(self, args):
        appid = args.pop(0)
        with admincnx(appid) as cnx:
            init_bfss(cnx.repo)
            eac_import_files(cnx, args)


class ImportOai(Command):
    """Harvest an OAI repository and import its content in the database."""

    arguments = "<instance> <oaiurls>"
    name = "import-oai"
    min_args = 2
    options = [
        (
            "fpath",
            {
                "short": "f",
                "type": "string",
                "help": (
                    "fichier contenant la correspondance entre les "
                    "services et les  urls moissonnées"
                ),
            },
        ),
    ]

    @staticmethod
    def url_key(url):
        parse_result = urlparse(url.strip())
        return parse_result.netloc + parse_result.path

    def load_services(self):
        services = {}
        with open(self.config.fpath) as f:
            reader = csv.reader(f)
            header = next(reader)  # noqa
            for entry in reader:
                # columns = 'Code_institution', 'URL'
                url = self.url_key(entry[1])
                if entry[0] and url:
                    services[url] = entry[0].strip()
        return services

    def run(self, args):
        appid = args.pop(0)
        with admincnx(appid) as cnx:
            services_map = self.load_services()
            for url in args:
                url_key = self.url_key(url)
                service_infos = None
                service_code = services_map.get(url_key)
                if service_code:
                    rset = cnx.execute(
                        "Any X WHERE X is Service, X code %(s)s", {"s": service_code}
                    )
                    if len(rset) == 1:
                        service = rset.one()
                        service_infos = {
                            "code": service_code,
                            "name": service.publisher(),
                            "eid": service.eid,
                        }
                else:
                    service_code = urlparse(url).netloc
                if service_infos is None:
                    service_infos = {
                        "code": service_code,
                        "name": service_code,
                        "eid": None,
                    }
                try:
                    print("harvesting %r" % url)
                    oai.import_oai(cnx, url, service_infos)
                    cnx.commit()
                except Exception as exc:
                    print("failed to harvest %r because %s" % (url, exc))
                    cnx.rollback()


class IndexESAutocomplete(Command):
    """Index content for autocomplete search in ElasticSearch.

    <instance id>
      identifier of the instance

    """

    name = "index-es-suggest"
    min_args = max_args = 1
    arguments = "<instance id>"
    options = [
        (
            "dry-run",
            {
                "type": "yn",
                "default": False,
                "help": "set to True if you want to skip the insertion in ES",
            },
        ),
        (
            "debug",
            {
                "type": "yn",
                "default": False,
                "help": "set to True if you want to print" "out debug info and progress",
            },
        ),
        (
            "suggest-index-name",
            {
                "type": "string",
                "default": None,
                "help": "use a custom index name rather than the one "
                "specified in the all-in-one.conf file. "
                "(Note that no implicit _suggest suffix will be "
                "appended to the index name specified by this option)",
            },
        ),
    ]

    def suggest_index_name(self, cnx):
        if self.config.suggest_index_name:
            return self.config.suggest_index_name
        else:
            return "{}_suggest".format(cnx.vreg.config["index-name"])

    def run(self, args):
        """run the command with its specific arguments"""
        appid = args.pop(0)
        with admincnx(appid) as cnx:
            indexer = cnx.vreg["es"].select("suggest-indexer", cnx)
            indexer.indexable_etypes = SUGGEST_ETYPES
            indexer.create_index(index_name=self.suggest_index_name(cnx))
            es = indexer.get_connection()
            if es:
                log_in_db(self.index_es_autosuggest)(cnx, es)
            else:
                if self.config.debug:
                    print("no elasticsearch configuration found, skipping")

    def index_es_autosuggest(self, cnx, es):
        for _ in parallel_bulk(
            es,
            self.bulk_actions(cnx, es, dry_run=self.config.dry_run),
            raise_on_error=False,
            raise_on_exception=False,
        ):
            pass

    etype2type = {
        "LocationAuthority": "geogname",
        "SubjectAuthority": "subject",
        "AgentAuthority": "agent",
    }
    etype2urlsegment = {
        "LocationAuthority": "location",
        "SubjectAuthority": "subject",
        "AgentAuthority": "agent",
    }

    def bulk_actions(self, cnx, es, dry_run=False):
        try:
            suggest_index_name = self.suggest_index_name(cnx)
            for etype, authtable, indextable, in (
                ("LocationAuthority", "cw_locationauthority", "cw_geogname"),
                ("SubjectAuthority", "cw_subjectauthority", "cw_subject"),
                ("AgentAuthority", "cw_agentauthority", "cw_agentname"),
            ):
                if self.config.debug:
                    print("processing {}".format(etype))
                # execute an SQL query instead of RQL like
                # Any X, L, COUNT(F), COUNT(B), COUNT(X1) GROUPBY X, L WHERE X is {etype},
                # X label L, A? authority X, B? related_authority X, A index F?,
                # X grouped_with X1?
                # as there is no simple way in RQL to count only distinct values
                query = """
                SELECT at.cw_eid, at.cw_label,
                    COUNT(DISTINCT rel_index.eid_to),
                    COUNT(DISTINCT rel_auth.eid_from),
                    COUNT(DISTINCT rel_group.eid_to)
                FROM {authtable} AS at
                    LEFT OUTER JOIN {indextable} AS it ON (it.cw_authority=at.cw_eid)
                    LEFT OUTER JOIN related_authority_relation AS rel_auth
                               ON (rel_auth.eid_to=at.cw_eid)
                    LEFT OUTER JOIN index_relation AS rel_index
                              ON (rel_index.eid_from=it.cw_eid)
                    LEFT OUTER JOIN grouped_with_relation AS rel_group
                              ON (rel_group.eid_from=at.cw_eid)
                GROUP BY at.cw_eid,at.cw_label"""
                rset = cnx.system_sql(
                    query.format(authtable=authtable, indextable=indextable)
                ).fetchall()
                if self.config.debug:
                    print("   > number of entities {}".format(len(rset)))
                for autheid, label, countfa, countcomext, countgrouped in rset:
                    if not dry_run:
                        count = countfa + countcomext
                        yield {
                            "_op_type": "index",
                            "_index": suggest_index_name,
                            "_type": "_doc",
                            "_id": autheid,
                            "_source": {
                                "cw_etype": etype,
                                "eid": autheid,
                                "text": label,
                                # do not use type from Geogname, Subject, AgentName
                                # because user could have group authorities so
                                # one authority could have 2 AgentName with two different
                                # type
                                "type": self.etype2type[etype],
                                "additional": "",
                                "urlpath": "{}/{}".format(self.etype2urlsegment[etype], autheid),
                                "count": count,
                                "grouped": bool(countgrouped),
                            },
                        }
        except Exception as err:
            import traceback

            traceback.print_exc()
            print("oups !!!", err)
            raise


class ImportDC(Command):
    """Import findingaids"""

    arguments = "<instance> <csvfile1> [<csvfile2> ...]"
    name = "import-dc"
    min_args = 2
    options = [
        (
            "esonly",
            {
                "action": "store_true",
                "default": False,
                "help": (
                    "contruit seulement les documents elasticsearch "
                    "(n'exécute aucune transaction sur la base postgres)"
                ),
            },
        ),
        (
            "dedupe-authorities",
            {
                "type": "string",
                "default": "service/normalize",
                "help": "which mode of autodedupe algorithme we want to use",
            },
        ),
        (
            "noes",
            {
                "action": "store_true",
                "default": False,
                "help": ("ne pousse pas les documents dans elasticsearch"),
            },
        ),
    ]

    def run(self, args):
        appid = args[0]
        with admincnx(appid) as cnx:
            config = readerconfig(
                cnx.vreg.config,
                appid,
                self.config.esonly,
                autodedupe_authorities=self.config.dedupe_authorities,
                noes=self.config.noes,
                dc_no_cache=True,
            )
            for filepath in args[1:]:
                metadata_filepath = osp.join(osp.dirname(filepath), "metadata.csv")
                if not osp.exists(metadata_filepath):
                    metadata_filepath = None
                dc_import_filepath(cnx, config, filepath, metadata_filepath)


class ImportMaps(Command):
    """Import maps"""

    arguments = "<instance> <csvfile directory>"
    name = "import-maps"
    min_args = max_args = 2

    def run(self, args):
        """call import_maps from dataimport.maps"""
        appid, directory = args
        with admincnx(appid) as cnx:
            import_maps(cnx, directory)


class GenRedirect(Command):
    """generate map file for nginx to redirect previous url"""

    arguments = "<instance>"
    name = "fa-gen-redirect"
    min_args = max_args = 1
    options = [
        (
            "output",
            {
                "type": "string",
                "default": "map.conf",
                "short": "o",
                "help": "filepath to write map file",
            },
        ),
    ]

    def run(self, args):
        appid = args.pop()
        with admincnx(appid) as cnx:
            baseurl_parsed = urlparse(cnx.vreg.config["base-url"])
            redirect_netloc = "redirect.%s" % baseurl_parsed.netloc
            rset = cnx.execute("Any X, U WHERE X previous_info Y, Y url U")
            redirects = []
            for idx, (eid, url) in enumerate(rset):
                entity = rset.get_entity(idx, 0)
                line = "~%s/%s/?$ %s;" % (redirect_netloc, url.strip("/"), entity.absolute_url())
                redirects.append(line)
            rset = cnx.execute(
                "Any F,FDN,FH WHERE F data_name FDN, "
                'F data_name LIKE "static_%", '
                "F data_hash FH, "
                "NOT EXISTS(X findingaid_support F)"
            )
            for f in rset.entities():
                basename = osp.splitext(f.data_name)[0]
                line = "~%s/%s/?$ %s;" % (
                    redirect_netloc,
                    "static/{}".format(basename.split("_")[-1]),
                    f.cw_adapt_to("IDownloadable").download_url(),
                )
                redirects.append(line)
            with open(self.config.output, "w") as fout:
                fout.write("\n".join(line.encode("utf-8") for line in redirects))


@CWCTL.register
class GenSitemap(Command):
    """generate sitemap files"""

    arguments = "<instance>"
    name = "fa-gen-sitemap"
    min_args = max_args = 1

    options = [
        (
            "base-url",
            {
                "type": "string",
                "default": None,
                "help": "custom base-url to use to build entity URLS",
            },
        ),
        (
            "clear-sitemap-dir",
            {
                "short": "c",
                "action": "store_true",
                "default": False,
                "help": ("clear destination directory content before generating " "sitemap files"),
            },
        ),
    ]

    def run(self, args):
        appid = args.pop()
        with admincnx(appid) as cnx:
            dst = cnx.vreg.config.get("sitemap-dir")
            if self.config.clear_sitemap_dir:
                for fname in os.listdir(dst):
                    fpath = osp.join(dst, fname)
                    if osp.isfile(fpath):
                        os.unlink(fpath)
                    else:
                        shutil.rmtree(fpath)
            if self.config.base_url:
                cnx.vreg.config.global_set_option("base-url", self.config.base_url)
            sitemap.dump_sitemaps(cnx, dst)


@CWCTL.register
class ImportNLSubscribers(Command):
    """import newsletter subscribers emails"""

    arguments = "<instance> <csvfile>"
    name = "import-subscribers"
    min_args = max_args = 2

    def run(self, args):
        appid, filepath = args
        with admincnx(appid) as cnx:
            import_subscribers(cnx, filepath)


@monkeypatch(cwcfg)
def _load_site_cubicweb(self, cube):
    """Load site_cubicweb.py from `cube` (or apphome if cube is None)."""
    mod = None
    if cube is not None:
        if not cube.startswith("cubicweb_"):
            try:
                modname = "cubicweb_%s" % cube
                __import__(modname)
            except ImportError:
                modname = "cubes.%s" % cube
                __import__(modname)
        else:
            modname = cube
        modname = modname + ".site_cubicweb"
        __import__(modname)
        mod = sys.modules[modname]
    else:
        import imp

        apphome_site = osp.join(self.apphome, "site_cubicweb.py")
        if osp.exists(apphome_site):
            with open(apphome_site, "rb") as f:
                mod = imp.load_source("site_cubicweb", apphome_site, f)
    if getattr(mod, "options", None):
        self.register_options(mod.options)
        self.load_defaults()


@CWCTL.register
class ESDumpSnapshot(Command):
    """create an ES snapshot"""

    name = "fa-es-dump"
    arguments = "<instance>"
    min_args = max_args = 1

    options = [
        (
            "snapshot-name",
            {
                "short": "s",
                "type": "string",
                "default": None,
                "help": "name of the snapshot (default to instance-name>-<timestamp>)",
            },
        ),
        (
            "setup-repository",
            {
                "action": "store_true",
                "default": False,
                "help": "setup ES repository before snapshotting",
            },
        ),
        (
            "delete-existing-snapshot",
            {
                "short": "d",
                "action": "store_true",
                "default": False,
                "help": ("delete the snapshot if it alredy exists in ES before" "snapshotting"),
            },
        ),
    ]

    def run(self, args):
        appid = args[0]
        cwconfig = cwcfg.config_for(appid)
        cwconfig.init_cubes(cwconfig.available_cubes())  # load all options
        print("elasticsearch-locations =", cwconfig["elasticsearch-locations"])
        if self.config.setup_repository:
            utils.es_setup_backup(cwconfig)

        snapshot_name = self.config.snapshot_name or "{}-{}".format(
            appid.lower(), datetime.now().strftime("%Y%m%d-%H:%M:%S")
        )
        utils.es_dump(cwconfig, snapshot_name, delete=self.config.delete_existing_snapshot)
        print(
            "The creation of the ES snapshot is in progress, it may "
            "take a while to complete. Please check "
            "http://%s/_cat/snapshots/francearchives-backups?v for "
            "job completion" % cwconfig.get("elasticsearch-locations")
        )


@CWCTL.register
class ESRestoreSnapshot(Command):
    """restore an ES snapshot"""

    name = "fa-es-restore"
    arguments = "<instance> <snapshot-name>"
    min_args = max_args = 2

    options = [
        (
            "index-prefix",
            {
                "short": "p",
                "type": "string",
                "default": "francearchives",
                "help": "basename of indices to restore (e.g. `xxx` in `xxx`_{all,suggest}",
            },
        ),
        (
            "delete-existing-indices",
            {
                "short": "d",
                "action": "store_true",
                "default": False,
                "help": ("delete existing indices from ES before " "restore"),
            },
        ),
    ]

    def run(self, args):
        appid, snapshot_name = args
        cwconfig = cwcfg.config_for(appid)
        cwconfig.init_cubes(cwconfig.available_cubes())  # load all options
        utils.es_restore(
            cwconfig,
            snapshot_name,
            self.config.index_prefix,
            delete=self.config.delete_existing_indices,
        )

        print(
            "The restore of the ES snapshot is in progress, it may "
            "take a while to complete. Please check "
            "http://%s/_cat/indices?v for "
            "job completion" % cwconfig.get("elasticsearch-locations")
        )


@CWCTL.register
class DeleteEAD(Command):
    """delete FindingAid and related entities in database and elasticsearch"""

    name = "fa-delete-ead"
    arguments = "<instance> <ead-files>"
    min_args = 2
    options = [
        (
            "esonly",
            {
                "action": "store_true",
                "default": False,
                "help": (
                    "supprime seulement les documents elasticsearch "
                    "(n'exécute aucune transaction sur la base postgres)"
                ),
            },
        ),
        (
            "interactive",
            {
                "action": "store_true",
                "default": False,
                "help": "force la demande des identifiants super-utilisateur postgresql",
            },
        ),
        (
            "stable-id",
            {
                "action": "store_true",
                "default": False,
                "help": ("flag pour indiquer si les paramètres correspondent à des " "stable_id."),
            },
        ),
    ]

    def run(self, args):
        appid = args.pop(0)
        with admincnx(appid) as cnx:
            cnx.vreg.config.debugmode = True
            cnx.vreg.config.init_log(force=True)
            from cubicweb_francearchives.dataimport import sqlutil

            cnx.commit()
            sqlutil.delete_from_filenames(
                cnx,
                args,
                esonly=self.config.esonly,
                interactive=self.config.interactive,
                is_filename=not self.config.stable_id,
            )


@CWCTL.register
class DeleteInEs(Command):
    """restore an ES snapshot"""

    name = "fa-delete-in-es"
    arguments = "<instance>"
    min_args = max_args = 1

    options = [
        ("etypes", {"type": "csv", "default": "", "help": "only index given etypes"}),
    ]

    @staticmethod
    def es_documents(es, index_name, etype):
        """return all documents of type ``etype`` stored in ES"""
        for doc in scan(
            es,
            index=index_name,
            doc_type="_doc",
            # no fields, limit result size, we only need metadata
            docvalue_fields=(),
        ):
            yield {
                "_op_type": "delete",
                "_index": index_name,
                "_type": "_doc",
                "_id": doc["_id"],
            }

    def run(self, args):
        appid = args.pop()
        with admincnx(appid) as cnx:
            indexer = cnx.vreg["es"].select("indexer", cnx)
            es = indexer.get_connection()
            es_docs = []
            for etype in self.config.etypes:
                es_docs.append(self.es_documents(es, indexer.index_name, etype))
        es_bulk_index(es, chain(*es_docs), raise_on_error=False)


@CWCTL.register
class ReindexIR(Command):
    """reindex IR (PDF / XML) documents stored in the database.

    Internally runs import-ead but only with files referenced in
    the database.
    """

    name = "fa-reindex-ead"
    arguments = "<instance>"
    min_args = max_args = 1

    def run(self, args):
        appid = args.pop()
        with admincnx(appid) as cnx:
            init_bfss(cnx.repo)
            rset = cnx.execute(
                "Any FSPATH(D) WHERE X is FindingAid, " "X findingaid_support F, F data D"
            )
            filepaths = [fspath.getvalue() for fspath, in rset]
            import_filepaths(cnx, filepaths, readerconfig(cnx.vreg.config, appid, True))


@CWCTL.register
class ReindexIRByStableId(Command):
    """reindex one IR (PDF / XML) documents stored in the database.

    Internally runs import-ead but only with files referenced in
    the database.
    """

    name = "fa-es-reindex"
    arguments = "<instance><stable_id>"
    min_args = max_args = 2

    def run(sealf, args):
        appid, stable_id = args
        with admincnx(appid) as cnx:
            init_bfss(cnx.repo)
            rset = cnx.execute(
                """Any FSPATH(D) WHERE X is FindingAid,
                   X findingaid_support F, F data D,
                   X stable_id %(sti)s""", {'sti': stable_id}
            )
            if not rset:
                print("No Findingaid with stable_id {} found".format(stable_id))
                return
            filepaths = [fspath.getvalue() for fspath, in rset]
            import_filepaths(cnx, filepaths, readerconfig(cnx.vreg.config, appid, True))


@CWCTL.register
class ReindexEsService(Command):
    """reindex FindingAid and FAComponent in es by service.

    This command dont delete existing data.

    arguments = '<instance> <service_code> <index>
    """

    name = "fa-reindex-es-service"
    arguments = "<instance>"
    min_args = max_args = 3
    options = [
        (
            "dry-run",
            {
                "type": "yn",
                "default": False,
                "help": "set to True if you want to skip the insertion in ES",
            },
        ),
        ("chunksize", {"type": "int", "default": 100000, "help": "chunksize size"}),
    ]

    def run(self, args):
        appid, service_code, es_index = args
        with admincnx(appid) as cnx:
            service = cnx.execute("Any X WHERE X code %(c)s", {"c": service_code})
            if not service:
                print("No service with code {} exists".format(service_code))
                return
            publisher = service.one().publisher()
            indexer = cnx.vreg["es"].select("indexer", cnx)
            es = indexer.get_connection()
            for _ in parallel_bulk(
                es,
                self.bulk_actions(
                    cnx,
                    publisher,
                    index_name=es_index,
                    chunksize=self.config.chunksize,
                    dry_run=self.config.dry_run,
                ),
                raise_on_error=False,
                raise_on_exception=False,
            ):
                pass

    def bulk_actions(self, cnx, publisher, index_name, chunksize, dry_run=True):
        for etype in ("FindingAid", "FAComponent"):
            gen = self.get_indexable_fa(cnx, etype, publisher, chunksize)
            for idx, entity in enumerate(gen, 1):
                try:
                    serializer = entity.cw_adapt_to("IFullTextIndexSerializable")
                    json = serializer.serialize(complete=False)
                except Exception:
                    cnx.error(
                        "[{}] Failed to serialize entity {} ({})".format(
                            index_name, entity.eid, etype
                        )
                    )
                    continue
                if not dry_run and json:
                    # Entities with
                    # fulltext_containers relations return their container
                    # IFullTextIndex serializer , therefor the "id" and
                    # "doc_type" in kwargs bellow must be container data.
                    data = {
                        "_op_type": "index",
                        "_index": index_name or cnx.vreg.config["index-name"],
                        "_type": "_doc",
                        "_id": serializer.es_id,
                        "_source": json,
                    }
                    yield data

    def get_indexable_fa(self, cnx, etype, publisher, chunksize=100000):
        rqlpart = (
            "X publisher %(p)s, "
            if etype == "FindingAid"
            else "X finding_aid FA, FA publisher %(p)s, "
        )
        lasteid = 0
        rql = (
            "Any X, E, D, U, S ORDERBY X LIMIT {} WHERE "
            "X is {}, E is EsDocument, E entity X, E doc D, "
            "X cwuri U, X stable_id S, "
            "{} "
            "X eid > %(l)s"
        ).format(chunksize, etype, rqlpart)
        while True:
            print("will execute", rql, {"l": lasteid, "p": publisher})
            rset = cnx.execute(rql, {"l": lasteid, "p": publisher})
            print("\tget", len(rset), "rows")
            if not rset:
                break
            for e in rset.entities():
                yield e
            cnx.drop_entity_cache()
            lasteid = rset[-1][0]


@CWCTL.register
class ReindexEsAuthority(Command):
    """reindex FindingAid and FAComponent in es for a given authority in both indexes

    arguments = '<instance> <authority_eid>
    """

    name = "fa-reindex-es-authority"
    arguments = "<instance>"
    min_args = max_args = 2

    def run(self, args):
        appid, eid = args
        with admincnx(appid) as cnx:
            reindex_authority(cnx, eid)


@CWCTL.register
class HarvestRepos(Command):
    """harvest OAI-PMH repositories registered in the database.

    """

    name = "fa-harvest-oai"
    arguments = "<instance>"
    min_args = max_args = 1
    options = [
        (
            "force",
            {
                "action": "store_true",
                "default": False,
                "help": (
                    "force le moissonnage des entrepôts indépendamment "
                    "de la dernière date de moissonnage"
                ),
            },
        ),
        (
            "services",
            {
                "type": "csv",
                "default": (),
                "help": (
                    "Liste services sur lesquels lancer le moissonnage "
                    "(séparés par des virgules). Si la liste est vide, "
                    "tous les services seront moissonnés"
                ),
            },
        ),
    ]

    def run(self, args):
        appid = args.pop()
        with admincnx(appid) as cnx:
            init_bfss(cnx.repo)
            for repo_eid in self.repositories_to_harvest(cnx):
                oai.import_delta(cnx, repo_eid, ignore_last_import=self.config.force)

    def repositories_to_harvest(self, cnx):
        query = "Any R WHERE R is OAIRepository"
        if self.config.services:
            query += ", R service S, S code IN ({})".format(
                ",".join('"%s"' % s.upper() for s in self.config.services)
            )
        return [repo_eid for repo_eid, in cnx.execute(query)]


@CWCTL.register
class RdfDump(Command):
    """harvest OAI-PMH repositories registered in the database.

    """

    name = "fa-rdfdump"
    arguments = "<instance>"
    min_args = max_args = 1
    options = [
        (
            "etypes",
            {
                "type": "csv",
                "default": list(rdfdump.ETYPES_ADAPTERS),
                "help": (
                    "liste des types d'entité à exporter " "de la dernière date de moissonnage"
                ),
            },
        ),
        (
            "output-dir",
            {
                "type": "string",
                "default": "/tmp",
                "help": ("répertoire dans lequel les archives seront créées"),
            },
        ),
        (
            "formats",
            {
                "type": "csv",
                "default": ("nt", "n3", "xml"),
                "help": ("liste des formats dans lequel on veut sérialiser le rdf"),
            },
        ),
    ]

    def run(self, args):
        appid = args.pop()
        with admincnx(appid) as cnx:
            rdfdump.create_dumps(cnx, self)


class InitDatabase(Command):
    """Initialize the database **in the default namespace** but do NOT
fill it with anything, and create entity tables for CMS entities
and their relations in the namespace defined in the db-namespace config
option

    """

    name = "db-init-tables"
    arguments = "<instance>"
    min_args = max_args = 1
    options = (
        (
            "drop",
            {
                "short": "d",
                "action": "store_true",
                "default": False,
                "help": "insert drop statements to remove previously existant "
                "tables, indexes... (no by default)",
            },
        ),
    )

    def run(self, args):
        print("\n" + underline_title("Initializing the system database"))
        appid = args[0]
        config = ServerConfiguration.config_for(appid)
        try:
            system = config.system_source_config
            sqlschema = system.pop("db-namespace")
            extra_args = system.get("db-extra-arguments")
            extra = extra_args and {"extra_args": extra_args} or {}
            cnx = get_connection(
                system["db-driver"],
                database=system["db-name"],
                host=system.get("db-host"),
                port=system.get("db-port"),
                user=system.get("db-user") or "",
                password=system.get("db-password") or "",
                **extra
            )
        except Exception as ex:
            raise ConfigurationError(
                "You seem to have provided wrong connection information in "
                "the %s file. Resolve this first (error: %s)."
                % (config.sources_file(), str(ex).strip())
            )
        init_repository(config, drop=self.config.drop)

        from cubicweb_francearchives.utils import setup_published_schema

        etypes = list(CMS_OBJECTS) + ["CWProperty"]
        rtypes = ("in_state", "children", "news_image")
        with cnx.cursor() as cursor:
            setup_published_schema(cursor.execute, etypes, rtypes, sqlschema=sqlschema)
            cnx.commit()
        print("DONE")


@CWCTL.register
class EnhanceAccessibility(Command):
    """
    Apply some RGAA rules to CMS HTML content.
    For exemple:
     - add missing `alt` attribute on image
     - add `_blank` traget in extrenal links, etc
    """

    name = "rgaa"
    arguments = "<instance>"
    min_args = max_args = 1
    options = (("replace", {"short": "r", "action": "store_true", "help": "replace all content"}),)

    def run(self, args):
        appid = args.pop()
        replace_all = self.config.replace
        with admincnx(appid) as cnx:
            init_bfss(cnx.repo)
            with cnx.allow_all_hooks_but("metadata"):
                """XXX Images/CSSImage.caption and description are not processed so far"""
                count = 0
                query = (
                    'Any X, C WHERE X content C, X content_format "text/html", '
                    "X is IN (%(etypes)s), NOT X content NULL"
                )
                for eid, c in cnx.execute(query % {"etypes": ", ".join(list(CMS_OBJECTS))}):
                    content = enhance_accessibility(c, cnx, eid=eid)
                    if replace_all or content != c:
                        count += 1
                        cnx.execute(
                            "SET X content %(c)s WHERE X eid %(eid)s", {"eid": eid, "c": content}
                        )
                        cnx.commit()
                map_query = (
                    "Any X, T, B WHERE X is Map, "
                    "X top_content T, NOT X top_content NULL, "
                    'X top_content_format "text/html", '
                    "X bottom_content B, NOT X  bottom_content NULL, "
                    'X bottom_content_format "text/html"'
                )
                for eid, top, bottom in cnx.execute(map_query):
                    top = enhance_accessibility(top, cnx, eid=eid)
                    bottom = enhance_accessibility(bottom, cnx, eid=eid)
                    count += 1
                    cnx.execute(
                        "SET X top_content %(t)s, X bottom_content %(b)s WHERE X eid %(eid)s",
                        {"eid": eid, "t": top, "b": bottom},
                    )
                    cnx.commit()
                service_query = (
                    'Any X, O WHERE X other O, X other_format "text/html", '
                    "X is Service,  NOT X other NULL"
                )
                for eid, o in cnx.execute(service_query):
                    other = enhance_accessibility(o, cnx)
                    if replace_all or other != o:
                        count += 1
                        cnx.execute(
                            "SET X other %(o)s WHERE X eid %(eid)s", {"eid": eid, "o": other}
                        )
                        cnx.commit()
            print("fixed {} entities".format(count))


@CWCTL.register
class GenerateApeEadFiles(Command):
    """Generate ApeEad files for all FindingAids"""

    arguments = "<instance>"
    name = "generate-ape-ead"
    min_args = 1
    max_args = 3
    options = [
        (
            "all",
            {
                "action": "store_true",
                "default": False,
                "help": ("generate ape-ead files for all ir"),
            },
        ),
        (
            "service",
            {
                "short": "s",
                "type": "string",
                "help": ("generate ape_ead files for all ir in service"),
            },
        ),
    ]

    def run(self, args):
        """call generate_ape_ead from dataimport.ape_ead"""
        self.appid = args.pop(0)
        with admincnx(self.appid) as cnx:
            generate_ape_ead_files(cnx, self.config.all, service_code=self.config.service)


@CWCTL.register
class GenerateOaiRedirections(Command):
    """Create FindingAid and FAComponent nginx redirections files
       from data stored in fa_redirects sql table
    """

    name = "gen-fa-redirects"
    arguments = "<instance>"
    min_args = max_args = 1

    def run(self, args):
        appid = args.pop()
        with admincnx(appid) as cnx:
            write_nginx_confs(cnx)


for cmdclass in (
    ImportEAD,
    ImportEAC,
    ImportOai,
    ImportAll,
    ImportDC,
    ImportDirectories,
    IndexESAutocomplete,
    PniaIndexInEs,
    GenRedirect,
    ImportMaps,
    InitDatabase,
    EnhanceAccessibility,
    GenerateApeEadFiles,
):
    CWCTL.register(cmdclass)
i18n.register_cwctl_commands()
