import mock
from stackinabox.stack import StackInABox
import stackinabox.util_requests_mock

from eom import metrics
from tests import util
from tests.util.httpstatsd import HttpStatsdService
from tests.util.statsd_http_client import HttpStatsdClient


metrics.configure(util.CONF)


class TestMetrics(util.TestCase):

    def setUp(self):
        super(TestMetrics, self).setUp()
        self.service = HttpStatsdService()
        StackInABox.register_service(self.service)
        self.statsd_client = HttpStatsdClient('http://localhost/statsd/')

    def tearDown(self):
        super(TestMetrics, self).tearDown()
        StackInABox.reset_services()

    def test_basic(self):
        with stackinabox.util_requests_mock.activate():
            stackinabox.util_requests_mock.requests_mock_registration(
                'localhost')
            with mock.patch('statsd.StatsClient') as mok_statsd_client:
                mok_statsd_client.return_value = self.statsd_client

                self.metrics = metrics.wrap(util.app)

    def test_delete(self):
        with stackinabox.util_requests_mock.activate():
            stackinabox.util_requests_mock.requests_mock_registration(
                'localhost')
            with mock.patch('statsd.StatsClient') as mok_statsd_client:
                mok_statsd_client.return_value = self.statsd_client

                self.metrics = metrics.wrap(util.app)

                my_env = self.create_env('/', method='DELETE')

                self.assertIn('REQUEST_METHOD', my_env)
                self.assertIn('PATH_INFO', my_env)
                self.metrics(my_env, self.start_response)

    def test_get(self):
        with stackinabox.util_requests_mock.activate():
            stackinabox.util_requests_mock.requests_mock_registration(
                'localhost')
            with mock.patch('statsd.StatsClient') as mok_statsd_client:
                mok_statsd_client.return_value = self.statsd_client

                self.metrics = metrics.wrap(util.app)

                my_env = self.create_env('/', method='GET')

                self.assertIn('REQUEST_METHOD', my_env)
                self.assertIn('PATH_INFO', my_env)
                self.metrics(my_env, self.start_response)

    def test_head(self):
        with stackinabox.util_requests_mock.activate():
            stackinabox.util_requests_mock.requests_mock_registration(
                'localhost')
            with mock.patch('statsd.StatsClient') as mok_statsd_client:
                mok_statsd_client.return_value = self.statsd_client

                self.metrics = metrics.wrap(util.app)

                my_env = self.create_env('/', method='HEAD')

                self.assertIn('REQUEST_METHOD', my_env)
                self.assertIn('PATH_INFO', my_env)
                self.metrics(my_env, self.start_response)

    def test_patch(self):
        with stackinabox.util_requests_mock.activate():
            stackinabox.util_requests_mock.requests_mock_registration(
                'localhost')
            with mock.patch('statsd.StatsClient') as mok_statsd_client:
                mok_statsd_client.return_value = self.statsd_client

                self.metrics = metrics.wrap(util.app)

                my_env = self.create_env('/', method='PATCH')

                self.assertIn('REQUEST_METHOD', my_env)
                self.assertIn('PATH_INFO', my_env)
                self.metrics(my_env, self.start_response)

    def test_post(self):
        with stackinabox.util_requests_mock.activate():
            stackinabox.util_requests_mock.requests_mock_registration(
                'localhost')
            with mock.patch('statsd.StatsClient') as mok_statsd_client:
                mok_statsd_client.return_value = self.statsd_client

                self.metrics = metrics.wrap(util.app)

                my_env = self.create_env('/', method='POST')

                self.assertIn('REQUEST_METHOD', my_env)
                self.assertIn('PATH_INFO', my_env)
                self.metrics(my_env, self.start_response)

    def test_put(self):
        with stackinabox.util_requests_mock.activate():
            stackinabox.util_requests_mock.requests_mock_registration(
                'localhost')
            with mock.patch('statsd.StatsClient') as mok_statsd_client:
                mok_statsd_client.return_value = self.statsd_client

                self.metrics = metrics.wrap(util.app)

                my_env = self.create_env('/', method='PUT')

                self.assertIn('REQUEST_METHOD', my_env)
                self.assertIn('PATH_INFO', my_env)
                self.metrics(my_env, self.start_response)

    def test_invalid_method(self):
        with stackinabox.util_requests_mock.activate():
            stackinabox.util_requests_mock.requests_mock_registration(
                'localhost')
            with mock.patch('statsd.StatsClient') as mok_statsd_client:
                mok_statsd_client.return_value = self.statsd_client

                self.metrics = metrics.wrap(util.app)

                my_env = self.create_env('/', method='INVALID')

                self.assertIn('REQUEST_METHOD', my_env)
                self.assertIn('PATH_INFO', my_env)
                self.metrics(my_env, self.start_response)
