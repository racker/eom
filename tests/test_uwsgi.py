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

from tests import util


class TestUwsgiImport(util.TestCase):

    def test_import_uwsgi_raises_import_error(self):
        try:
            from eom import uwsgi  # noqa
            self.fail("Did not raise ImportError")
        except ImportError:
            pass

    def test_import_uwsgi_specific_module_raises_import_error(self):
        try:
            from eom.uwsgi import logvar_mapper  # noqa
            self.fail("Did not raise ImportError")
        except ImportError:
            pass
