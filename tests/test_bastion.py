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

import ddt

from eom import bastion
from tests import util


@ddt.ddt
class TestBastion(util.TestCase):

    def setUp(self):
        super(TestBastion, self).setUp()

        app = util.app
        wrapped_app = util.wrap_403(app)
        self.bastion = bastion.wrap(app, wrapped_app)
        self.restricted_route = '/v1/health'
        self.normal_route = '/v1'

    def _expect(self, env, code):
        # NOTE(cabrera): 204 means we used the backdoor that bastion
        # allows, 403 means we hit the gate, and 404 means an attempt
        # was made to access a restricted route by a load-balancer
        # forwarded client.
        lookup = {204: '204 No Content',
                  403: '403 Forbidden',
                  404: '404 Not Found'}
        self.bastion(env, self.start_response)
        self.assertEqual(self.status, lookup[code])

    def test_unrestricted_route_hits_gate(self):
        env = self.create_env(self.normal_route)
        self._expect(env, 403)

    def test_route_restricted_and_xforward_present_returns_204(self):
        env = self.create_env(self.restricted_route)
        env['HTTP_X_FORWARDED_FOR'] = 'taco'
        self._expect(env, 204)

    def test_route_restricted_and_not_forwarded_returns_204(self):
        env = self.create_env(self.restricted_route)
        self._expect(env, 204)

    @ddt.data('/v1/healthy', '/v1/heath', '/health', 'health')
    def test_restrict_close_match_route_hits_gate(self, route):
        env = self.create_env(route)
        env['HTTP_X_FORWARDED_FOR'] = 'taco'
        self._expect(env, 403)

    @ddt.data('GET', 'HEAD', 'PUT', 'DELETE', 'POST', 'PATCH')
    def test_restrict_works_regardless_of_method(self, method):
        env = self.create_env(self.restricted_route)
        self._expect(env, 204)

        env['HTTP_X_FORWARDED_FOR'] = 'taco'
        self._expect(env, 204)
