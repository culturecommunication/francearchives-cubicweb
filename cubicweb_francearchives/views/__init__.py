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

"""cubicweb-francearchives views/forms/actions/components for web ui"""

import os.path as osp

from urllib.parse import urlparse, parse_qs, urlunsplit, urlsplit

from babel import dates as babel_dates, numbers as babel_numbers, Locale

from jinja2 import Environment, PackageLoader

import yaml
from yaml.parser import ParserError

from cwtags import tag as T

from logilab.mtconverter import xml_escape
from logilab.common.decorators import monkeypatch

from cubicweb.pyramid.core import CubicWebPyramidRequest
from cubicweb.web.views.bookmark import BookmarksBox
from cubicweb.web.views.boxes import SearchBox, EditBox
from cubicweb.web.views.basecomponents import RQLInputForm, MetaDataComponent
from cubicweb.web.views.baseviews import InContextView

from cubicweb_francearchives.utils import is_external_link


_ = str

HERE = osp.dirname(__file__)
PORTAL_CONFIG = None

env = Environment(loader=PackageLoader("cubicweb_francearchives.views"))

STRING_SEP = "#####"


def get_template(template_name):
    return env.get_template(template_name)


def format_date(date, req):
    if date:
        try:
            return babel_dates.format_date(date, format="short", locale=req.lang)
        except Exception as exc:
            req.warning("failed to format date %s with locale %s because %s", date, req.lang, exc)
            return ""
    return ""


def format_agent_date(cnx, date, precision="d", isbc=False, iso=True):
    year = date.year
    if isbc:
        template = "{{template}} {bc}".format(bc=cnx._("bc"))
        if iso:
            # https://en.wikipedia.org/wiki/ISO_8601#Years
            # 0000 is 1BC -0001 is 2BC and so on
            year += 1
    else:
        template = "{template}"
    if precision in ("d", "m"):
        lc = cnx.lang
        month = Locale(lc).months["format"]["wide"][date.month]
    else:
        month = ""
    return template.format(
        template={
            "d": "{date.day:2d} {month} {year:04d}",
            "m": "{month} {year:04d}",
            "y": "{year:04d}",
        }[precision].format(date=date, year=year, month=month)
    )


def format_number(number, req):
    if number is not None:
        try:
            return babel_numbers.format_number(number, locale=req.lang)
        except Exception as exc:
            req.warning(
                "failed to format number %s with locale %s because %s", number, req.lang, exc
            )
            return ""
    return ""


env.filters["format_number"] = format_number


def top_sections_desc(cnx):
    """retrive info for the 3 top sections"""
    top_sections = []
    sections = (("decouvrir", "discover"), ("comprendre", "understand"), ("gerer", "manage"))
    infos = {
        n: (t, d, s)
        for n, t, d, s in cnx.execute(
            (
                "Any N, T, D, S WHERE X is Section, "
                "X name N, X title T, X short_description D, "
                "X subtitle S, X name IN (%s)"
            )
            % ",".join('"%s"' % s[0] for s in sections)
        )
    }
    for name, cssclass in sections:
        title, desc, label = infos.get(name, (None, None, None))
        if title:
            # may not exist (in tests)
            top_sections.append((title.upper(), label, name, cssclass, desc or ""))
    return top_sections


class JinjaViewMixin(object):
    template = None

    def call_template(self, **ctx):
        self.w(self.template.render(**ctx))


@monkeypatch(CubicWebPyramidRequest)
def relative_path(self, includeparams=True):
    path = self._request.path_info[1:]
    if self.lang:
        langprefix = self.lang + "/"
        if path.startswith(langprefix):
            path = path[len(langprefix) :]
    if includeparams and self._request.query_string:
        return "%s?%s" % (path, self._request.query_string)
    return path


def load_portal_config(cwconfig):
    global PORTAL_CONFIG
    if PORTAL_CONFIG is None:
        lookup_paths = [
            osp.join(cwconfig.apphome, "portal_config.yaml"),
            osp.join(HERE, "portal_config.yaml"),
        ]
        for filepath in lookup_paths:
            if osp.isfile(filepath):
                try:
                    with open(filepath, "r") as f:
                        PORTAL_CONFIG = yaml.load(f)
                        cwconfig.info("loaded portal config from file %r", filepath)
                        break
                except ParserError:
                    cwconfig.error("ignoring invalid yaml file %r", filepath)
        else:
            cwconfig.warning("failed to find a valid YAML portal config file")
            PORTAL_CONFIG = {}
    return PORTAL_CONFIG


def twitter_account_name(cwconfig):
    portal_config = load_portal_config(cwconfig)
    twitter_account_url = portal_config.get("sn", {}).get("twitter", {}).get("url", "")
    return "@" + twitter_account_url.rsplit("/", 1)[-1]


def rebuild_url(req, url=None, **newparams):
    """Override `cubicweb.req.RequestSessionbase.rebuild_url` implementation.

    Behaviour is the same except that query values can be removed by
    specifying a ``None`` value in ``newparams``.
    """
    if url is None:
        path = req.relative_path(includeparams=True)
        if req.lang:
            path = "{}/{}".format(req.lang, path)
        url = req.base_url() + path
    schema, netloc, path, query, fragment = urlsplit(url)
    query = parse_qs(query)
    # sort for testing predictability
    for key, val in sorted(newparams.items()):
        # <cw-patch>: remove query parameter if new value is None
        if val is None:
            query.pop(key, None)
        # </cw-patch>
        else:
            if not isinstance(val, (list, tuple)):
                val = (val,)
            query[key] = val
    query = "&".join(
        "%s=%s" % (param, req.url_quote(value))
        for param, values in sorted(query.items())
        for value in values
    )
    return urlunsplit((schema, netloc, path, query, fragment))


def html_link(cnx, url, label=None, icon=None):
    if is_external_link(url, cnx.base_url()):
        return exturl_link(cnx, url, label=label, icon=icon)
    return internurl_link(cnx, url, label=label, icon=icon)


def internurl_link(cnx, url, label=None, icon=None, title=None):
    url = xml_escape(url)
    if label is None:
        label = url
    else:
        label = xml_escape(label)
    if icon is None:
        link_content = label
    else:
        link_content = T.span(
            "{} {}".format(T.i(_class="fa fa-{}".format(icon), aria_hidden="true"), label),
            _class="nowrap",
        )
    if title:
        return T.a(link_content, href=url, title=title)
    return T.a(link_content, href=url)


def exturl_link(cnx, url, label=None, icon=None):
    url = xml_escape(url)
    if label is None:
        label = url
        title = blank_link_title(cnx, url)
    else:
        title = "{} {}".format(label, cnx._("- New window"))
    if icon is None:
        link_content = label
    else:
        link_content = T.span(
            "{} {}".format(T.i(_class="fa fa-{}".format(icon), aria_hidden="true"), label),
            _class="nowrap",
        )
    return T.a(
        link_content, href=url, target="_blank", rel="nofollow noopener noreferrer", title=title
    )


def blank_link_title(cnx, site):
    site = urlparse(site).netloc or site
    return "{} {} {}".format(cnx._("Go to the site:"), site, cnx._("- New window"))


@monkeypatch(InContextView)
def cell_call(self, row, col):
    entity = self.cw_rset.get_entity(row, col)
    desc = entity.dc_description()
    self.w(internurl_link(self._cw, entity.absolute_url(), label=entity.dc_title(), title=desc))


def registration_callback(vreg):
    vreg.register_all(list(globals().values()), __name__)
    vreg.unregister(BookmarksBox)
    vreg.unregister(SearchBox)
    vreg.unregister(RQLInputForm)
    vreg.unregister(EditBox)
    vreg.unregister(MetaDataComponent)
