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
import redis


CONF = cfg.CONF

GOV_GROUP_NAME = 'eom:governor'
OPTIONS = [
    cfg.StrOpt('rates_file'),
    cfg.StrOpt('project_rates_file'),
    cfg.IntOpt('throttle_milliseconds')
]

CONF.register_opts(OPTIONS, group=GOV_GROUP_NAME)

REDIS_GROUP_NAME = 'eom:redis'
OPTIONS = [
    cfg.StrOpt('host'),
    cfg.StrOpt('port'),
]

CONF.register_opts(OPTIONS, group=REDIS_GROUP_NAME)


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
        'limit'
    )

    def __init__(self, document):
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

        self.limit = document['limit']
        self.drain_velocity = document['drain_velocity']


class HardLimitError(Exception):
    pass


def _load_json_file(path):
    full_path = CONF.find_file(path)
    if not full_path:
        raise cfg.ConfigFilesNotFoundError([path or '<Empty>'])

    with open(full_path) as fd:
        document = json.load(fd)

    return document


def _load_rates(path):
    document = _load_json_file(path)
    return [Rate(rate_doc)
            for rate_doc in document]


def _load_project_rates(path):
    try:
        document = _load_json_file(path)
        return dict(
            (doc['project'], Rate(doc))
            for doc in document
        )
    except cfg.ConfigFilesNotFoundError:
        LOG.warn('Proceeding without project-specific rate limits.')
        return {}


def _create_limiter(redis_client):
    """Creates a closure with the given params for convenience and perf."""

    def calc_sleep(project_id, rate):
        now = time.time()
        count = 1.0

        try:
            count, last_time = [
                key for key in redis_client.hmget(
                    project_id, 'c', 't')]
            if not all([count, last_time]):
                raise KeyError
            drain = (
                now - float(last_time)) * rate.drain_velocity
            # note(cabrera): disallow negative counts, increment inline
            new_count = max(0.0, float(count) - drain) + 1.0
            redis_client.hmset(project_id, {'c': new_count, 't': now})

        except KeyError:
            redis_client.hmset(project_id, {'c': 1.0, 't': now})
        except redis.exceptions.ConnectionError as ex:
            message = _('Redis Error:{exception} for Project-ID:{project_id}')
            LOG.warn((message.format(exception=ex, project_id=project_id)))

        if count > rate.limit:
            raise HardLimitError()

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


def wrap(app, redis_client):
    """Wrap a WSGI app with ACL middleware.

    Takes configuration from oslo.config.cfg.CONF.

    :param app: WSGI app to wrap
    :param redis_client: pooled redis client
    :returns: a new WSGI app that wraps the original
    """
    group = CONF[GOV_GROUP_NAME]

    rates_path = group['rates_file']
    project_rates_path = group['project_rates_file']
    throttle_milliseconds = group['throttle_milliseconds'] / 1000

    rates = _load_rates(rates_path)
    project_rates = _load_project_rates(project_rates_path)

    check_limit = _create_limiter(redis_client)

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
            check_limit(project_id, rate)
        except HardLimitError:
            message = _('Hit limit of {rate} per sec. for '
                        'project {project_id} according to '
                        'rate rule "{name}"')

            time.sleep(throttle_milliseconds)
            LOG.warn(message,
                     {'rate': rate.limit,
                      'project_id': project_id,
                      'name': rate.name})

            return _http_429(start_response)

        return app(env, start_response)

    return middleware
