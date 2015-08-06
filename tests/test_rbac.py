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

import eom.rbac
from tests import util


eom.rbac.configure(util.CONF)


class TestRBAC(util.TestCase):

    def setUp(self):
        super(TestRBAC, self).setUp()

        self.rbac = eom.rbac.wrap(util.app)

    def test_get_conf(self):
        config = eom.rbac.get_conf()
        self.assertIsNotNone(config)

    def test_noacl(self):
        env = self.create_env('/v1')
        self.rbac(env, self.start_response)
        self.assertEqual(self.status, '204 No Content')

    def test_noroles(self):
        env = self.create_env('/v1/queues')
        self.rbac(env, self.start_response)
        self.assertEqual(self.status, '403 Forbidden')

    def test_unrecognized_role(self):
        env = self.create_env('/v1/queues', 'super:fly')
        self.rbac(env, self.start_response)
        self.assertEqual(self.status, '403 Forbidden')

    def test_can_read(self):
        for http_method in ('GET', 'HEAD', 'OPTIONS'):
            env = self.create_env('/v1/queues', 'queuing:observer',
                                  method=http_method)
            self.rbac(env, self.start_response)
            self.assertEqual(self.status, '204 No Content')

    def test_no_read(self):
        for http_method in ('GET', 'HEAD', 'OPTIONS'):
            env = self.create_env('/v1/queues', 'queuing:producer',
                                  method=http_method)
            self.rbac(env, self.start_response)
            self.assertEqual(self.status, '403 Forbidden')

    def test_can_write(self):
        for http_method in ('PATCH', 'POST', 'PUT'):
            env = self.create_env('/v1/queues', 'queuing:admin',
                                  method=http_method)
            self.rbac(env, self.start_response)
            self.assertEqual(self.status, '204 No Content')

    def test_no_write(self):
        for http_method in ('PATCH', 'POST', 'PUT'):
            env = self.create_env('/v1/queues', 'observer',
                                  method=http_method)
            self.rbac(env, self.start_response)
            self.assertEqual(self.status, '403 Forbidden')

    def test_can_delete(self):
        env = self.create_env('/v1/queues', 'queuing:gc',
                              method='DELETE')
        self.rbac(env, self.start_response)
        self.assertEqual(self.status, '204 No Content')

    def test_no_delete(self):
        env = self.create_env('/v1/queues', 'queuing:producer',
                              method='DELETE')
        self.rbac(env, self.start_response)
        self.assertEqual(self.status, '403 Forbidden')
