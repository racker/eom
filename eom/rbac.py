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

import re

from oslo_config import cfg
import simplejson as json

from eom.utils import log as logging

_CONF = cfg.CONF
LOG = logging.getLogger(__name__)

OPT_GROUP_NAME = 'eom:rbac'
OPTION_NAME = 'acls_file'

EMPTY_SET = set()


def configure(config):
    global _CONF
    global LOG

    _CONF = config
    _CONF.register_opt(cfg.StrOpt(OPTION_NAME), group=OPT_GROUP_NAME)

    logging.register(_CONF, OPT_GROUP_NAME)
    logging.setup(_CONF, OPT_GROUP_NAME)
    LOG = logging.getLogger(__name__)


def get_conf():
    global _CONF
    return _CONF[OPT_GROUP_NAME]


def _load_rules(path):
    full_path = _CONF.find_file(path)
    if not full_path:
        raise cfg.ConfigFilesNotFoundError([path])

    with open(full_path) as fd:
        return json.load(fd)


def _create_acl_map(rules):
    acl_map = []
    for rule in rules:
        resource = rule['resource']
        route = re.compile(rule['route'] + '$')

        acl = rule['acl']

        if acl:
            can_read = set(acl.get('read', []))
            can_write = set(acl.get('write', []))
            can_delete = set(acl.get('delete', []))

            # Construct a lookup table
            lookup = {
                'GET': can_read,
                'HEAD': can_read,
                'OPTIONS': can_read,

                'PATCH': can_write,
                'POST': can_write,
                'PUT': can_write,

                'DELETE': can_delete,
            }
        else:
            lookup = None

        acl_map.append((resource, route, lookup))

    return acl_map


def _http_forbidden(start_response):
    """Responds with HTTP 403."""
    start_response('403 Forbidden', [('Content-Length', '0')])
    return []


# NOTE(kgriffs): Using a functional style since it is more
# performant than an object-oriented one (middleware should
# introduce as little overhead as possible.)
def wrap(app):
    """Wrap a WSGI app with ACL middleware.

    Takes configuration from oslo.config.cfg.CONF.

    :param app: WSGI app to wrap
    :returns: a new WSGI app that wraps the original
    """
    group = _CONF[OPT_GROUP_NAME]
    rules_path = group[OPTION_NAME]
    rules = _load_rules(rules_path)
    acl_map = _create_acl_map(rules)

    # WSGI callable
    def middleware(env, start_response):
        path = env['PATH_INFO']
        for resource, route, acl in acl_map:
            if route.match(path):
                break
        else:
            LOG.debug('Requested path not recognized. Skipping RBAC.')
            return app(env, start_response)

        try:
            roles = env['HTTP_X_ROLES']
        except KeyError:
            LOG.error('Request headers did not include X-Roles')
            return _http_forbidden(start_response)

        given_roles = set(roles.split(',')) if roles else EMPTY_SET

        method = env['REQUEST_METHOD']
        try:
            authorized_roles = acl[method]
        except KeyError:
            LOG.error('HTTP method not supported: {0}'.format(method))
            return _http_forbidden(start_response)

        # The user must have one of the roles that
        # is authorized for the requested method.
        if (authorized_roles & given_roles):
            # Carry on
            return app(env, start_response)

        log_line = 'User not authorized to {0} the {1} resource'
        LOG.info(log_line.format(method, resource))
        return _http_forbidden(start_response)

    return middleware
