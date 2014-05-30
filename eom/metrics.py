from statsd import StatsClient
import time
import re
from oslo.config import cfg
import socket

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

    # initialize buckets
    for request_method in ["GET", "PUT", "HEAD", "POST", "DELETE", "PATCH"]:
        for name, regex in regex_strings:
            for code in ["2xx", "4xx", "5xx"]:
                client.incr("marconi."+socket.gethostname()+".requests."+request_method+"."+name+"."+code)
                client.decr("marconi."+socket.gethostname()+".requests."+request_method+"."+name+"."+code)


    def middleware(env, start_response):

        def _start_response(status, headers, *args):
            status_code = int(status[:3])
            if status_code / 500 == 1:
                client.incr("marconi."+hostname+".requests."+request_method+"."+api_method+".5xx")
            elif status_code / 400 == 1:
                client.incr("marconi."+hostname+".requests."+request_method+"."+api_method+".4xx")
            elif status_code / 200 == 1:
                client.incr("marconi."+hostname+".requests."+request_method+"."+api_method+".2xx")

            client.incr("marconi."+hostname+".requests."+request_method+"."+api_method)

            return start_response(status, headers, *args)

        request_method = env["REQUEST_METHOD"]
        path = env["PATH_INFO"]
        hostname = socket.gethostname()
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