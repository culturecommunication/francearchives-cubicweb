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
from __future__ import print_function

from glob import glob
import os.path as osp
import sys

from six import text_type

from pyramid.view import view_config
from pyramid.response import Response, FileResponse
from pyramid.httpexceptions import HTTPNotFound, HTTPFound

from cubicweb_francearchives.pviews.helpers import update_headers


def static_file(request, filepath):
    if osp.isfile(filepath):
        return FileResponse(filepath, request=request)
    return HTTPNotFound()


@view_config(route_name='static',
             request_method=('GET', 'HEAD'))
def static_asset_view(request):
    asset_relpath = request.matchdict['relpath']
    if isinstance(asset_relpath, text_type):
        asset_relpath = asset_relpath.encode(sys.getfilesystemencoding())
    first_segment = asset_relpath.split('/', 1)[0]
    cwconfig = request.registry['cubicweb.config']
    filepath = osp.join(cwconfig['appfiles-dir'],
                        '*_static_{}.*'.format(first_segment))
    res = glob(filepath)
    if res:
        basename = osp.basename(res[0])
        hash, basename = basename.split('_', 1)
        location = request.route_path('bfss', hash=hash,
                                      basename=basename)
        return HTTPFound(location=location)
    return static_file(request,
                       osp.join(cwconfig.static_directory, asset_relpath))


@view_config(route_name='data',
             request_method=('GET', 'HEAD'))
def data_asset_view(request):
    asset_relpath = request.matchdict['relpath']
    cwconfig = request.registry['cubicweb.config']
    md5 = cwconfig.instance_md5_version()
    if asset_relpath.startswith(md5):
        asset_relpath = asset_relpath[len(md5) + 1:]
    dirpath, rid = cwconfig.locate_resource(asset_relpath)
    if dirpath is None:
        return HTTPNotFound()
    return static_file(request, osp.join(dirpath, rid))


def startup_view_factory(vid, status_code=200):
    def _view(request):
        return cw_startup_view(vid, request, status_code)
    return _view


def cw_startup_view(vid, request, status_code=200):
    cwreq = request.cw_request
    viewsreg = cwreq.vreg['views']
    view = viewsreg.select(vid, cwreq, rset=None)
    return update_headers(cwreq, Response(
        viewsreg.main_template(cwreq, 'main-template', rset=None, view=view),
        status_code=status_code))


@view_config(route_name='home',
             request_method=('GET', 'HEAD'))
def home_view(request):
    return cw_startup_view('index', request)


@view_config(route_name='bfss',
             request_method=('GET', 'HEAD'))
def bfss_download_view(request):
    cwconfig = request.registry['cubicweb.config']
    filepath = osp.join(cwconfig['appfiles-dir'],
                        '{hash}_{basename}'.format(**request.matchdict))
    return static_file(request, filepath)


@view_config(route_name='ape-bfss',
             request_method=('GET', 'HEAD'))
def ape_bfss_download_view(request):
    cwconfig = request.registry['cubicweb.config']
    filepath = osp.join(cwconfig['appfiles-dir'], 'ape-ead',
                        request.matchdict['servicecode'],
                        request.matchdict['basename'])
    return static_file(request, filepath)


def includeme(config):
    config.add_route('home', '/')
    config.add_route('static', '/static/{relpath:.*}')
    config.add_route('data', '/data/{relpath:.*}')
    config.add_route('bfss', '/file/{hash}/{basename}')
    config.add_route('ape-bfss', '/file/{hash}/ape-ead/{servicecode}/{basename}')
    config.scan(__name__)
