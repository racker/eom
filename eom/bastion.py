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
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
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

1. If the route being accessed is present in the unrestricted list, use
   the backdoor. However, if X-Forwarded-For is present, return 404.
2. Otherwise, proceed through the gate.

The configuration is given as a comma-separated list of paths, e.g.:

    [eom:bastion]
    unrestricted_routes = /v1/health, /v1/stats

Routes may also be separated by newlines, e.g.:

    unrestricted_routes =
        /v1/health
        /v1/stats

"""

from oslo_config import cfg

from eom.utils import log as logging

_CONF = cfg.CONF
LOG = logging.getLogger(__name__)

OPT_GROUP_NAME = 'eom:bastion'
OPTIONS = [
    cfg.ListOpt(
        'unrestricted_routes',
        help='List of paths to allow through the gate.',
        default=[]
    ),
    cfg.ListOpt(
        'gate_headers',
        help=(
            "List of wsgi 'HTTP_' headers. If all of the headers are present, "
            "deny access to gated app."
        ),
        default=[]
    )
]


def configure(config):
    global _CONF
    global LOG

    _CONF = config
    _CONF.register_opts(OPTIONS, group=OPT_GROUP_NAME)

    logging.register(_CONF, OPT_GROUP_NAME)
    logging.setup(_CONF, OPT_GROUP_NAME)
    LOG = logging.getLogger(__name__)


def get_conf():
    global _CONF
    return _CONF[OPT_GROUP_NAME]


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
    unrestricted_routes = _CONF[OPT_GROUP_NAME].unrestricted_routes
    gate_headers = _CONF[OPT_GROUP_NAME].gate_headers

    # WSGI callable
    def middleware(env, start_response):
        path = env['PATH_INFO']
        contains_gate_headers = set(gate_headers).issubset(set(env.keys()))
        for route in unrestricted_routes:
            if route == path:
                if not contains_gate_headers:
                    return app_backdoor(env, start_response)
                else:
                    return _http_gate_failure(start_response)

        # NOTE(cabrera): not special route - keep calm and WSGI on
        return app_gated(env, start_response)

    return middleware
