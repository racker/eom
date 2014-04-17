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
import io
import logging
import multiprocessing
import sys
import time
import uuid
from wsgiref import simple_server

import ddt
from eom import governor
import requests

import tests


def make_rate(slimit, hlimit, methods=None,
              route=None, period_sec=1, node_count=1):
    req = [
        ('name', str(uuid.uuid4())),
        ('soft_limit', slimit),
        ('hard_limit', hlimit)
    ]
    return governor.Rate(dict(
        req + (
            [('methods', methods)] if methods is not None else []
        ) + (
            [('route', route)] if route is not None else []
        )
    ), period_sec, node_count)


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
class TestGovernor(tests.util.TestCase):

    def setUp(self):
        super(TestGovernor, self).setUp()

        self.governor = governor.wrap(tests.util.app)

        config = governor.CONF['eom:governor']
        self.node_count = config['node_count']
        self.period_sec = config['period_sec']
        rates = governor._load_rates(config['rates_file'],
                                     self.period_sec, self.node_count)

        self.test_rate = rates[0]
        self.soft_limit = self.test_rate.soft_limit
        self.hard_limit = self.test_rate.hard_limit
        self.test_url = '/v1/queues/fizbit/messages'

        self.default_rate = rates[1]

    def _quantum_leap(self):
        # Wait until the next time quantum
        normalized = time.time() % (self.period_sec * 2)
        if normalized < self.period_sec:
            time.sleep(self.period_sec - normalized)
        else:
            time.sleep(self.period_sec * 2 - normalized)

    def test_missing_project_id(self):
        env = self.create_env('/v1')
        self.governor(env, self.start_response)
        self.assertEqual(self.status, '400 Bad Request')

    def test_simple(self):
        env = self.create_env('/v1', project_id='84197')
        self.governor(env, self.start_response)
        self.assertEqual(self.status, '204 No Content')

    def test_soft_limit(self):
        self._test_limit(self.soft_limit, 204)

    def test_soft_limit_burst(self):
        self._test_limit(self.soft_limit, 204, burst=True)

    def test_soft_limit_default(self):
        self._test_limit(self.default_rate.soft_limit, 204, 'PATCH')

    def test_hard_limit(self):
        self._test_limit(self.hard_limit, 429)

    def test_hard_limit_burst(self):
        self._test_limit(self.hard_limit, 429, burst=True)

    @ddt.data(
        # (rate, method, expect)
        method_annotate(make_rate(100, 200), "GET", True),
        method_annotate(make_rate(100, 200, ["GET"]), "GET", True),
        method_annotate(make_rate(100, 200, ["GET"]), "POST", False),
        method_annotate(make_rate(100, 200, ["GET", "POST"]), "POST", True),
        method_annotate(make_rate(100, 200, ["GET", "POST"]), "PUT", False)
    )
    def test_applies_to_method(self, data):
        rate, method, expect = data
        self.assertEqual(governor.applies_to(rate, method, ""), expect)

    @ddt.data(
        # (rate, route, expect)
        route_annotate(make_rate(100, 200, route="/"), "/", True),
        route_annotate(make_rate(100, 200, route="/"), "/v1", False),
        route_annotate(make_rate(100, 200, route="/v1.*"), "/v1", True),
        route_annotate(make_rate(100, 200, route="/v1.*"), "/v1/queues", True),
        route_annotate(make_rate(100, 200, route="/v1.*"), "/v2/queues", False)
    )
    def test_applies_to_route(self, data):
        rate, route, expect = data
        self.assertEqual(governor.applies_to(rate, [], route), expect)

    def test_match_rate_gives_preference_to_project_specific(self):
        expect = make_rate(1, 2)
        prates = {'11': expect}
        grates = [make_rate(1, 2), make_rate(3, 4)]
        self.assertEqual(
            governor.match_rate('11', None, None, prates, grates),
            expect
        )

    def test_match_rate_returns_general_rate_otherwise(self):
        expect = make_rate(1, 2)
        prates = {'11': make_rate(1, 2)}
        grates = [expect, make_rate(3, 4)]
        self.assertEqual(
            governor.match_rate('12', None, None, prates, grates),
            expect
        )

    def test_match_rate_returns_none_when_none_applicable(self):
        prates = {'11': make_rate(1, 2)}
        grates = [make_rate(1, 2, ['GET']), make_rate(1, 2, ['DELETE'])]
        self.assertIsNone(
            governor.match_rate('12', 'PUT', None, prates, grates)
        )

    #----------------------------------------------------------------------
    # Helpers
    #----------------------------------------------------------------------

    def _test_limit(self, limit, expected_status,
                    http_method='GET', burst=False):

        request = getattr(requests, http_method.lower())

        def run_server():
            sys.stderr = io.BytesIO()  # Suppress logging

            httpd = simple_server.make_server('127.0.0.1', 8783,
                                              self.governor)
            httpd.serve_forever()

        process = multiprocessing.Process(target=run_server)
        process.daemon = True
        process.start()

        # Suppress logging
        requests_log = logging.getLogger("requests")
        requests_log.setLevel(logging.WARNING)

        # Give the process a moment to start up
        time.sleep(0.1)

        num_periods = 5
        sec_per_req = self.period_sec / limit
        url = 'http://127.0.0.1:8783' + self.test_url

        # Start out at the beginning of a time bucket
        self._quantum_leap()

        if burst:
            for i in range(int(limit) + 100):
                request(url, headers={'X-Project-ID': 1234})

            self._quantum_leap()

        start = time.time()
        stop_1 = start + self.period_sec
        stop_N = start + self.period_sec * num_periods

        responses = []
        while time.time() < stop_1:
            resp = request(url, headers={'X-Project-ID': 1234})
            responses.append(resp.status_code)
            time.sleep(sec_per_req * .7)

        num_requests = 0
        while time.time() < stop_N:
            resp = request(url, headers={'X-Project-ID': 1234})
            responses.append(resp.status_code)
            num_requests += 1
            time.sleep(sec_per_req * .7)

        if expected_status == 204:
            # We would have slept so we can predict
            # the rate.
            expected = limit * (num_periods - 1)

            self.assertAlmostEqual(num_requests, expected,
                                   delta=(150 / self.node_count))
            self.assertNotIn(429, responses[1:])
        else:
            self.assertIn(429, responses)

        process.terminate()
