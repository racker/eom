import re
import socket
import time

from oslo.config import cfg
import statsd

OPT_GROUP_NAME = 'eom:statsd'
OPTIONS = [
    cfg.StrOpt('address',
               help='host:port for statsd server.',
               required=True),
    cfg.ListOpt('path_regexes_keys',
                help='keys for regexes for the paths of the WSGI app',
                required=False),

    cfg.ListOpt('path_regexes_values',
                help='regexes for the paths of the WSGI app',
                required=False),

    cfg.StrOpt("prefix",
               help="Prefix for graphite metrics",
               required=False)
]


def wrap(app):
    conf = cfg.CONF
    conf.register_opts(OPTIONS, group=OPT_GROUP_NAME)
    addr = conf[OPT_GROUP_NAME].address or 'localhost'
    keys = conf[OPT_GROUP_NAME].path_regexes_keys or []
    values = conf[OPT_GROUP_NAME].path_regexes_values or []
    prefix = conf[OPT_GROUP_NAME].prefix or ""

    regex_strings = zip(keys, values)
    regex = []
    for (method, pattern) in regex_strings:
        regex.append((method, re.compile(pattern)))

    client = statsd.StatsClient(addr, prefix=prefix)

    # initialize buckets
    for request_method in ["GET", "PUT", "HEAD", "POST", "DELETE", "PATCH"]:
        for name, regexstr in regex_strings:
            for code in ["2xx", "4xx", "5xx"]:
                client.incr("marconi." + socket.gethostname() + ".requests." +
                            request_method + "." + name + "." + code)
                client.decr("marconi." + socket.gethostname() + ".requests." +
                            request_method + "." + name + "." + code)

    def middleware(env, start_response):

        request_method = env["REQUEST_METHOD"]
        path = env["PATH_INFO"]
        hostname = socket.gethostname()
        api_method = "unknown"

        for (method, regex_pattern) in regex:
            if regex_pattern.match(path):
                api_method = method

        def _start_response(status, headers, *args):
            status_path = ("marconi." + hostname + ".requests." +
                           request_method + "." + api_method)
            status_code = int(status[:3])
            if status_code / 500 == 1:
                client.incr(status_path + ".5xx")
            elif status_code / 400 == 1:
                client.incr(status_path + ".4xx")
            elif status_code / 200 == 1:
                client.incr(status_path + ".2xx")

            # client.incr("marconi." + hostname + ".requests." +
            #            request_method + "." + api_method)

            return start_response(status, headers, *args)

        start = time.time() * 1000
        response = app(env, _start_response)
        stop = time.time() * 1000

        elapsed = stop - start
        client.timing("marconi."+hostname+".latency."+request_method, elapsed)
        return response

    return middleware
