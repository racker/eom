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
import socket
import time

from oslo_config import cfg
import statsd

from eom.utils import log as logging

_CONF = cfg.CONF
LOG = logging.getLogger(__name__)

OPT_GROUP_NAME = 'eom:metrics'
OPTIONS = [
    cfg.StrOpt('address',
               help='host for statsd server.',
               required=True,
               default='localhost'),
    cfg.IntOpt('port',
               help='port for statsd server.',
               required=False,
               default=8125),
    cfg.ListOpt('path_regexes_keys',
                help='keys for regexes for the paths of the WSGI app',
                required=False,
                default=[]),

    cfg.ListOpt('path_regexes_values',
                help='regexes for the paths of the WSGI app',
                required=False,
                default=[]),

    cfg.StrOpt("prefix",
               help="Prefix for graphite metrics",
               required=False,
               default=""),

    cfg.StrOpt('app_name',
               help="Application name",
               required=True)
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


def wrap(app):
    addr = _CONF[OPT_GROUP_NAME].address
    port = _CONF[OPT_GROUP_NAME].port
    keys = _CONF[OPT_GROUP_NAME].path_regexes_keys
    values = _CONF[OPT_GROUP_NAME].path_regexes_values
    prefix = _CONF[OPT_GROUP_NAME].prefix
    app_name = _CONF[OPT_GROUP_NAME].app_name

    regex_strings = zip(keys, values)
    regex = []
    for (method, pattern) in regex_strings:
        regex.append((method, re.compile(pattern)))

    client = statsd.StatsClient(host=addr,
                                port=port,
                                prefix=prefix)

    # initialize buckets
    for request_method in ["GET", "PUT", "HEAD", "POST", "DELETE", "PATCH"]:
        for name, regexstr in regex_strings:
            for code in ["2xx", "4xx", "5xx"]:
                client.incr(app_name + "." + socket.gethostname() +
                            ".requests." + request_method + "." +
                            name + "." + code)
                client.decr(app_name + "." + socket.gethostname() +
                            ".requests." + request_method + "." +
                            name + "." + code)

    def middleware(env, start_response):

        request_method = env["REQUEST_METHOD"]
        path = env["PATH_INFO"]
        hostname = socket.gethostname()
        api_method = "unknown"

        for (method, regex_pattern) in regex:
            if regex_pattern.match(path):
                api_method = method

        def _start_response(status, headers, *args):
            status_path = (app_name + "." + hostname + ".requests." +
                           request_method + "." + api_method)
            status_code = int(status[:3])
            if status_code / 500 == 1:
                client.incr(status_path + ".5xx")
            elif status_code / 400 == 1:
                client.incr(status_path + ".4xx")
            elif status_code / 200 == 1:
                client.incr(status_path + ".2xx")

            return start_response(status, headers, *args)

        start = time.time() * 1000
        response = app(env, _start_response)
        stop = time.time() * 1000

        elapsed = stop - start
        client.timing(app_name + "." + hostname + ".latency." +
                      request_method, elapsed)
        return response

    return middleware
