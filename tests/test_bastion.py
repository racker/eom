import ddt

from eom import bastion
from tests import util


@ddt.ddt
class TestBastion(util.TestCase):

    def setUp(self):
        super(TestBastion, self).setUp()

        app = util.app
        wrapped_app = util.wrap_404(app)
        self.bastion = bastion.wrap(app, wrapped_app)

    def _expect(self, env, code):
        lookup = {204: '204 No Content',
                  404: '404 Not Found'}
        self.bastion(env, self.start_response)
        self.assertEquals(self.status, lookup[code])

    def test_no_xforwarded_for_returns_204(self):
        env = self.create_env('/v1')
        self._expect(env, 204)

    def test_xforwarded_for_present_and_not_whitelisted_returns_404(self):
        env = self.create_env('/v1')
        env['X_FORWARDED_FOR'] = 'taco'
        self._expect(env, 404)

    def test_whitelisted_route_returns_204(self):
        env = self.create_env('/v1/health')
        self._expect(env, 204)

        env['X_FORWARDED_FOR'] = 'taco'
        self._expect(env, 204)

    def test_whitelist_close_match_route_returns_404(self):
        env = self.create_env('/v1/healthy')
        env['X_FORWARDED_FOR'] = 'taco'
        self._expect(env, 404)

    @ddt.data('GET', 'HEAD', 'PUT', 'DELETE', 'POST', 'PATCH')
    def test_whitelist_works_regardless_of_method(self, method):
        env = self.create_env('/v1/health')
        self._expect(env, 204)

        env['X_FORWARDED_FOR'] = 'taco'
        self._expect(env, 204)
