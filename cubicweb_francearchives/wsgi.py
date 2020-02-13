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

import os

from cubicweb.cwconfig import CubicWebConfiguration as cwcfg
from cubicweb.pyramid import wsgi_application_from_cwconfig


def with_proxy(app):
    # copied and adapted from http://flask.pocoo.org/snippets/35/
    def proxy_decorator(environ, start_response):
        script_name = environ.get("HTTP_X_SCRIPT_NAME", "")
        if script_name:
            environ["SCRIPT_NAME"] = script_name
            path_info = environ["PATH_INFO"]
            if path_info.startswith(script_name):
                environ["PATH_INFO"] = path_info[len(script_name) :]
        scheme = environ.get("HTTP_X_SCHEME", "")
        if scheme:
            environ["wsgi.url_scheme"] = scheme
        return app(environ, start_response)

    return proxy_decorator


def wsgi_application(instance_name=None, debug=None):
    if instance_name is None:
        instance_name = os.environ["CW_INSTANCE"]
    if debug is None:
        debug = "CW_DEBUG" in os.environ

    cwconfig = cwcfg.config_for(instance_name, debugmode=debug)

    app = wsgi_application_from_cwconfig(cwconfig)
    repo = app.application.registry["cubicweb.repository"]
    # repo.start_looping_tasks()
    repo.hm.call_hooks("server_startup", repo=repo)
    return with_proxy(app)
