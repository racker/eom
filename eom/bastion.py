# Copyright (c) 2013 Rackspace, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR ONDITIONS OF ANY KIND, either express or
# implied.
#
# See the License for the specific language governing permissions and
# limitations under the License.

"""bastion: A WSGI middleware that serves as a simple gate keeper.

Its primary function is to provide a way to bypass certain layers of
the middleware wrapping onion, particularly for the purpose of
allowing special access to /health -type endpoints for a load balancer
(LB).

Here, skipping layers is referred to as "using the backdoor" and the
standard entry point for the app is referred to as "gated entry".

Wrapping with the bastion looks like:

    backdoor = marconi.queues.transport.wsgi.app.app
    gated = UriTransformer.wrap(Authentication.wrap(backdoor))
    app = bastion.wrap(backdoor, gated)

The control flow is as follows:

1. If the route being accessed is present in the restricted list, use
   the backdoor. However, if X-Forwarded-For is present, return 404.
2. Otherwise, proceed through the gate.

The configuration is given as a comma-separated list of paths, e.g.:

    [eom:bastion]
    restricted_routes = /v1/health, /v1/stats

Routes may also be separated by newlines, e.g.:

    restricted_routes =
        /v1/health
        /v1/stats

"""

import logging

from oslo.config import cfg


OPT_GROUP_NAME = 'eom:bastion'
OPTIONS = [
    cfg.ListOpt('restricted_routes',
                help='List of paths to gate.',
                default=[])
]

LOG = logging.getLogger(__name__)


def _http_gate_failure(start_response):
    """Responds with HTTP 404"""
    start_response('404 Not Found', [('Content-Length', '0')])
    return []


def wrap(app_backdoor, app_gated):
    """Creates a backdoor to a set of routes for the app.

    :param app_backdoor: an entry point in the app that bypasses middleware
    :type app_backdoor: wsgi_app
    :param app_gated: app all wrapped and safe
    :type app_gated: wsgi_app
    :returns: a new WSGI app that wraps the original with bastion powers
    :rtype: wsgi_app
    """
    conf = cfg.CONF

    conf.register_opts(OPTIONS, group=OPT_GROUP_NAME)
    restricted_routes = conf[OPT_GROUP_NAME].restricted_routes

    # WSGI callable
    def middleware(env, start_response):
        path = env['PATH_INFO']
        contains_x_forward = 'HTTP_X_FORWARDED_FOR' in env
        for route in restricted_routes:
            if route == path:
                if not contains_x_forward:
                    return app_backdoor(env, start_response)
                else:
                    return _http_gate_failure(start_response)

        # NOTE(cabrera): not special route - keep calm and WSGI on
        return app_gated(env, start_response)

    return middleware
