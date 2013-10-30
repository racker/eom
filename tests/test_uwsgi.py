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

import io
import multiprocessing
import os
import os.path
import signal
import subprocess
import sys
import tempfile
import time

import requests
from tests import util

MY_DIR = os.path.abspath(os.path.dirname(__file__))
WSGI_FILE = 'uwsgi-app.py'


class TestUWSGI(util.TestCase):

    def setUp(self):
        super(TestUWSGI, self).setUp()

        self.uwsgi_process = subprocess.Popen([
            'uwsgi',
            '--master',
            '--http', '127.0.0.1:8783',
            '--chdir', os.path.join(MY_DIR, '..'),
            '--wsgi-file', os.path.join('tests', WSGI_FILE),
            '--logformat', '[TEST-TEMPVARS]: %(project_id), %(client_id)',
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)

        # Give uwsgi time to boot
        time.sleep(0.5)

    def _kill_uwsgi(self):
        try:
            os.kill(self.uwsgi_process.pid, signal.SIGINT)
        except OSError:
            # Propbably already dead
            pass

    def _get_uwsgi_response(self):
        self._kill_uwsgi()

        # Blocks until the process exits, so no need to sleep
        out, err = self.uwsgi_process.communicate()
        return err

    def tearDown(self):
        self._kill_uwsgi()  # Just in case
        super(TestUWSGI, self).tearDown()

    def test_tempvar_map(self):
        url = 'http://127.0.0.1:8783/v1'
        headers = {
            'X-Project-ID': 1234,
            'clieNt-Id': 'xyz',
        }

        resp = requests.get(url, headers=headers)
        self.assertEquals(resp.status_code, 204)

        loglines = self._get_uwsgi_response()
        self.assertIn('[TEST-TEMPVARS]: 1234, xyz', loglines)

    def test_tempvar_map_na(self):
        url = 'http://127.0.0.1:8783/v1'
        resp = requests.get(url)
        self.assertEquals(resp.status_code, 204)

        loglines = self._get_uwsgi_response()
        self.assertIn('[TEST-TEMPVARS]: None, None', loglines)
