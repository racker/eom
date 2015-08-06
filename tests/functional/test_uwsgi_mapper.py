# Copyright (c) 2013 Rackspace, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import subprocess
import sys
import tempfile
import time

import requests
import six
from testtools import testcase

from tests import util


MAP_CONTENTS = """
{
    "map": {
        "X-Project-Id": "project"
    }
}
"""

CONF_CONTENTS = """
[eom:uwsgi:mapper]
options_file = {0}
"""

APP_CONTENTS = """
from oslo_config import cfg

from eom.uwsgi import logvar_mapper


CONF = cfg.CONF

CONF(args=[], default_config_files=['{0}'])

def app_204(env, start_response):
    start_response('204 No Content', [])
    return [b""]


app = application = logvar_mapper.wrap(app_204)
"""


def _kill_uwsgi_process(process):
    try:
        # NOTE(cabrera): using process.terminate instead of
        # process.kill here because on some platforms, uwsgi will
        # outright ignore SIGKILL. This was happening on Mac OS
        # X. Also ensure that the --die-on-term flag in enabled below
        # in setUp().
        process.terminate()
    except OSError:
        pass


class TestUwsgiMapper(util.TestCase):

    @testcase.skipIf(hasattr(sys, 'pypy_version_info'),
                     'getting uwsgi running under pypy is difficult')
    def setUp(self):
        super(TestUwsgiMapper, self).setUp()

        # NOTE(cabrera): Create temporary files for the configuration
        # files and the application. This makes testing directory
        # independent and avoids introducing files into our
        # repository.
        # NOTE(BenjamenMeyer): Tests seem to fail without the w+ parameter
        self.map_file = tempfile.NamedTemporaryFile(mode='w+')
        self.map_file.write(six.u(MAP_CONTENTS))

        self.conf_file = tempfile.NamedTemporaryFile(mode='w+')
        self.conf_file.write(six.u(CONF_CONTENTS.format(self.map_file.name)))

        self.app_file = tempfile.NamedTemporaryFile(mode='w+')
        self.app_file.write(six.u(APP_CONTENTS.format(self.conf_file.name)))

        # NOTE(cabrera): Prepare the files to be read in by the uwsgi
        # process. This is necessary because child processes inherit
        # open file descriptors from the parent, including SEEK
        # position. After having written the app, map, and conf files
        # above, the seek cursor is pointing to end of file for all of
        # them. Without seeking to start, uwsgi fails to launch
        # because it encounters an empty application file.
        self.app_file.file.seek(0)
        self.map_file.file.seek(0)
        self.conf_file.file.seek(0)

        url = '127.0.0.1:8783'
        self.url = 'http://' + url

        self.uwsgi_process = subprocess.Popen(
            [
                'uwsgi',
                '--master',
                '-H', os.environ.get('VIRTUAL_ENV'),
                '--http-socket', url,
                '--die-on-term',
                '--wsgi-file', self.app_file.name,
                '--logformat', '[TEST-TEMPVARS]: %(project)',
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        # NOTE(cabrera): Give uwsgi time to boot. This value was
        # chosen after some experimentation. If you find these tests
        # failing spuriously in your test environment, submit an issue
        # to the github repo and let's bump this value up!
        time.sleep(0.03)

    def tearDown(self):
        _kill_uwsgi_process(self.uwsgi_process)  # Just in case
        self.app_file.close()
        self.map_file.close()
        self.conf_file.close()
        super(TestUwsgiMapper, self).tearDown()

    def _get_uwsgi_response(self):
        _kill_uwsgi_process(self.uwsgi_process)

        # Blocks until the process exits, so no need to sleep
        _, err = self.uwsgi_process.communicate()
        return err

    def _expect(self, headers=None):
        resp = requests.get(self.url, headers=headers)
        self.assertEqual(resp.status_code, 204)

        loglines = self._get_uwsgi_response()
        project = headers.get('X-Project-Id') if headers else None
        self.assertIn(six.b('[TEST-TEMPVARS]: {0}'.format(project)),
                      loglines)

    def test_map_logs_project_when_given(self):
        self._expect({'X-Project-Id': 1234})

    def test_map_logs_None_when_missing(self):
        self._expect()
