# Copyright (c) 2014 Rackspace, Inc.
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
import logging
import re
import uuid

from oslo.config import cfg
import requests


LOG = logging.getLogger(__name__)
CONF = cfg.CONF

PROXY_GROUP_NAME = 'eom:proxy'
PROXY_OPTIONS = [
    cfg.StrOpt('upstream'),
    cfg.IntOpt('timeout')
]

CONF.register_opts(PROXY_OPTIONS, group=PROXY_GROUP_NAME)


class ReverseProxyRequest(object):

    def __init__(self, environ):
        self.environ = environ
        self.environ_controlled = {
            k.upper(): v
            for k, v in environ.items()
        }
        self.headers = {}

        self.method = self.environ_controlled['REQUEST_METHOD']
        self.path_virtual = self.environ_controlled['SCRIPT_NAME']
        self.path = self.environ_controlled['PATH_INFO']
        self.query_string = self.environ_controlled['QUERY_STRING']
        self.server = {
            'host': self.environ_controlled['HTTP_HOST']
            if 'HTTP_HOST' in self.environ_controlled else None,
            'name': self.environ_controlled['SERVER_NAME'],
            'port': self.environ_controlled['SERVER_PORT']
        }
        self.body = None
        self.wsgi = {
            'version': environ['wsgi.version'],
            'scheme': environ['wsgi.url_scheme'],
            'input': environ['wsgi.input'],
            'errors': environ['wsgi.errors'],
            'multithread': environ['wsgi.multithread'],
            'multiprocess': environ['wsgi.multiprocess'],
            'run_once': environ['wsgi.run_once']
        }
        self.transaction_id = uuid.uuid4()
        self.rebuild_headers()

    def rebuild_headers(self):
        self.headers = {}

        for k, v in self.environ_controlled.items():

            kp = k
            kp.replace('_', '-')

            if k.startswith('HTTP_'):
                self.headers[kp] = v

            elif k.startswith('CONTENT_'):
                self.headers[kp] = v

        self.headers['X-Reverse-Proxy-Transaction-Id'] = str(
            self.transaction_id)

    def url(self, upstream):
        return '{0}{1}?{2}'.format(upstream,
                                   self.path,
                                   self.query_string)

    def body(self):
        return self.wsgi['input']


class ReverseProxy(object):
    """WSGI Reverse Proxy Application

    """
    STREAM_BLOCK_SIZE = 8 * 1024  # 8 Kilobytes

    def __init__(self):
        config_group = CONF[PROXY_GROUP_NAME]

        self.config = {
            'upstream': config_group['upstream'],
            'timeout': config_group['timeout']
        }

        if self.config['upstream'] in (None, ''):
            LOG.error('upstream not valid')
            LOG.warn('Configuration Error - upstream = {0}'
                     .format(self.config['upstream']))

        url_regex = re.compile('(http|https|ftp)?(://)?[\w\d\.\-_]+:?(\d+)?/*')
        if self.config['upstream']:
            if not url_regex.match(self.config['upstream']):
                LOG.error('Invalid URL - {0:}'.format(self.config['upstream']))

    @staticmethod
    def make_response_text(response):
        return '{0} {1}'.format(response.status_code,
                                response.reason)

    def handler(self, environ, start_response):

        if self.config['upstream'] in (None, ''):
            start_response('500 Internal Server Error',
                           [('Content-Type', 'plain/text')])
            return [b'Please contact the administrator.']

        req = ReverseProxyRequest(environ)

        target_url = req.url(self.config['upstream'])

        response = requests.request(req.method,
                                    target_url,
                                    headers=req.headers,
                                    data=req.body,
                                    timeout=self.config['timeout'],
                                    allow_redirects=False,
                                    stream=True)
        start_response(ReverseProxy.make_response_text(response),
                       [(k, v) for k, v in response.headers.items()])
        if 'wsgi.file_wrapper' in environ:
            if environ['wsgi.file_wrapper']:
                file_wrapper = environ['wsgi.file_wrapper']
                return file_wrapper(response.raw,
                                    ReverseProxy.STREAM_BLOCK_SIZE)

        return iter(lambda: response.raw.read(ReverseProxy.STREAM_BLOCK_SIZE),
                    b'')

    def __call__(self, environ, start_response):
        return self.handler(environ, start_response)
