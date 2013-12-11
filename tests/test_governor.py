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

from eom import governor
from tests import util


class TestGovernor(util.TestCase):

    def setUp(self):
        super(TestGovernor, self).setUp()

        self.governor = governor.wrap(util.app)

    def test_simple(self):
        env = self.create_env('/v1', project_id='84197')
        self.governor(env, self.start_response)
        self.assertEquals(self.status, '204 No Content')

    def test_missing_project_id(self):
        env = self.create_env('/v1')
        self.governor(env, self.start_response)
        self.assertEquals(self.status, '400 Bad Request')
