from statsd import StatsClient
import time
from oslo.config import cfg

OPT_GROUP_NAME = 'eom:statsd'
OPTIONS = [
    cfg.StrOpt('statsd_address',
               help='host:port for statsd server.',
               required=True)
]


def wrap(app):
    conf = cfg.CONF
    conf.register_opts(OPTIONS, group=OPT_GROUP_NAME)
    addr = conf[OPT_GROUP_NAME].statsd_address or 'localhost'
    client = StatsClient(addr)

    def middleware(env, start_response):

        def _start_response(status, headers, *args):
            statuscode = int(status[:3])
            if statuscode / 500 == 1:
                client.incr("500")
            elif statuscode / 400 == 1:
                client.incr("400")
            elif statuscode / 200 == 1:
                client.incr("200")
            client.incr("requests")

            return start_response(status, headers, *args)

        start = time.time() * 1000
        response = app(env, _start_response)
        stop = time.time() * 1000

        elapsed = stop - start
        client.timing("latency", elapsed)
        return response

    return middleware