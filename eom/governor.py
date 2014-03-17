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

from __future__ import division
import collections
import logging
import re
import time

from oslo.config import cfg
import simplejson as json

CONF = cfg.CONF

OPT_GROUP_NAME = 'eom:governor'
OPTIONS = [
    cfg.StrOpt('rates_file'),
    cfg.IntOpt('node_count', default=1),
    cfg.IntOpt('period_sec', default=5),
    cfg.FloatOpt('sleep_threshold', default=0.1),
    cfg.FloatOpt('sleep_offset', default=0.99),
]

CONF.register_opts(OPTIONS, group=OPT_GROUP_NAME)

LOG = logging.getLogger(__name__)


class Rate(object):
    """Represents an individual rate configuration."""

    # NOTE(kgriffs): Hard-code slots to make attribute
    # access faster.
    __slots__ = (
        'name',
        'route',
        'methods',
        'soft_limit',
        'hard_limit',
        'target',
    )

    def __init__(self, document, period_sec, node_count):
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
        self.target = self.soft_limit / period_sec

        if self.hard_limit <= self.soft_limit:
            raise ValueError('hard limit must be > soft limit')

        if not period_sec > 0:
            raise ValueError('period_sec must be > 0')

    def applies_to(self, method, path):
        """Determines whether this rate applies to a given request.

        :param str method: HTTP method, such as GET or POST
        :param str path: URL path, such as "/v1/queues"
        """
        if self.methods is not None and method not in self.methods:
            return False

        if self.route is not None and not self.route.match(path):
            return False

        return True


class HardLimitError(Exception):
    pass


def _load_rates(path, period_sec, node_count):
    full_path = CONF.find_file(path)
    if not full_path:
        raise cfg.ConfigFilesNotFoundError([path or '<Empty>'])

    with open(full_path) as fd:
        document = json.load(fd)

    return [Rate(rate_doc, period_sec, node_count)
            for rate_doc in document]


def _get_counter_key(project_id, bucket):
    return project_id + ':bucket:' + bucket


# TODO(kgriffs): Consider converting to closure-style
class Cache(object):
    __slots__ = ('store',)

    def __init__(self):
        self.store = collections.defaultdict(int)

    def __repr__(self):
        return str(self.store)

    def inc_counter(self, project_id, bucket):
        key = _get_counter_key(project_id, bucket)
        self.store[key] += 1
        return self.store[key]

    def get_counter(self, project_id, bucket):
        key = _get_counter_key(project_id, bucket)
        return self.store[key]

    def set_counter(self, project_id, bucket, val):
        key = _get_counter_key(project_id, bucket)
        self.store[key] = val

    def reset_counter(self, project_id, bucket):
        key = _get_counter_key(project_id, bucket)
        self.store[key] = 0


def _create_calc_sleep(period_sec, cache, sleep_threshold, sleep_offset):
    """Creates a closure with the given params for convenience and perf."""

    ctx = {'last_bucket': None}

    def calc_sleep(project_id, rate):
        normalized = int(time.time()) % (period_sec * 2)

        current_bucket, previous_bucket = (
            ('a', 'b') if normalized < period_sec else ('b', 'a')
        )

        if ctx['last_bucket'] != current_bucket:
            cache.reset_counter(project_id, current_bucket)
            ctx['last_bucket'] = current_bucket

        cache.inc_counter(project_id, current_bucket)
        previous_count = cache.get_counter(project_id, previous_bucket)

        if previous_count > rate.hard_limit:
            cache.set_counter(project_id, previous_bucket, rate.hard_limit - 1)
            raise HardLimitError()

        if previous_count > rate.soft_limit:
            # Normalize the sleep quantity as follows:
            # normalized_sec = previous_count / rate.target
            # extra_sec = normailzed_sec - period_sec
            # return (extra_sec / previous_count) * sleep_offset
            sleep_sec = (
                (
                    (previous_count / rate.target) - period_sec
                )
                / previous_count
            ) * sleep_offset
            return sleep_sec if sleep_sec >= 0 else 0

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


def wrap(app):
    """Wrap a WSGI app with ACL middleware.

    Takes configuration from oslo.config.cfg.CONF.

    :param app: WSGI app to wrap
    :returns: a new WSGI app that wraps the original
    """
    group = CONF[OPT_GROUP_NAME]

    node_count = group['node_count']
    period_sec = group['period_sec']
    sleep_threshold = group['sleep_threshold']
    sleep_offset = group['sleep_offset']

    rates_path = group['rates_file']
    rates = _load_rates(rates_path, period_sec, node_count)

    cache = Cache()
    calc_sleep = _create_calc_sleep(period_sec, cache,
                                    sleep_threshold, sleep_offset)

    def middleware(env, start_response):
        path = env['PATH_INFO']
        method = env['REQUEST_METHOD']

        for rate in rates:
            if rate.applies_to(method, path):
                break
        else:
            LOG.debug(_('Requested path not recognized. Full steam ahead!'))
            return app(env, start_response)

        try:
            project_id = env['HTTP_X_PROJECT_ID']
        except KeyError:
            LOG.debug(_('Request headers did not include X-Project-ID'))
            return _http_400(start_response)

        try:
            sleep_sec = calc_sleep(project_id, rate)
        except HardLimitError:
            message = _('Hit hard limit of {rate} per sec. for '
                        'project {project_id} according to '
                        'rate rule "{name}"')

            hard_rate = rate.hard_limit / period_sec
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
