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
