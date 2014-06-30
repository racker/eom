# Copyright (c) 2013 Rackspace, Inc.
#
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR ONDITIONS OF ANY KIND, either express or
# implied.
#
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import subprocess
import time
import json
import copy
import requests
from multiprocessing import Process, Queue
from testtools import testcase
from tests import util

APP_CONTENTS = '''
from eom.utils import redis_pool
from eom import governor
from marconi.queues.transport.wsgi import app as marconi

redis_client = redis_pool.get_client()
marconi_app = marconi.app
application = governor.wrap(marconi_app, redis_client)
'''


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


class TestUwsgiRequests(util.TestCase):

    def setUp(self):
        super(TestUwsgiRequests, self).setUp()

        self.limits = {
            'defaultLimit': 0,
            'specialLimit': 0,
            '281928defaultLimit': 0,
            '281929specialLimit': 0}

        self.getLimits()

        self.appfilename = 'guvapp.py'
        with open('guvapp.py', 'w') as guvwriter:
            guvwriter.write(APP_CONTENTS)

        self.port = ':8000'
        self.socketurl = 'http://127.0.0.1:8000'

        with open(os.devnull, 'wb') as pipeDown:
            self.uwsgi_process = subprocess.Popen(
                [
                    'uwsgi',
                    '--http-socket', self.port,
                    '-H',  os.environ.get('VIRTUAL_ENV'),
                    '--wsgi-file', self.appfilename
                ], stdout=pipeDown, stderr=pipeDown
            )

        self.defaultHeaders = {
            'content-type': 'application/json',
            'Client-ID': '0fc2b683-e762-475b-855f-9d813daf15a2',
            'X-Project-ID': '123456'}

        time.sleep(0.5)

    def _get_uwsgi_response(self):
        _kill_uwsgi_process(self.uwsgi_process)

        # Blocks until the process exits, so no need to sleep
        _, err = self.uwsgi_process.communicate()
        return err

    def tearDown(self):
        _kill_uwsgi_process(self.uwsgi_process)  # Just in case
        time.sleep(0.3)
        super(TestUwsgiRequests, self).tearDown()

    def getLimits(self):
        configPath = os.environ.get('HOME') + '/.marconi/governor.json-sample'
        with open(configPath, 'r') as configReader:
            conf = configReader.read()
            jsnConf = json.loads(conf)
            self.limits['defaultLimit'] = jsnConf[1]['limit']
            self.limits['specialLimit'] = jsnConf[0]['limit']

        configPath = '%s/.marconi/governor-project.json-sample' % (
            os.environ.get('HOME'))
        with open(configPath, 'r') as configReader:
            conf = configReader.read()
            jsnConf = json.loads(conf)
            self.limits['281928defaultLimit'] = jsnConf[0]['limit']
            self.limits['281929specialLimit'] = jsnConf[1]['limit']

    def test_GetTillJustOverLimit(self):
        time.sleep(1)
        call = lambda: requests.get(
            self.socketurl + '/v1/queues', headers=self.defaultHeaders)
        resps = [call().status_code for _ in range(
            self.limits['defaultLimit'] + 1)]
        self.assertNotEqual(resps[-2], 429)
        self.assertEqual(resps[-1], 429)

    def test_LimitResetsAfterWait(self):
        time.sleep(1)
        startTime = time.time()
        call = lambda: requests.get(
            self.socketurl + '/v1/queues', headers=self.defaultHeaders)
        resps = [call().status_code for _ in range(
            self.limits['defaultLimit'] + 1)]
        endTime = time.time()

        self.assertNotEqual(resps[-2], 429)
        self.assertEqual(resps[-1], 429)
        # time.sleep(1 - endTime + startTime + 0.05)
        self.assertNotEqual(call().status_code, 429)

    def test_PostAndGetLargeMessages(self):
        # create queue if it doesn't exist
        time.sleep(1)
        urlRequest = self.socketurl + '/v1/queues/trillian'
        reqCheckQueue = requests.get(urlRequest, headers=self.defaultHeaders)

        if reqCheckQueue.status_code != 204:
            queueData = {'metadata': 'A packetful of metadata'}

            reqAddQueue = requests.put(
                urlRequest, data=json.dumps(queueData),
                headers=self.defaultHeaders)

            self.assertEqual(reqAddQueue.status_code, 201)

        # post message
        time.sleep(1)
        messageSize = 131080
        for _ in range(self.limits['defaultLimit'] - 1):
            rnd = 'o' * messageSize
            largeData = [{'ttl': 120, 'body': rnd}]

            reqPostMsg = requests.post('%s/v1/queues/trillian/messages' %
                                       (self.socketurl),
                                       data=json.dumps(largeData),
                                       headers=self.defaultHeaders)

            self.assertEqual(reqPostMsg.status_code, 201)

        # get the messages
        echoParams = {'echo': 'true'}
        reqGetMsgs = requests.get(
            self.socketurl + '/v1/queues/trillian/messages/',
            params=echoParams, headers=self.defaultHeaders)
        self.assertEqual(reqGetMsgs.status_code, 200)

    def test_BombardAcrossProjectIDs(self):
        headerProjA = copy.deepcopy(self.defaultHeaders)
        headerProjB = copy.deepcopy(self.defaultHeaders)
        headerProjA['X-Project-ID'] = '123450'
        headerProjB['X-Project-ID'] = '281928'

        # A - stays just under, B hits limit.
        time.sleep(1)

        callA = lambda: requests.get(
            self.socketurl + '/v1/queues', headers=headerProjA)
        callB = lambda: requests.get(
            self.socketurl + '/v1/queues', headers=headerProjB)

        respsA = [
            callA().status_code for _ in range(self.limits['defaultLimit'])]
        respsB = [callB().status_code for _ in range(
            self.limits['281928defaultLimit'] + 1)]

        self.assertNotEqual(respsA[-1], 429)
        self.assertEqual(respsB[-1], 429)

        # A and B are good independently
        time.sleep(2)
        respsA = [
            callA().status_code for _ in range(self.limits['defaultLimit'])]

        respsB = [callB().status_code for _ in range(
            self.limits['281928defaultLimit'])]

        self.assertNotEqual(respsA[-1], 429)
        self.assertNotEqual(respsB[-1], 429)

        # A and B hit limits independently
        time.sleep(2)
        respsA = [callA().status_code for _ in range(
            self.limits['defaultLimit'] + 1)]

        respsB = [callB().status_code for _ in range(
            self.limits['281928defaultLimit'] + 1)]

        self.assertEqual(respsA[-1], 429)
        self.assertEqual(respsB[-1], 429)

    def test_marconiErrors(self):
        time.sleep(1)
        urlQueue = self.socketurl + '/v1/queues/beeblebrox'

        # delete queue, just in case
        reqCheckQueue = requests.delete(urlQueue, headers=self.defaultHeaders)

        # check 404 on dummy queue
        reqCheckQueue = requests.get(urlQueue, headers=self.defaultHeaders)
        self.assertEqual(reqCheckQueue.status_code, 404)

        # create queue and check 400 on sending a large message
        queueData = {'metadata': '42'}
        reqAddQueue = requests.put(urlQueue,
                                   data=json.dumps(queueData),
                                   headers=self.defaultHeaders)
        self.assertEqual(reqAddQueue.status_code, 201)

        messageSize = 1538800
        largeMsg = [{'ttl': 120, 'body': 'o' * messageSize}]
        reqPostMsg = requests.post('%s/messages' % (urlQueue),
                                   data=json.dumps(largeMsg),
                                   headers=self.defaultHeaders)
        self.assertEqual(reqPostMsg.status_code, 400)
