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
"""cubicweb-francearchives application package

FranceArchives
"""
import os
import os.path as osp
import stat


import psycopg2

from pyramid.settings import asbool

from logilab.common.decorators import monkeypatch

from cubicweb.__pkginfo__ import numversion as cwversion
from cubicweb.cwctl import init_cmdline_log_threshold
from cubicweb.cwconfig import CubicWebConfiguration
from cubicweb.entity import Entity, TransformData, ENGINE
from cubicweb.server.repository import Repository
from cubicweb.server.utils import scheduler
from cubicweb.server.sources import storages
from cubicweb import repoapi

from cubicweb_francearchives.__pkginfo__ import numversion as faversion

from cubicweb_elasticsearch import es

from cubicweb_francearchives.cssimages import static_css_dir
from cubicweb_francearchives.htmlutils import soup2xhtml

# make sure psycopg2 always return unicode strings,
# cf. http://initd.org/psycopg/docs/faq.html#faq-unicode
psycopg2.extensions.register_type(psycopg2.extensions.UNICODE)
psycopg2.extensions.register_type(psycopg2.extensions.UNICODEARRAY)

GLOSSARY_CACHE = []


def get_user_agent():
    def format_version(numversion):
        return ".".join(str(i) for i in numversion)

    user_agent = (
        "FranceArchives/{faversion} (francearchives.siaf@culture.gouv.fr) CubicWeb/{cwversion}"
    )
    return user_agent.format(
        faversion=format_version(faversion), cwversion=format_version(cwversion)
    )


# safety belt to register a custom, hard-coded list of indexable types to avoid
# indexing Files, EmailAddress (or any unwanted entity type) by mistake

es.INDEXABLE_TYPES = [
    "Section",
    "CommemorationItem",
    "BaseContent",
    "Card",
    "NewsContent",
    "Circular",
    "Service",
    "CommemoCollection",
    "Map",
    "ExternRef",
    "Person",
    "FindingAid",
    "FAComponent",
    "File",
    "BaseContentTranslation",
    "SectionTranslation",
    "CommemorationItemTranslation",
]


SUPPORTED_LANGS = ("fr", "en", "de", "es")

SOCIAL_NETWORK_LIST = (
    "facebook",
    "twitter",
    "storify",
    "flickr",
    "wikimedia",
    "rss",
    "dailymotion",
    "blog",
    "pinterest",
    "foursquare",
    "scoop it",
    "vimeo",
    "youtube",
    "instagram",
)

CMS_OBJECTS = (
    "Section",
    "BaseContent",
    "NewsContent",
    "Circular",
    "CommemorationItem",
    "CommemoCollection",
    "ExternRef",
    "Map",
)

ES_CMS_I18N_OBJECTS = (
    "SectionTranslation",
    "BaseContentTranslation",
    "CommemorationItemTranslation",
)

CMS_I18N_OBJECTS = ES_CMS_I18N_OBJECTS + ("FaqItemTranslation",)

FIRST_LEVEL_SECTIONS = {"decouvrir", "comprendre", "gerer"}


class Authkey(object):
    def __init__(self, fa_stable_id, type, label, role):
        self.fa_stable_id = fa_stable_id
        self.type = type
        self.label = label
        self.role = role

    def as_tuple(self):
        return (self.fa_stable_id, self.type, self.label, self.role)


def register_auth_history(cnx, key, autheid):
    """make sure all of fa_stable_id, type, label, indexrole values are different
    from NONE, otherwise the ON CONFLICT statement does not work (SQL may be
    testing NULL = NULL instead of NULL is NULL)
    """
    cnx.system_sql(
        "INSERT INTO authority_history (fa_stable_id, type, label, indexrole, autheid) VALUES "
        "(%(fa)s, %(type)s, %(l)s, %(role)s, %(a)s) "
        "ON CONFLICT (fa_stable_id, type, label, indexrole) DO UPDATE SET autheid = EXCLUDED.autheid",  # noqa
        {
            "fa": key.fa_stable_id,
            "type": key.type,
            "l": key.label,
            "role": key.role or "index",
            "a": autheid,
        },
    )


class FABfssStorage(storages.BytesFileSystemStorage):
    wmode = stat.S_IRUSR | stat.S_IWUSR

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("wmode", self.wmode)
        super(FABfssStorage, self).__init__(*args, **kwargs)

    def new_fs_path(self, entity, attr):
        relpath = entity.bfss_storage_relpath(attr)
        fspath = osp.join(self.default_directory, relpath)
        destdir = osp.dirname(fspath)
        # XXX handle broken symlinks ? race conditions ?
        if not osp.isdir(destdir):
            os.makedirs(destdir)
        if osp.isfile(fspath):
            flags = os.O_RDWR | os.O_TRUNC | os.O_NOFOLLOW
        else:
            flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        fd = os.open(fspath, flags, self.wmode)
        return fd, fspath

    def entity_deleted(self, entity, attr):
        """an entity using this storage for attr has been deleted.
        Francearchives customization:
          while deleting a CWFile, only delete the referenced file from FS
          if there is no other CWFile referencing the same filepath (e.g same cw_data)
        """
        fpath = self.current_fs_path(entity, attr)
        if fpath is not None:
            sys_source = entity._cw.repo.system_source
            sql_query = """
            SELECT count(f.cw_eid) FROM cw_file f
            JOIN cw_file f1 ON f.cw_{attr}=f1.cw_{attr}
            WHERE f1.cw_eid =%(eid)s
                  AND f.cw_eid!=%(eid)s;
            """.format(
                attr=attr
            )
            attrs = {"eid": entity.eid}
            cu = sys_source.doexec(entity._cw, sql_query, attrs)
            res = cu.fetchone()[0]
            # only delete the file if there is no more cw_files referencing the same
            # fspath
            if not res:
                storages.DeleteFileOp.get_instance(entity._cw).add_data(fpath)


def admincnx(appid, loglevel=None):
    config = CubicWebConfiguration.config_for(appid)
    config["connections-pool-size"] = 2

    login = config.default_admin_config["login"]
    password = config.default_admin_config["password"]

    if loglevel is not None:
        init_cmdline_log_threshold(config, loglevel)

    repo = Repository(config, scheduler=scheduler())
    repo.bootstrap()
    return repoapi.connect(repo, login, password=password)


def init_bfss(repo):
    bfssdir = repo.config["appfiles-dir"]
    if not osp.exists(bfssdir):
        os.makedirs(bfssdir)
        print("created {}".format(bfssdir))
    storage = FABfssStorage(bfssdir)
    storages.set_attribute_storage(repo, "File", "data", storage)


def check_static_css_dir(repo):
    if repo.config.name != "all-in-one":
        return
    directory = static_css_dir(repo.config.static_directory)
    if not osp.isdir(directory):
        repo.critical(
            "static css files directory {} does not exist. Trying to create it".format(directory)
        )
        try:
            os.makedirs(directory)
        except Exception:
            repo.critical("could not create static css files directory {}".format(directory))
            raise
    if not os.access(directory, os.W_OK):
        raise ValueError('static css directory "{}" is not writable'.format(directory))


def includeme(config):
    if asbool(config.registry.settings.get("francearchives.autoinclude", True)):
        config.include(".pviews")
        config.include(".pviews.catch_all")


@monkeypatch(Entity)
def _cw_mtc_transform(self, data, format, target_format, encoding, _engine=ENGINE):
    trdata = TransformData(data, format, encoding, appobject=self)
    data = _engine.convert(trdata, target_format).decode()
    if target_format == "text/html":
        data = soup2xhtml(data, self._cw.encoding)
    return data


def create_homepage_metadata(cnx):
    cnx.create_entity(
        "Metadata",
        uuid="metadata-homepage",
        title="FranceArchives.fr",
        description="Portail National des Archives de France",
        type="website",
    )
