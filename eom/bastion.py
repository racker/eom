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

"""bastion: A WSGI middleware that serves as a basic gate keeper.

Its primary function is to provide a way to bypass certain layers of
the middleware wrapping onion, particularly for the purpose of
allowing special access to /health -type endpoints for a load balancer
(LB).

Wrapping with the bastion looks like:

    # Example: middleware app order is important!
    wrapped_app = UriTransformer.wrap(Authentication.wrap(core))
    app = bastion.wrap(core, wrapped_app)

The control flow is as follows:

1. If the X-Forwarded-For header is NOT present, bypass the middleware
and go straight to the app.
2. If the route being accessed is present in the whitelist, bypass the
middleware and go straight to the app.
3. Otherwise, proceed as normal (through the middleware layer).

A configuration file is given as a list of routes in JSON:

[
  "/v1/health",
  "/v1/stats"
]

"""

import json
import logging
import re

from oslo.config import cfg


LOG = logging.getLogger(__name__)


def _load_whitelist(conf):
    """Load routes file and turn them into compiled re objects.

    :param conf: Configuration object
    :type conf: oslo.config.cfg.ConfigOpts
    :returns: compiled re objects
    :rtype: type(re.compile(''))
    :raises: IOError|FileNotFoundError, ValueError, ConfigFilesNotFoundError
    """
    routes = None
    path = conf['eom:bastion'].routes_file
    full_path = conf.find_file(path)
    if not full_path:
        raise cfg.ConfigFilesNotFoundError([path])

    with open(full_path) as f:
        routes = json.load(f)

    return [re.compile(r + '$') for r in routes]


def wrap(app, wrapped_app):
    """Wrap a pipeline of WSGI apps with this bastion.

    :param app: wrap layer you'd like to jump to - usually, a naked app
    :type app: wsgi_app
    :param wrapped_app: wrapped WSGI application
    :type wrapped_app: wsgi_app
    :returns: a new WSGI app that wraps the original with bastion powers
    :rtype: wsgi_app
    """
    conf = cfg.CONF

    OPT_GROUP_NAME = 'eom:bastion'
    OPTIONS = [
        cfg.StrOpt('routes_file',
                   help='A JSON file serving as a routes whitelist.',
                   default='routes.json')
    ]

    conf.register_opts(OPTIONS, group=OPT_GROUP_NAME)
    routes = _load_whitelist(conf)  # load paths to match against

    # WSGI callable
    def middleware(env, start_response):
        path = env['PATH_INFO']
        forwarded = env.get('X_FORWARDED_FOR') is not None
        for route in routes:
            if route.match(path):
                # NOTE(cabrera): skip to last app in pipeline
                return app(env, start_response)

        # NOTE(cpp-cabrera): this is a request from a LB, or an
        # attacker has bypassed the LB - allow it to proceed to the
        # core application.
        if not forwarded:
            return app(env, start_response)

        # NOTE(cabrera): not whitelisted, not from a LB - proceed as usual
        return wrapped_app(env, start_response)

    return middleware
