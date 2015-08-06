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

"""
HTTP statsd Service Mock
"""
import re

from stackinabox.services.service import StackInABoxService


class HttpStatsdService(StackInABoxService):

    def __init__(self):
        super(HttpStatsdService, self).__init__('statsd')
        self.register(StackInABoxService.PUT,
                      re.compile('^/$'),
                      HttpStatsdService.handler)
        self.register(StackInABoxService.POST,
                      re.compile('^/$'),
                      HttpStatsdService.handler)

    def handler(self, request, uri, headers):
        print('HttpStatsdService ({0}): Received {1}'
              .format(id(self), request.body))
        return (201, headers, '')
