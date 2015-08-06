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

import os

from oslo_config import cfg
import testtools


CONF = cfg.CONF


class TestCase(testtools.TestCase):

    def setUp(self):
        super(TestCase, self).setUp()

        self.config_file = self.conf_path('eom.conf-sample')
        CONF(args=[], default_config_files=[self.config_file])

    def assertGreater(self, left, right):
        if left > right:
            return

        msg = '%s not greater than %s' % (left, right)
        raise self.failureException(msg)

    # Copied from unittest2 for python 2.6 compat
    # https://github.com/wildfuse/unittest2/blob/master/unittest2/case.py
    def assertAlmostEqual(self, first, second, places=None,
                          msg=None, delta=None):
        """Determine if two objects are nearly equal

           Fail if the two objects are unequal as determined by their
           difference rounded to the given number of decimal places
           (default 7) and comparing to zero, or by comparing that the
           between the two objects is more than the given delta.

           Note that decimal places (from zero) are usually not the same
           as significant digits (measured from the most signficant digit).

           If the two objects compare equal then they will automatically
           compare almost equal.
        """
        if first == second:
            # shortcut
            return
        if delta is not None and places is not None:
            raise TypeError("specify delta or places not both")

        if delta is not None:
            if abs(first - second) <= delta:
                return

            standardMsg = '%s != %s within %s delta' % (first, second, delta)
        else:
            if places is None:
                places = 7

            if round(abs(second-first), places) == 0:
                return

            standardMsg = '%s != %s within %r places' % (first, second, places)

        if msg is None:
            msg = standardMsg
        else:
            msg = standardMsg + ' : ' + msg

        raise self.failureException(msg)

    def conf_path(self, filename):
        """Returns the full path to the specified conf file.

        :param filename: Name of the conf file to find (e.g.,
                         'eom.conf')
        """

        module_dir = os.path.abspath(os.path.dirname(__file__))
        parent = os.path.dirname(module_dir)
        return os.path.join(parent, '../etc', filename)

    def create_env(self, path, roles=None, project_id=None, auth_token=None,
                   method='GET'):
        env = {
            'PATH_INFO': path,
            'REQUEST_METHOD': method
        }

        if auth_token is not None:
            env['HTTP_X_AUTH_TOKEN'] = auth_token

        if project_id is not None:
            env['HTTP_X_PROJECT_ID'] = project_id

        if roles is not None:
            if not isinstance(roles, str):
                roles = ','.join(roles or [])

            env['HTTP_X_ROLES'] = roles

        return env

    def start_response(self, status, headers):
        self.status = status
        self.headers = headers


def app(env, start_response):
    start_response('204 No Content', [])
    return []


def wrap_403(app):

    def middleware(env, start_response):
        start_response('403 Forbidden', [])
        return []

    return middleware
