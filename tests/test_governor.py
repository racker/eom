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
import contextlib
import io
import logging
import multiprocessing
import sys
import time
import uuid
from wsgiref import simple_server

import ddt
import fakeredis
import mock
import requests
import six
import testtools

from eom import governor
from tests import util


def run_server(app, host, port):
    httpd = simple_server.make_server(host, port, app)
    httpd.serve_forever()


def _suppress_logging():
    requests_log = logging.getLogger("requests")
    rlevel = requests_log.level
    requests_log.setLevel(logging.WARNING)

    # Suppress logging
    stdtmp, sys.stderr = sys.stderr, io.BytesIO() if six.PY2 else io.StringIO()

    return stdtmp, rlevel,


def _recover_logging(stdtmp, rlevel):
    requests_log = logging.getLogger("requests")
    requests_log.setLevel(rlevel)
    sys.stderr = stdtmp


@contextlib.contextmanager
def make_silent_server(app, host, port):
    stdtmp, rlevel = _suppress_logging()
    process = multiprocessing.Process(
        target=run_server, args=(app, host, port)
    )
    process.daemon = True
    process.start()

    # Give the process a moment to start up
    time.sleep(0.1)

    yield process

    process.terminate()
    _recover_logging(stdtmp, rlevel)


def make_rate(limit, methods=None,
              route=None, drain_velocity=1.0):
    req = [
        ('name', str(uuid.uuid4())),
        ('limit', limit),
        ('drain_velocity', drain_velocity)
    ]
    return governor.Rate(dict(
        req + (
            [('methods', methods)] if methods is not None else []
        ) + (
            [('route', route)] if route is not None else []
        )
    ))


def fakeredis_connection():
    return fakeredis.FakeRedis()


class DTuple(tuple):
    pass


def method_annotate(rate, method, expect):
    r = DTuple((rate, method, expect))
    template = '{0} | {1} -> {2}'
    setattr(r, '__name__', template.format(
        list(rate.methods) if rate.methods is not None else "[]",
        method, expect)
    )
    return r


def route_annotate(rate, route, expect):
    r = DTuple((rate, route, expect))
    template = '{0} | {1} -> {2}'
    setattr(r, '__name__', template.format(
        rate.route.pattern.replace('.', '%'),
        route, expect)
    )
    return r


@ddt.ddt
class TestGovernor(util.TestCase):

    def setUp(self):
        super(TestGovernor, self).setUp()
        self.redis_client = fakeredis_connection()
        governor.configure(util.CONF)
        self.governor = governor.wrap(util.app, self.redis_client)

        config = governor.get_conf()
        rates = governor._load_rates(config['rates_file'])

        self.test_rate = rates[0]
        self.limit = self.test_rate.limit
        self.test_url = '/v1/queues/fizbit/messages'
        self.limiter = governor._create_limiter(self.redis_client)

        self.default_rate = rates[1]

    def tearDown(self):
        super(TestGovernor, self).tearDown()
        redis_client = fakeredis_connection()
        redis_client.flushall()

    def test_get_conf(self):
        config = governor.get_conf()
        self.assertIsNotNone(config)

    def test_missing_project_id(self):
        env = self.create_env('/v1')
        self.governor(env, self.start_response)
        self.assertEqual(self.status, '400 Bad Request')

    def test_simple(self):
        env = self.create_env('/v1', project_id='84197')
        self.governor(env, self.start_response)
        self.assertEqual(self.status, '204 No Content')

    @ddt.data(
        # (rate, method, expect)
        method_annotate(make_rate(200), "GET", True),
        method_annotate(make_rate(200, ["GET"]), "GET", True),
        method_annotate(make_rate(200, ["GET"]), "POST", False),
        method_annotate(make_rate(200, ["GET", "POST"]), "POST", True),
        method_annotate(make_rate(200, ["GET", "POST"]), "PUT", False)
    )
    def test_applies_to_method(self, data):
        rate, method, expect = data
        self.assertEqual(governor.applies_to(rate, method, ""), expect)

    @ddt.data(
        # (rate, route, expect)
        route_annotate(make_rate(200, route="/"), "/", True),
        route_annotate(make_rate(200, route="/"), "/v1", False),
        route_annotate(make_rate(200, route="/v1.*"), "/v1", True),
        route_annotate(make_rate(200, route="/v1.*"), "/v1/queues", True),
        route_annotate(make_rate(200, route="/v1.*"), "/v2/queues", False)
    )
    def test_applies_to_route(self, data):
        rate, route, expect = data
        self.assertEqual(governor.applies_to(rate, [], route), expect)

    def test_match_rate_gives_preference_to_project_specific(self):
        expect = make_rate(1)
        prates = {'11': expect}
        grates = [make_rate(2), make_rate(4)]
        self.assertEqual(
            governor.match_rate('11', None, None, prates, grates),
            expect
        )

    def test_match_rate_returns_general_rate_otherwise(self):
        expect = make_rate(2)
        prates = {'11': make_rate(2)}
        grates = [expect, make_rate(4)]
        self.assertEqual(
            governor.match_rate('12', None, None, prates, grates),
            expect
        )

    def test_match_rate_returns_none_when_none_applicable(self):
        prates = {'11': make_rate(2)}
        grates = [make_rate(2, ['GET']), make_rate(1, ['DELETE'])]
        self.assertIsNone(
            governor.match_rate('12', 'PUT', None, prates, grates)
        )

    @mock.patch('time.time')
    def test_limiter_raises_if_over_limit(self, mock_time):
        mock_time.return_value = 0.0
        call = lambda: self.limiter(1, self.test_rate)
        [call() for _ in range(self.limit)]

        self.assertEqual(
            float(self.redis_client.hmget(1, 'c')[0]),
            float(self.limit)
        )
        with testtools.ExpectedException(governor.HardLimitError):
            call()

    @mock.patch('time.time')
    def test_limit_reached_no_429(self, mock_time):
        mock_time.return_value = 0.0
        self._test_limit(self.default_rate.limit, 204)

    @mock.patch('time.time')
    def test_limit_surpassed_leads_to_429(self, mock_time):
        mock_time.return_value = 0.0
        self._test_limit(self.default_rate.limit + 1, 429)

    def test_draining_evades_429(self):
        self._test_draining(self.default_rate.limit + 3, 204)

    # ----------------------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------------------

    def _test_limit(self, limit, expected_status,
                    method='GET'):
        request = getattr(requests, method.lower())
        host, port = '127.0.0.1', 8783
        with make_silent_server(self.governor, host, port):
            url = 'http://%s:%s' % (host, port) + self.test_url
            call = lambda: request(url, headers={'X-Project-ID': 1234})
            resps = [call().status_code for _ in range(limit)]
            self.assertEqual(resps[-1], expected_status)

    def _test_draining(self, limit, expected_status,
                       method='GET'):
        request = getattr(requests, method.lower())
        host, port = '127.0.0.1', 8783
        with make_silent_server(self.governor, host, port):
            url = 'http://%s:%s' % (host, port) + self.test_url
            call = lambda: request(url, headers={'X-Project-ID': 1234})
            [call().status_code for _ in range(limit // 2)]
            time.sleep(2.0)
            resp = [call().status_code for _ in range(limit // 2)][-1]
            self.assertEqual(resp, expected_status)
