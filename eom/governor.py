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

from __future__ import division
import re
import time

from oslo_config import cfg
import redis
from redis import connection
import simplejson as json
import six

from eom.utils import log as logging


_CONF = cfg.CONF

GOV_GROUP_NAME = 'eom:governor'
GOV_OPTIONS = [
    cfg.StrOpt(
        'rates_file',
        help='JSON file containing route, methods, limits and drain_velocity.'
    ),
    cfg.StrOpt(
        'project_rates_file',
        help='JSON file with details on project id specific rate limiting.'
    ),
    cfg.IntOpt(
        'throttle_milliseconds',
        help='Number of milliseconds to sleep when bucket is full.'
    )
]

REDIS_GROUP_NAME = 'eom:redis'
REDIS_OPTIONS = [
    cfg.StrOpt('host'),
    cfg.StrOpt('port'),
    cfg.IntOpt('redis_db', default=0),
    cfg.StrOpt('password', default=None),
    cfg.BoolOpt('ssl_enable', default=False),
    cfg.StrOpt('ssl_keyfile', default=None),
    cfg.StrOpt('ssl_certfile', default=None),
    cfg.StrOpt('ssl_cert_reqs', default=None),
    cfg.StrOpt('ssl_ca_certs', default=None),
]


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


class Governor(object):

    def __init__(self, app, conf):
        """Wraps a WSGI app with ACL middleware.

        Takes configuration from oslo.config.cfg.CONF.

        :param app: WSGI app to wrap
        :param conf: configuration options for governor middleware
        """

        self.app = app
        self.conf = conf

        conf.register_opts(GOV_OPTIONS, group=GOV_GROUP_NAME)
        conf.register_opts(REDIS_OPTIONS, group=REDIS_GROUP_NAME)

        logging.register(conf, GOV_GROUP_NAME)
        logging.setup(conf, GOV_GROUP_NAME)

        self.logger = logging.getLogger(__name__)

        self._redis_conf = conf[REDIS_GROUP_NAME]
        self._gov_conf = conf[GOV_GROUP_NAME]

        rates_path = self._gov_conf['rates_file']
        project_rates_path = self._gov_conf['project_rates_file']

        self.rates = self._load_rates(rates_path)
        self.project_rates = self._load_project_rates(project_rates_path)
        self.throttle_milliseconds = (
            self._gov_conf['throttle_milliseconds'] / 1000
        )
        self.check_limit = self._create_limiter()

    @property
    def redis_client(self):
        """Get a Redis Client connection from the pool

        uses the eom:auth_redis settings
        """

        if self._redis_conf['ssl_enable']:
            pool = redis.ConnectionPool(
                host=self._redis_conf['host'],
                port=self._redis_conf['port'],
                db=self._redis_conf['redis_db'],
                password=self._redis_conf['password'],
                ssl_keyfile=self._redis_conf['ssl_keyfile'],
                ssl_certfile=self._redis_conf['ssl_certfile'],
                ssl_cert_reqs=self._redis_conf['ssl_cert_reqs'],
                ssl_ca_certs=self._redis_conf['ssl_ca_certs'],
                connection_class=connection.SSLConnection
            )
        else:
            pool = redis.ConnectionPool(
                host=self._redis_conf['host'],
                port=self._redis_conf['port'],
                password=self._redis_conf['password'],
                db=self._redis_conf['redis_db']
            )

        return redis.Redis(connection_pool=pool)

    def _load_json_file(self, path):
        full_path = self.conf.find_file(path)
        if not full_path:
            raise cfg.ConfigFilesNotFoundError([path or '<Empty>'])

        with open(full_path) as fd:
            document = json.load(fd)

        return document

    def _load_rates(self, path):
        document = self._load_json_file(path)
        return [Rate(rate_doc)
                for rate_doc in document]

    def _load_project_rates(self, path):
        try:
            document = self._load_json_file(path)
            return dict(
                (doc['project'], Rate(doc))
                for doc in document
            )
        except cfg.ConfigFilesNotFoundError:
            self.logger.warn(
                'Proceeding without project-specific rate limits.')
            return {}

    @staticmethod
    def applies_to(rate, method, route):
        """Determines whether this rate applies to a given request.

        :param Rate.rate rate: Rate object defines rates for governor
        :param str method: HTTP method, such as GET or POST
        :param str route: URL path, such as "/v1/queues"
        """
        if rate.methods is not None and method not in rate.methods:
            return False

        if rate.route is not None and not rate.route.match(route):
            return False

        return True

    def _create_limiter(self):
        """Creates a closure with the given params for convenience and perf."""

        def calc_sleep(project_id, rate):
            now = time.time()
            last_time = now
            count = 1.0
            new_count = 1.0

            try:
                lookup = self.redis_client.hmget(project_id, 'c', 't')

                if lookup is not None:
                    count, last_time = lookup

                    if count is None:
                        count = float(1.0)

                    if last_time is None:
                        last_time = now

                if not all([count, last_time]):
                    raise KeyError

                count, last_time = float(count), float(last_time)

                drain = (now - last_time) * rate.drain_velocity
                # note(cabrera): disallow negative counts, increment inline
                new_count = max(0.0, count - drain) + 1.0
                self.redis_client.hmset(project_id, {'c': new_count, 't': now})

            except KeyError:
                self.redis_client.hmset(project_id, {'c': 1.0, 't': now})

            except redis.exceptions.ConnectionError as ex:
                message = 'Redis Error:{0} for Project-ID:{1}'
                self.logger.warn(message.format(ex, project_id))

            if new_count > rate.limit:
                raise HardLimitError()

        return calc_sleep

    @staticmethod
    def _http_429(start_response):
        """Responds with HTTP 429."""
        start_response('429 Too Many Requests', [('Content-Length', '0')])
        return []

    @staticmethod
    def _http_400(start_response):
        """Responds with HTTP 400."""
        start_response('400 Bad Request', [('Content-Length', '0')])
        return []

    def match_rate(self, project, method, route):
        """Gives priority to project-specific Rate limits."""
        try:
            rate = self.project_rates[project]
            if self.applies_to(rate, method, route):
                return rate
        except KeyError:
            pass

        try:
            matcher = lambda r: self.applies_to(r, method, route)
            return next(six.moves.filter(matcher, self.rates))
        except StopIteration:
            return None

    def __call__(self, env, start_response):
        path = env['PATH_INFO']
        method = env['REQUEST_METHOD']

        try:
            project_id = env['HTTP_X_PROJECT_ID']
        except KeyError:
            self.logger.debug('Request headers did not include X-Project-ID')
            return self._http_400(start_response)

        rate = self.match_rate(project_id, path, method)
        if rate is None:
            self.logger.debug(
                'Requested path not recognized. Full steam ahead!')
            return self.app(env, start_response)

        try:
            self.check_limit(project_id, rate)
        except HardLimitError:
            message = (
                'Hit limit of {rate} per sec. for '
                'project {project_id} according to '
                'rate rule "{name}"'
            )

            time.sleep(self.throttle_milliseconds)

            self.logger.warn(message.format(rate=rate.limit,
                                            project_id=project_id,
                                            name=rate.name))
            return self._http_429(start_response)

        return self.app(env, start_response)
