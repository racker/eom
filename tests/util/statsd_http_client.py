
import requests
import statsd.client


class HttpStatsdClient(statsd.client.StatsClientBase):

    def __init__(self, url, prefix=None):
        self._url = url
        self._prefix = prefix

    def _send(self, data):
        res = requests.post(self._url, data=data)
        if res.status_code != 201:
            print('Call Failed')

    def pipeline(self):
        return statsd.client.TCPPipeline(self)
