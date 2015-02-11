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
#
# See the License for the specific language governing permissions and
# limitations under the License.
import io
import logging

import ddt
import fixtures
import httpretty
from oslo_config import fixture as fixture_config
import stackinabox.httpretty
from stackinabox.services.service import StackInABoxService
from stackinabox.stack import StackInABox

from eom import proxy
from tests import util


LOG = logging.getLogger(__name__)


class ProxyTestingService(StackInABoxService):

    DELETE_RESPONSE = "Where'd it go?"
    GET_RESPONSE = "You've been gotten"
    OPTIONS_ALLOW_HEADERS = ','.join(StackInABoxService.METHODS)
    OPTIONS_RESPONSE = "Enjoy your options while they last"
    PATCH_RESPONSE = "Glad to be of your medical service"
    POST_RESPONSE = "Riding horses is fun."
    PUT_RESPONSE = "You're presciption is ready."

    def __init__(self):
        super(ProxyTestingService, self).__init__('proxy')
        self.register(StackInABoxService.GET, '/hello',
                      ProxyTestingService.root_handler)
        self.register('DELETE', '/d',
                      ProxyTestingService.delete_handler)
        self.register(StackInABoxService.GET, '/g',
                      ProxyTestingService.get_handler)
        self.register(StackInABoxService.HEAD, '/h',
                      ProxyTestingService.head_handler)
        self.register(StackInABoxService.OPTIONS, '/o',
                      ProxyTestingService.options_handler)
        self.register(StackInABoxService.PATCH, '/p1',
                      ProxyTestingService.patch_handler)
        self.register(StackInABoxService.POST, '/p2',
                      ProxyTestingService.post_handler)
        self.register(StackInABoxService.PUT, '/p3',
                      ProxyTestingService.put_handler)

    def root_handler(self, request, uri, headers):
        return (200, headers, 'Hello')

    def delete_handler(self, request, uri, headers):
        return (200, headers, ProxyTestingService.DELETE_RESPONSE)

    def get_handler(self, request, uri, headers):
        return (200, headers, ProxyTestingService.GET_RESPONSE)

    def head_handler(self, request, uri, headers):
        return (201, headers, '')

    def options_handler(self, request, uri, headers):
        headers['allow'] = ProxyTestingService.OPTIONS_ALLOW_HEADERS
        return (200, headers, ProxyTestingService.OPTIONS_RESPONSE)

    def patch_handler(self, request, uri, headers):
        return (200, headers, ProxyTestingService.PATCH_RESPONSE)

    def post_handler(self, request, uri, headers):
        return (200, headers, ProxyTestingService.POST_RESPONSE)

    def put_handler(self, request, uri, headers):
        return (200, headers, ProxyTestingService.PUT_RESPONSE)


class FakeProxyResponse(object):

    def __init__(self):
        self.status_code = None
        self.reason = None
        self.result = None
        self.headers = None
        self.__body = None

    def __call__(self, result, headers):
        self.result = result
        status_code, self.reason = result.split(' ', maxsplit=1)
        self.status_code = int(status_code)
        self.headers = headers

    def app_call(self, app, environ):
        self.__body = app(environ, self)
        if self.__body is not None:
            LOG.debug('Response body has a body')
        else:
            LOG.debug('Response has no body')

    @property
    def body(self):
        return bytes().join(self.__body)

    def iter_content(self, chunk_size=None):
        yield self.__body


@ddt.ddt
@httpretty.activate
class TestProxy(util.TestCase, fixtures.TestWithFixtures):

    def setUp(self):
        super(TestProxy, self).setUp()

        StackInABox.register_service(ProxyTestingService())

        self.response = FakeProxyResponse()
        self.CONF = self.useFixture(fixture_config.Config()).conf
        self.__wsgi = {
            'version': 'test.proxy',
            'url_scheme': None,
            'input': io.BytesIO(),
            'errors': io.BytesIO(),
            'multithread': False,
            'multiprocess': False,
            'run_once': False
        }

    def tearDown(self):
        super(TestProxy, self).tearDown()
        StackInABox.reset_services()

    def make_environ(self, scheme, method, path,
                     headers, body=None, query_string=''):
        environ = {
            'wsgi.{0}'.format(k): v
            for k, v in self.__wsgi.items()
        }
        environ['wsgi.url_scheme'] = scheme

        environ.update({
            k: v
            for k, v in headers.items()
        })

        environ['request_method'] = method
        environ['script_name'] = path
        environ['path_info'] = path
        environ['query_string'] = query_string
        environ['http_host'] = 'proxy.test'
        environ['server_name'] = 'proxy.test'
        environ['server_port'] = 9999

        if body is not None:
            environ['wsgi.input'].write(body)

        return environ

    def test_proxy_init_valid(self):
        stackinabox.httpretty.httpretty_registration('localhost')
        service_url = 'http://localhost/proxy/'
        service_timeoutms = 30000

        self.CONF.set_override('upstream',
                               service_url,
                               group=proxy.PROXY_GROUP_NAME)
        self.CONF.set_override('timeout',
                               service_timeoutms,
                               group=proxy.PROXY_GROUP_NAME)

        my_proxy = proxy.ReverseProxy()

        self.assertEqual(my_proxy.config['upstream'],
                         service_url)
        self.assertEqual(my_proxy.config['timeout'],
                         service_timeoutms)

        environ = self.make_environ(scheme=u'http',
                                    method=u'GET',
                                    path=u'hello',
                                    headers={},
                                    body=None,
                                    query_string=u'')

        self.response.app_call(my_proxy, environ)

        controlled_headers = {
            k.upper(): v
            for k, v in self.response.headers
        }
        self.assertNotIn('X-Reverse-Proxy-Transaction-Id'.upper(),
                      controlled_headers)

        self.assertEqual(self.response.status_code,
                         200)
        self.assertEqual(self.response.body,
                         b'Hello')

    def test_proxy_init_invalid(self):
        stackinabox.httpretty.httpretty_registration('localhost')
        service_url = None
        service_timeoutms = 30000

        self.CONF.set_override('upstream',
                               service_url,
                               group=proxy.PROXY_GROUP_NAME)
        self.CONF.set_override('timeout',
                               service_timeoutms,
                               group=proxy.PROXY_GROUP_NAME)

        my_proxy = proxy.ReverseProxy()

        self.assertEqual(my_proxy.config['upstream'],
                         service_url)
        self.assertEqual(my_proxy.config['timeout'],
                         service_timeoutms)

        environ = self.make_environ(scheme=u'http',
                                    method=u'GET',
                                    path=u'/',
                                    headers={},
                                    body=None,
                                    query_string=u'')

        self.response.app_call(my_proxy, environ)

        self.assertEqual(self.response.status_code,
                         500)
        self.assertEqual(self.response.reason,
                         'Internal Server Error')

    @ddt.data((200, 'd', 'DELETE',
               ProxyTestingService.DELETE_RESPONSE.encode()),
              (200, 'g', 'GET',
               ProxyTestingService.GET_RESPONSE.encode()),
              (201, 'h', 'HEAD',
               b''),
              (200, 'o', 'OPTIONS',
               ProxyTestingService.OPTIONS_RESPONSE.encode()),
              (200, 'p1', 'PATCH',
               ProxyTestingService.PATCH_RESPONSE.encode()),
              (200, 'p2', 'POST',
               ProxyTestingService.POST_RESPONSE.encode()),
              (200, 'p3', 'PUT',
               ProxyTestingService.PUT_RESPONSE.encode()))
    @ddt.unpack
    def test_proxy_test_http_verb(self, code, path, verb, response_body):
        stackinabox.httpretty.httpretty_registration('localhost')
        service_url = 'http://localhost/proxy/'
        service_timeoutms = 30000

        self.CONF.set_override('upstream',
                               service_url,
                               group=proxy.PROXY_GROUP_NAME)
        self.CONF.set_override('timeout',
                               service_timeoutms,
                               group=proxy.PROXY_GROUP_NAME)

        my_proxy = proxy.ReverseProxy()

        self.assertEqual(my_proxy.config['upstream'],
                         service_url)
        self.assertEqual(my_proxy.config['timeout'],
                         service_timeoutms)

        environ = self.make_environ(scheme=u'http',
                                    method=verb,
                                    path=path,
                                    headers={},
                                    body=None,
                                    query_string=u'')

        self.response.app_call(my_proxy, environ)

        self.assertEqual(self.response.status_code,
                         code)
        self.assertEqual(self.response.body,
                         response_body)
