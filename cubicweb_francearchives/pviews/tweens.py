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
from pyramid.settings import asbool

from cubicweb_francearchives import SUPPORTED_LANGS


def sanitize_parameters_tween_factory(handler, registry):
    unauthorized_form_params = {
        # unauhtorized_param: (excepted_values)
        '__message': None,
        'rql': None,
        '__login': None,
        '__password': None,
        '__notemplate': None,
        '__lang': None,
        'debug-es': None,
        'vid': ('download',),
    }

    def sanitize_parameters_tween(request):
        cwreq = request.cw_request
        for param, value in cwreq.form.items():
            if param in unauthorized_form_params:
                authorized_values = unauthorized_form_params[param]
                if authorized_values is None or value not in authorized_values:
                    cwreq.form.pop(param)
        return handler(request)

    return sanitize_parameters_tween


def langprefix_tween_factory(handler, registry):

    def langprefix_tween(request):
        cwreq = request.cw_request
        for lang in SUPPORTED_LANGS:
            prefix = '/{}/'.format(lang)
            if request.path_info.startswith(prefix):
                request.path_info = request.path_info[3:]
                lang = prefix[1:-1]
                cwreq.set_language(lang)
                break
        else:
            lang = cwreq.negotiated_language() or 'fr'
            cwreq.set_language(lang)
        response = handler(request)
        response.content_language = lang
        return response

    return langprefix_tween


def https_tween_factory(handler, registry):
    def https_tween(request):
        cwreq = request.cw_request
        if cwreq.vreg.config.get('base-url', '').startswith('https'):
            request.scheme = 'https'
        return handler(request)
    return https_tween


def script_name_factory(handler, registry):
    def script_name_factory(request):
        environ = request.environ
        script_name = environ.get('HTTP_X_SCRIPT_NAME', '')
        if script_name:
            environ['SCRIPT_NAME'] = script_name
            path_info = environ['PATH_INFO']
            if path_info.startswith(script_name):
                environ['PATH_INFO'] = path_info[len(script_name):]
        scheme = environ.get('HTTP_X_SCHEME', '')
        if scheme:
            environ['wsgi.url_scheme'] = scheme
        return handler(request)
    return script_name_factory


def includeme(config):
    config.add_tween('cubicweb_francearchives.pviews.tweens.langprefix_tween_factory')
    config.add_tween('cubicweb_francearchives.pviews.tweens.https_tween_factory')
    config.add_tween('cubicweb_francearchives.pviews.tweens.script_name_factory')
    if asbool(config.registry.settings.get('francearchives.sanitize_params', True)):
        config.add_tween('cubicweb_francearchives.pviews.tweens.sanitize_parameters_tween_factory')
