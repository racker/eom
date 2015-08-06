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

"""logvar_mapper: maps HTTP headers to uwsgi logvars

This modules helps you capture information from the WSGI/HTTP headers
and logs them to your uwsgi log.

Given a CONF-formatted configuration file with the following section:

[eom:uwsgi:mapper]
options_file = <file_name>

It'll load from <file_name>, say, *map.json*. The options_file should
look like:

{
    "map": {
        "X-Project-Id": "project",
        "X-Forwarded-For": "lb_ip"
    }
}

* The keys are case-insensitive HTTP header names
* The values are case-sensitive uwsgi logvar names

For every request that arrives, the contents of those headers mapped
previously will be written to your uwsgi log IFF the header is present
in the request and you've modified the logging configuration for uwsgi
accordingly [0]. Otherwise, your app will keep calm and carry on.

[0] http://uwsgi-docs.readthedocs.org/en/latest/LogFormat.html

"""

import json
import logging

from oslo_config import cfg
import uwsgi  # Injected by host server, assuming it's uWSGI!

LOG = logging.getLogger(__name__)

OPT_GROUP_NAME = 'eom:uwsgi:mapper'
OPTION_NAME = 'options_file'


def _load_options(path, conf):
    full_path = conf.find_file(path)
    if not full_path:
        raise cfg.ConfigFilesNotFoundError([path])

    with open(full_path) as fd:
        return json.load(fd)


def _prepare_logvar_map(options):
    """Normalize header names to WSGI style to improve performance."""
    raw_map = options['map']

    return [
        ('HTTP_' + header.replace('-', '_').upper(), logvar)
        for header, logvar in raw_map.items()
    ]


# NOTE(kgriffs): Using a functional style since it is more
# performant than an object-oriented one (middleware should
# introduce as little overhead as possible.)
def wrap(app):
    """Wrap a WSGI with uwsgi logvar-mapping powers.

    Takes configuration from oslo.config.cfg.CONF.

    :param app: WSGI app to wrap
    :returns: a new WSGI app that wraps the original
    """

    # NOTE(cabrera): register options
    conf = cfg.CONF
    conf.register_opt(cfg.StrOpt(OPTION_NAME),
                      group=OPT_GROUP_NAME)
    group = conf[OPT_GROUP_NAME]

    # NOTE(cabrera): load up the mapping
    options_path = group[OPTION_NAME]
    options = _load_options(options_path, conf)
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
