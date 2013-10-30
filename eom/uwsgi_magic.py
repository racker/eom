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

import logging
import re

from oslo.config import cfg
import simplejson as json
import uwsgi  # Injected by host server, assuming it's uWSGI!

LOG = logging.getLogger(__name__)
CONF = cfg.CONF

OPT_GROUP_NAME = 'eom:uwsgi'
OPTION_NAME = 'options_file'

CONF.register_opt(cfg.StrOpt(OPTION_NAME), group=OPT_GROUP_NAME)


def _load_options(path):
    full_path = CONF.find_file(path)
    if not full_path:
        raise cfg.ConfigFilesNotFoundError([path])

    with open(full_path) as fd:
        return json.load(fd)


def _prepare_logvar_map(options):
    """Normalize header names to WSGI style to improve performance."""
    raw_map = options['logvar_map']

    return [
        ('HTTP_' + header.replace('-', '_').upper(), logvar)
        for header, logvar in raw_map.iteritems()
    ]


# NOTE(kgriffs): Using a functional style since it is more
# performant than an object-oriented one (middleware should
# introduce as little overhead as possible.)
def wrap(app):
    """Wrap a WSGI app with ACL middleware.

    Takes configuration from oslo.config.cfg.CONF.

    :param app: WSGI app to wrap
    :returns: a new WSGI app that wraps the original
    """
    group = CONF[OPT_GROUP_NAME]
    options_path = group[OPTION_NAME]
    options = _load_options(options_path)
    logvar_map = _prepare_logvar_map(options)

    # WSGI callable
    def middleware(env, start_response):
        # NOTE(kgriffs): For now, this is the only thing the
        # middleware does, so keep it inline.
        for header_name, logvar_name in logvar_map:
            try:
                value = env[header_name]
            except KeyError:
                value = 'None'

            uwsgi.set_logvar(logvar_name, value)

        # Carry on
        return app(env, start_response)

    return middleware
