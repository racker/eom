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
#
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import division
import itertools
import logging
import re
import time

from oslo.config import cfg
import simplejson as json

CONF = cfg.CONF

OPT_GROUP_NAME = 'eom:governor'
OPTIONS = [
    cfg.StrOpt('rates_file'),
    cfg.StrOpt('project_rates_file'),
    cfg.FloatOpt('sleep_offset', default=0.01)
]

CONF.register_opts(OPTIONS, group=OPT_GROUP_NAME)

LOG = logging.getLogger(__name__)


def applies_to(rate, method, route):
    """Determines whether this rate applies to a given request.

    :param str method: HTTP method, such as GET or POST
    :param str path: URL path, such as "/v1/queues"
    """
    if rate.methods is not None and method not in rate.methods:
        return False

    if rate.route is not None and not rate.route.match(route):
        return False

    return True


class Rate(object):
    """Represents an individual rate configuration."""

    # NOTE(kgriffs): Hard-code slots to make attribute
    # access faster.
    __slots__ = (
        'name',
        'route',
        'methods',
        'drain_velocity',
        'soft_limit',
        'hard_limit'
    )

    def __init__(self, document, node_count):
        """Initializes attributes.

        :param dict document:
        """
        self.name = document['name']
        self.route = (
            re.compile(document['route'] + '$')
            if 'route' in document else None
        )
        self.methods = (
            set(document['methods']) if 'methods' in document
            else None
        )

        self.hard_limit = document['hard_limit'] / node_count
        self.soft_limit = document['soft_limit'] / node_count
        self.drain_velocity = document['drain_velocity']

        if self.hard_limit <= self.soft_limit:
            raise ValueError('Hard limit must be > soft limit')


class HardLimitError(Exception):
    pass


def _load_json_file(path):
    full_path = CONF.find_file(path)
    if not full_path:
        raise cfg.ConfigFilesNotFoundError([path or '<Empty>'])

    with open(full_path) as fd:
        document = json.load(fd)

    return document


def _load_rates(path, node_count):
    document = _load_json_file(path)
    return [Rate(rate_doc, node_count)
            for rate_doc in document]


def _load_project_rates(path, node_count):
    document = _load_json_file(path)
    return dict(
        (doc['project'], Rate(doc, node_count))
        for doc in document
    )


def sleep_for(count, limit, sleep_offset):
    return (count / limit) * sleep_offset


def _create_calc_sleep(cache, sleep_offset):
    """Creates a closure with the given params for convenience and perf."""

    def calc_sleep(project_id, rate):
        now = time.time()
        try:
            last = cache[project_id]['t']
            drain = (now - last) * rate.drain_velocity
            # note(cabrera): never allow negative request counts
            new_count = max(1, cache[project_id]['c'] - drain + 1)
            cache[project_id] = {
                'c': new_count,
                't': now
            }

        except KeyError:
            cache[project_id] = {
                'c': 1,
                't': now
            }

        count = cache[project_id]['c']
        if count > rate.hard_limit:
            raise HardLimitError()

        if count > rate.soft_limit:
            return sleep_for(count, rate.soft_limit, sleep_offset)

        return 0

    return calc_sleep


def _http_429(start_response):
    """Responds with HTTP 429."""
    start_response('429 Too Many Requests', [('Content-Length', '0')])
    return []


def _http_400(start_response):
    """Responds with HTTP 400."""
    start_response('400 Bad Request', [('Content-Length', '0')])
    return []


def match_rate(project, method, route, project_rates, general_rates):
    """Gives priority to project-specific Rate limits."""
    try:
        rate = project_rates[project]
        if applies_to(rate, method, route):
            return rate
    except KeyError:
        pass

    try:
        matcher = lambda r: applies_to(r, method, route)
        return next(itertools.ifilter(matcher,
                                      general_rates))
    except StopIteration:
        return None


def wrap(app):
    """Wrap a WSGI app with ACL middleware.

    Takes configuration from oslo.config.cfg.CONF.

    :param app: WSGI app to wrap
    :returns: a new WSGI app that wraps the original
    """
    group = CONF[OPT_GROUP_NAME]

    node_count = group['node_count']
    sleep_offset = group['sleep_offset']

    rates_path = group['rates_file']
    project_rates_path = group['project_rates_file']
    rates = _load_rates(rates_path, node_count)
    try:
        project_rates = _load_project_rates(
            project_rates_path, node_count
        )
    except cfg.ConfigFilesNotFoundError:
        project_rates = {}

    cache = {}
    calc_sleep = _create_calc_sleep(cache, sleep_offset)

    def middleware(env, start_response):
        path = env['PATH_INFO']
        method = env['REQUEST_METHOD']

        try:
            project_id = env['HTTP_X_PROJECT_ID']
        except KeyError:
            LOG.debug(_('Request headers did not include X-Project-ID'))
            return _http_400(start_response)

        rate = match_rate(project_id, path, method,
                          project_rates, rates)
        if rate is None:
            LOG.debug(_('Requested path not recognized. Full steam ahead!'))
            return app(env, start_response)

        try:
            sleep_sec = calc_sleep(project_id, rate)
        except HardLimitError:
            message = _('Hit hard limit of {rate} per sec. for '
                        'project {project_id} according to '
                        'rate rule "{name}"')

            hard_rate = rate.hard_limit
            time.sleep(1)
            LOG.warn(message,
                     {'rate': hard_rate,
                      'project_id': project_id,
                      'name': rate.name})

            return _http_429(start_response)

        if sleep_sec > 0:
            message = _('Sleeping {sleep_sec} sec. for '
                        'project {project_id} to limit '
                        'rate to {limit} according to '
                        'rate rule "{name}"')

            LOG.debug(message,
                      {'sleep_sec': sleep_sec,
                       'project_id': project_id,
                       'limit': rate.soft_limit,
                       'name': rate.name})

            # Keep calm...
            time.sleep(sleep_sec)

        # ...and carry on.
        return app(env, start_response)

    return middleware
