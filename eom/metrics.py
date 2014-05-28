from statsd import StatsClient
import time
import re
from oslo.config import cfg

OPT_GROUP_NAME = 'eom:statsd'
OPTIONS = [
    cfg.StrOpt('statsd_address',
               help='host:port for statsd server.',
               required=True)
]

regex_strings = [
    ('queues', '^/v[0-9]+(\.[0-9]+)?/queues(/)?(\?(.)+)?$'),
    ('queue', '^/v[0-9]+(\.[0-9]+)?/queues/[a-zA-Z0-9\-_]+(/)?$'),
    ('messages', '^/v[0-9]+(\.[0-9]+)?/queues/[a-zA-Z0-9\-_]+/messages(/)?(\?(.)+)?$'),
    ('message_claim', '^/v[0-9]+(\.[0-9]+)?/queues/[a-zA-Z0-9\-_]+'
                      '/messages/[a-zA-Z0-9_\-]+(/)?(\?claim_id=[a-zA-Z0-9_\-]+)?$'),
    ('claim_create', '^/v[0-9]+(\.[0-9]+)?/queues/[a-zA-Z0-9\-_]+/claims(/)?(\?(.)+)?$'),
    ('claim', '^/v[0-9]+(\.[0-9]+)?/queues/[a-zA-Z0-9\-_]+/claims/[a-zA-Z0-9_\-]+(/)?$'),
]


def wrap(app):
    conf = cfg.CONF
    conf.register_opts(OPTIONS, group=OPT_GROUP_NAME)
    addr = conf[OPT_GROUP_NAME].statsd_address or 'localhost'
    client = StatsClient(addr)

    def middleware(env, start_response):

        def _start_response(status, headers, *args):
            status_code = int(status[:3])
            if status_code / 500 == 1:
                client.incr("requests.500")
                client.incr("requests."+request_method+".500")
                client.incr("requests."+request_method+"."+api_method+".500")
            elif status_code / 400 == 1:
                client.incr("requests.400")
                client.incr("requests."+request_method+".400")
                client.incr("requests."+request_method+"."+api_method+".400")
            elif status_code / 200 == 1:
                client.incr("requests.200")
                client.incr("requests."+request_method+".200")
                client.incr("requests."+request_method+"."+api_method+".200")

            client.incr("requests.total")
            client.incr("requests."+request_method)
            client.incr("requests."+request_method+"."+api_method)

            return start_response(status, headers, *args)

        request_method = env["REQUEST_METHOD"]
        path = env["PATH_INFO"]
        api_method = ""

        for (method, pattern) in regex_strings:
            regex = re.compile(pattern)
            if regex.match(path):
                api_method = method

        start = time.time() * 1000
        response = app(env, _start_response)
        stop = time.time() * 1000

        elapsed = stop - start
        client.timing("latency."+request_method, elapsed)
        return response

    return middleware