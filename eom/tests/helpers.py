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

import functools
import os


SKIP_SLOW_TESTS = os.getenv('EOM_TEST_SLOW') is None


def is_slow(condition=lambda x: True):
    """Decorator to flag slow tests.

    Slow tests will be skipped unless EOM_TEST_SLOW is set, and
    condition(self) returns True.

    :param condition: Function that returns True IFF the test will be
    slow; useful for child classes which may modify the behavior of a
    test such that it may or may not be slow.
    :type condition: f(a) -> bool
    """

    def decorator(test_method):
        @functools.wraps(test_method)
        def wrapper(self):
            if SKIP_SLOW_TESTS and condition(self):
                msg = ('Skipping slow test. Set EOM_TEST_SLOW '
                       'to enable slow tests.')

                self.skipTest(msg)

            test_method(self)

        return wrapper

    return decorator
