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

from __future__ import division
import base64
import datetime
import logging
from wsgiref import simple_server

import ddt
import fakeredis
from keystoneclient import access
from keystoneclient import exceptions
import mock
import msgpack.exceptions
import simplejson as json
import six

from eom import auth
import tests
from tests.mocks import servicecatalog
from tests import util


LOG = logging.getLogger(__name__)
auth.configure(util.CONF)


def run_server(app, host, port):
    httpd = simple_server.make_server(host, port, app)
    httpd.serve_forever()


# Monkey patch the FakeRedis so we can expire data - even if it does nothing
def fakeredis_pexpireat(self, key, when):
    pass
fakeredis.FakeRedis.pexpireat = fakeredis_pexpireat


def fakeredis_pexpire(self, key, ttl):
    pass
fakeredis.FakeRedis.pexpire = fakeredis_pexpire


def fakeredis_connection():
    return fakeredis.FakeRedis()


def fake_catalog(tenant, token):
    """Generate a fake Service Catalog

    """
    catalog_gen = servicecatalog.ServiceCatalogGenerator(token, tenant)
    catalog = catalog_gen.generate_full_catalog()['access']
    return access.AccessInfoV2(**catalog)


def fake_auth_raise(self, auth_url, tenant_id, token):
    raise exceptions.AuthorizationFailure('mock Keystone error')


class fake_client_object_raise(object):

    def get_raw_token_from_identity_service(self, auth_url, tenant_id, token):
        raise exceptions.AuthorizationFailure(
            'mocking - identity crisis')


class fake_client_object_check_credentials(object):

    def get_raw_token_from_identity_service(self, auth_url, tenant_id, token):
        LOG.debug('URL: {0}'.format(auth_url))
        LOG.debug('Token: {0}'.format(token))
        LOG.debug('Tenant: {0}'.format(tenant_id))

        if token == 'valid_token' and tenant_id == 'valid_projectid':
            catalog_gen = servicecatalog.ServiceCatalogGenerator(
                token, tenant_id)
            catalog = catalog_gen.generate_full_catalog()['access']
            return access.AccessInfoV2(**catalog)
        else:
            if token == 'valid_token':
                raise exceptions.AuthorizationFailure(
                    'mocking - invalid project id')
            elif tenant_id == 'valid_projectid':
                raise exceptions.AuthorizationFailure(
                    'mocking - invalid token')
            else:
                raise exceptions.AuthorizationFailure(
                    'mocking - invalid or missing token or project id')


class fake_access_data(object):

    def __init__(self, result):
        self.result = result

    def will_expire_soon(self):
        return self.result


@ddt.ddt
class TestAuth(util.TestCase):

    def setUp(self):
        super(TestAuth, self).setUp()
        redis_client = fakeredis_connection()
        self.auth = auth.wrap(tests.util.app, redis_client)
        self.test_url = '/v2/vault'
        self.default_max_cache_life = 30

        # config = auth.CONF['eom:auth']
        # self.runtime_url = config['auth_url']
        # config['auth_url'] = 'localhost/v2'

    def tearDown(self):
        super(TestAuth, self).tearDown()
        redis_client = fakeredis_connection()
        redis_client.flushall()

        # config = auth.CONF['eom:auth']
        # config['auth_url'] = self.runtime_url

    def test_get_conf_auth(self):
        config = auth.get_conf()
        self.assertIsNotNone(config)

    def test_get_conf_auth_redis(self):
        auth_config = auth.get_conf()
        redis_config = auth.get_conf(True)
        self.assertIsNotNone(auth_config)
        self.assertIsNotNone(redis_config)
        self.assertNotEqual(auth_config, redis_config)

    def test_cache_key(self):
        value_input = ('1', '2', '3', '4')
        value_output = "(1,2,3,4)"

        test_result = auth._tuple_to_cache_key(value_input)
        self.assertEqual(test_result, value_output)

    def test_blacklist_insertion(self):
        token = 'h0t3l4lph4tang0'
        bttl = 5

        redis_client = fakeredis_connection()

        # The data that will get cached
        packed_data = msgpack.packb(True,
                                    use_bin_type=True,
                                    encoding='utf-8')

        # Redis fails to expire ttl
        with mock.patch(
                'fakeredis.FakeRedis.pexpire') as MockRedisExpire:
            MockRedisExpire.side_effect = Exception(
                'mock redis expire failure')
            redis_error = auth._blacklist_token(redis_client,
                                                token,
                                                bttl)
            self.assertFalse(redis_error)

        # Redis fails to set the data
        with mock.patch(
                'fakeredis.FakeRedis.set') as MockRedisSet:
            MockRedisSet.side_effect = Exception('mock redis set data failed')
            redis_error = auth._blacklist_token(redis_client,
                                                token,
                                                bttl)
            self.assertFalse(redis_error)

        # Happy path
        store_result = auth._blacklist_token(redis_client,
                                             token,
                                             bttl)
        self.assertTrue(store_result)
        stored_data = redis_client.get(token)
        self.assertIsNotNone(stored_data)
        self.assertEqual(stored_data, packed_data)
        stored_data_original = msgpack.unpackb(stored_data, encoding='utf-8')
        self.assertEqual(True, stored_data_original)

    @ddt.data(
        (datetime.datetime.max, 500, True),
        ((datetime.datetime.utcnow() + datetime.timedelta(seconds=50)),
         500, False),
        ((datetime.datetime.utcnow() + datetime.timedelta(seconds=500)),
         50, True)
    )
    @ddt.unpack
    def test_expiration_time(self, time_to_check,
                             slop, slop_makes_younger_time):
        auth_time = auth._get_expiration_time(time_to_check, slop)
        if slop_makes_younger_time:
            self.assertLess(auth_time, time_to_check)
        else:
            self.assertEqual(auth_time, time_to_check)

    def test_store_data_to_cache(self):
        url = 'myfakeurl'
        tenant_id = '0987654321'
        token = 'fedcbaFEDCBA'
        key_data = (tenant_id, token, url)
        key_value = auth._tuple_to_cache_key(key_data)

        redis_client = fakeredis_connection()

        # The data that will get cached
        access_data = fake_catalog(tenant_id, token)
        packed_data = msgpack.packb(access_data,
                                    use_bin_type=True,
                                    encoding='utf-8')

        # Redis fails the expiration time
        with mock.patch(
                'fakeredis.FakeRedis.pexpireat') as MockRedisExpire:
            MockRedisExpire.side_effect = Exception(
                'mock redis expire failure')
            redis_error = auth._send_data_to_cache(redis_client,
                                                   url,
                                                   access_data,
                                                   self.default_max_cache_life)
            self.assertFalse(redis_error)

        # Redis fails to set the data
        with mock.patch(
                'fakeredis.FakeRedis.set') as MockRedisSet:
            MockRedisSet.side_effect = Exception('mock redis set data failed')
            redis_error = auth._send_data_to_cache(redis_client,
                                                   url,
                                                   access_data,
                                                   self.default_max_cache_life)
            self.assertFalse(redis_error)

        # Happy Path
        store_result = auth._send_data_to_cache(redis_client,
                                                url,
                                                access_data,
                                                self.default_max_cache_life)
        self.assertTrue(store_result)
        stored_data = redis_client.get(key_value)
        self.assertIsNotNone(stored_data)
        self.assertEqual(stored_data, packed_data)
        stored_data_original = msgpack.unpackb(stored_data, encoding='utf-8')

        self.assertEqual(stored_data_original, access_data)

    def test_retrieve_cache_data(self):
        url = 'myurl'
        tenant_id = '123456890'
        token = 'ABCDEFabcdef'
        key_data = (tenant_id, token, url)
        key_value = auth._tuple_to_cache_key(key_data)

        data = fake_catalog(tenant_id, token)
        data_packed = msgpack.packb(data, encoding='utf-8', use_bin_type=True)

        redis_client = fakeredis_connection()
        self.assertTrue(redis_client.set(key_value, data_packed))

        # Invalid Cache Error
        # - we use a random url for the cache conflict portion
        invalid_cached_data = auth._retrieve_data_from_cache(redis_client,
                                                             '/random/url',
                                                             tenant_id,
                                                             token)
        self.assertIsNone(invalid_cached_data)

        # Test: Redis Client tosses exception
        def redis_toss_exception(*args, **kwargs):
            raise Exception('mock redis exception')

        redis_exception_result = auth._retrieve_data_from_cache(
            redis_toss_exception, url, tenant_id, token)
        self.assertEqual(redis_exception_result, None)

        # msgpack error
        with mock.patch('eom.auth.__unpacker') as MockMsgPacker:
            MockMsgPacker.side_effect = msgpack.exceptions.UnpackException(
                'mock')
            msgpack_error = auth._retrieve_data_from_cache(redis_client,
                                                           url,
                                                           tenant_id, token)
            self.assertIsNone(msgpack_error)

        # Test: Happy case V2 data
        happy_v2_result = auth._retrieve_data_from_cache(redis_client,
                                                         url,
                                                         tenant_id,
                                                         token)
        self.assertEqual(happy_v2_result, data)

    def test_retrieve_keystone_bad_client_authorization_error(self):
        url = 'myurl'
        tenant_id = '789012345'
        token = 'abcdefABCDEF'
        bttl = 5

        redis_client = fakeredis_connection()

        with mock.patch(
                'keystoneclient.v2_0.client.Client') as MockKeystoneClient:
            MockKeystoneClient.side_effect = exceptions.Unauthorized(
                'Mock - invalid client object')
            keystone_create_error = auth._retrieve_data_from_keystone(
                redis_client,
                url,
                tenant_id,
                token,
                bttl,
                self.default_max_cache_life)
            self.assertIsNone(keystone_create_error)

        with mock.patch(
                'keystoneclient.v2_0.client.Client') as MockKeystoneClient:
            MockKeystoneClient.side_effect = exceptions.AuthorizationFailure(
                'Mock - invalid client object')
            keystone_create_error = auth._retrieve_data_from_keystone(
                redis_client,
                url,
                tenant_id,
                token,
                bttl,
                self.default_max_cache_life)
            self.assertIsNone(keystone_create_error)

    def test_retrieve_keystone_bad_client(self):
        url = 'myurl'
        tenant_id = '789012345'
        token = 'abcdefABCDEF'
        bttl = 5

        redis_client = fakeredis_connection()

        with mock.patch(
                'keystoneclient.v2_0.client.Client') as MockKeystoneClient:
            MockKeystoneClient.side_effect = Exception(
                'Mock - invalid client object')
            keystone_create_error = auth._retrieve_data_from_keystone(
                redis_client,
                url,
                tenant_id,
                token,
                bttl,
                self.default_max_cache_life)
            self.assertIsNone(keystone_create_error)

    def test_retrieve_keystone_bad_identity_access(self):
        url = 'myurl'
        tenant_id = '789012345'
        token = 'abcdefABCDEF'
        bttl = 5

        redis_client = fakeredis_connection()

        with mock.patch(
                'keystoneclient.v2_0.client.Client') as MockKeystoneClient:
            MockKeystoneClient.return_value = fake_client_object_raise()
            # Fail to get a valid Client object
            # Note: Client() uses the requests package to do an auth;
            #   on failure it is the requests module that fails.
            keystone_error = auth._retrieve_data_from_keystone(
                redis_client,
                url,
                tenant_id,
                token,
                bttl,
                self.default_max_cache_life)
            self.assertIsNone(keystone_error)

    def test_retrieve_keystone_check_credentials(self):
        url = 'myurl'
        bttl = 5

        redis_client = fakeredis_connection()

        with mock.patch(
                'keystoneclient.v2_0.client.Client') as MockKeystoneClient:
            MockKeystoneClient.return_value = (
                fake_client_object_check_credentials())

            credential_sets = [
                {
                    'projectid': 'valid_projectid',
                    'authtoken': 'valid_token',
                    'is_none': False
                },
                {
                    'projectid': None,
                    'authtoken': 'valid_token',
                    'is_none': True
                },
                {
                    'projectid': 'valid_projectid',
                    'authtoken': None,
                    'is_none': True
                },
                {
                    'projectid': None,
                    'authtoken': None,
                    'is_none': True
                },
                {
                    'projectid': 'invalid_projectid',
                    'authtoken': 'valid_token',
                    'is_none': True
                },
                {
                    'projectid': 'valid_projectid',
                    'authtoken': 'invalid_token',
                    'is_none': True
                },
                {
                    'projectid': 'invalid_projectid',
                    'authtoken': 'invalid_token',
                    'is_none': True
                }
            ]

            for creds in credential_sets:
                keystone_error = auth._retrieve_data_from_keystone(
                    redis_client,
                    url,
                    creds['projectid'],
                    creds['authtoken'],
                    bttl,
                    self.default_max_cache_life)
                if creds['is_none']:
                    self.assertIsNone(keystone_error)
                else:
                    self.assertIsNotNone(keystone_error)

    def test_get_access_info(self):
        url = 'myurl'
        tenant_id = '172839405'
        token = 'AaBbCcDdEeFf'
        bttl = 5

        redis_client = fakeredis_connection()

        with mock.patch(
                'eom.auth._retrieve_data_from_cache') as MockRetrieveCacheData:

            with mock.patch(
                    'eom.auth._retrieve_data_from_keystone') as (
                    MockRetrieveKeystoneData):

                # No data in cache, keystone can't retrieve
                MockRetrieveCacheData.return_value = None
                MockRetrieveKeystoneData.return_value = None
                access_info = auth._get_access_info(
                    redis_client,
                    url,
                    tenant_id,
                    token,
                    bttl,
                    self.default_max_cache_life)
                self.assertIsNone(access_info)

                # Data in cache, not expired
                MockRetrieveCacheData.return_value = fake_access_data(False)
                MockRetrieveKeystoneData.return_value = None
                access_info = auth._get_access_info(
                    redis_client,
                    url,
                    tenant_id,
                    token,
                    bttl,
                    self.default_max_cache_life)
                self.assertEqual(access_info,
                                 MockRetrieveCacheData.return_value)

                # No data in cache, keystone retrieves
                MockRetrieveCacheData.return_value = None
                MockRetrieveKeystoneData.return_value = fake_access_data(False)
                access_info = auth._get_access_info(
                    redis_client,
                    url,
                    tenant_id,
                    token,
                    bttl,
                    self.default_max_cache_life)
                self.assertEqual(access_info,
                                 MockRetrieveKeystoneData.return_value)

                # Expired data in cache, keystone can't retrieve
                MockRetrieveCacheData.return_value = fake_access_data(True)
                MockRetrieveKeystoneData.return_value = None
                access_info = auth._get_access_info(
                    redis_client,
                    url,
                    tenant_id,
                    token,
                    bttl,
                    self.default_max_cache_life)
                self.assertNotEqual(access_info,
                                    MockRetrieveCacheData.return_value)
                self.assertIsNone(access_info)

                # No data in cache, keystone returns expired data
                MockRetrieveCacheData.return_value = None
                MockRetrieveKeystoneData.return_value = fake_access_data(True)
                access_info = auth._get_access_info(
                    redis_client,
                    url,
                    tenant_id,
                    token,
                    bttl,
                    self.default_max_cache_life)
                self.assertNotEqual(access_info,
                                    MockRetrieveKeystoneData.return_value)
                self.assertIsNone(access_info)

                # Expired data in cache, keystone returns expired data
                MockRetrieveCacheData.return_value = fake_access_data(True)
                MockRetrieveKeystoneData.return_value = fake_access_data(True)
                access_info = auth._get_access_info(
                    redis_client,
                    url,
                    tenant_id,
                    token,
                    bttl,
                    self.default_max_cache_life)
                self.assertNotEqual(access_info,
                                    MockRetrieveCacheData.return_value)
                self.assertNotEqual(access_info,
                                    MockRetrieveKeystoneData.return_value)
                self.assertIsNone(access_info)

    def test_validate_client_exception(self):
        url = 'myurl'
        tenant_id = '172839405'
        token = 'AaBbCcDdEeFf'

        redis_client = fakeredis_connection()
        bttl = 5

        # Throw an exception - anything, just needs to throw
        with mock.patch(
                'eom.auth._get_access_info') as MockGetAccessInfo:

            env_exception_thrown = {}
            MockGetAccessInfo.side_effect = Exception(
                'mock - just blowing it up')
            result = auth._validate_client(redis_client,
                                           url,
                                           tenant_id,
                                           token,
                                           env_exception_thrown,
                                           bttl,
                                           self.default_max_cache_life)
            self.assertFalse(result)

    def test_validate_client_invalid_data(self):
        url = 'myurl'
        tenant_id = '172839405'
        token = 'AaBbCcDdEeFf'

        redis_client = fakeredis_connection()
        bttl = 5

        # No data is returned
        with mock.patch(
                'eom.auth._get_access_info') as MockGetAccessInfo:

            env_no_data = {}
            MockGetAccessInfo.return_value = None
            result = auth._validate_client(redis_client,
                                           url,
                                           tenant_id,
                                           token,
                                           env_no_data,
                                           bttl,
                                           self.default_max_cache_life)
            self.assertFalse(result)

    def test_validate_client_token_blacklisted(self):
        url = 'myurl'
        tenant_id = '504938271'
        token = '1nd14r0m303ch0n0v3mb3r3ch0'

        redis_client = fakeredis_connection()
        bttl = 5

        # We have data
        with mock.patch(
                'eom.auth._is_token_blacklisted') as MockBlacklist:

            env_result = {}
            MockBlacklist.return_value = True
            result = auth._validate_client(redis_client,
                                           url,
                                           tenant_id,
                                           token,
                                           env_result,
                                           bttl,
                                           self.default_max_cache_life)
            self.assertFalse(result)

    def test_validate_client_b64decode_error(self):
        url = 'myurl'
        tenant_id = '172839405'
        token = 'AaBbCcDdEeFf'

        redis_client = fakeredis_connection()
        bttl = 5

        # The data that will get cached
        access_info = fake_catalog(tenant_id, token)

        # We have data
        with mock.patch(
                'eom.auth._get_access_info') as MockGetAccessInfo:
            with mock.patch(
                    'eom.auth._is_token_blacklisted') as MockBlacklist:
                with mock.patch(
                        'base64.b64decode') as MockB64Decode:

                    MockB64Decode.side_effect = Exception(
                        'mock b64decode error')

                    env_result = {}
                    MockBlacklist.return_value = False
                    MockGetAccessInfo.return_value = access_info
                    result = auth._validate_client(redis_client,
                                                   url,
                                                   tenant_id,
                                                   token,
                                                   env_result,
                                                   bttl,
                                                   self.default_max_cache_life)
                    self.assertFalse(result)

    def test_validate_client_valid_data(self):
        url = 'myurl'
        tenant_id = '172839405'
        token = 'AaBbCcDdEeFf'

        redis_client = fakeredis_connection()
        bttl = 5

        # The data that will get cached
        access_info = fake_catalog(tenant_id, token)

        # Encode a version of the data for verification tests later
        data = access_info.service_catalog.catalog
        json_data = json.dumps(data)
        u_json_data = json_data
        if six.PY2:
            if isinstance(u_json_data, bytes):
                u_json_data = json_data.decode('utf-8')
        access_data_utf8 = u_json_data.encode(encoding='utf-8',
                                              errors='strict')
        access_data_b64 = base64.b64encode(access_data_utf8)

        # We have data
        with mock.patch(
                'eom.auth._get_access_info') as MockGetAccessInfo:
            with mock.patch(
                    'eom.auth._is_token_blacklisted') as MockBlacklist:

                env_result = {}
                MockBlacklist.return_value = False
                MockGetAccessInfo.return_value = access_info
                result = auth._validate_client(redis_client,
                                               url,
                                               tenant_id,
                                               token,
                                               env_result,
                                               bttl,
                                               self.default_max_cache_life)
                self.assertTrue(result)
                self.assertEqual(env_result['HTTP_X_IDENTITY_STATUS'],
                                 'Confirmed')
                self.assertEqual(env_result['HTTP_X_USER_ID'],
                                 MockGetAccessInfo.return_value.user_id)
                self.assertEqual(env_result['HTTP_X_USER_NAME'],
                                 MockGetAccessInfo.return_value.username)
                self.assertEqual(env_result['HTTP_X_USER_DOMAIN_ID'],
                                 MockGetAccessInfo.return_value.user_domain_id)
                self.assertEqual(env_result['HTTP_X_USER_DOMAIN_NAME'],
                                 MockGetAccessInfo.return_value.
                                 user_domain_name)
                role_names = MockGetAccessInfo.return_value.role_names
                self.assertEqual(env_result['HTTP_X_ROLES'],
                                 ','.join(role for role in role_names))
                self.assertEqual(env_result['HTTP_X_SERVICE_CATALOG'],
                                 access_data_b64)
                env_service_catalog_utf8 = base64.b64decode(
                    env_result['HTTP_X_SERVICE_CATALOG'])
                self.assertEqual(env_service_catalog_utf8, access_data_utf8)
                env_service_catalog = json.loads(env_service_catalog_utf8)
                self.assertEqual(env_service_catalog, data)

                self.assertTrue(MockGetAccessInfo.return_value.project_scoped)
                self.assertEqual(env_result['HTTP_X_PROJECT_ID'], tenant_id)
                self.assertEqual(env_result['HTTP_X_PROJECT_ID'],
                                 MockGetAccessInfo.return_value.project_id)
                self.assertEqual(env_result['HTTP_X_PROJECT_NAME'],
                                 MockGetAccessInfo.return_value.project_name)

                if MockGetAccessInfo.return_value.domain_scoped:
                    self.assertEqual(env_result['HTTP_X_DOMAIN_ID'],
                                     MockGetAccessInfo.return_value.domain_id)
                    self.assertEqual(env_result['HTTP_X_DOMAIN_NAME'],
                                     MockGetAccessInfo.return_value.
                                     domain_name)
                else:
                    self.assertTrue('HTTP_X_DOMAIN_ID' not in
                                    env_result.keys())
                    self.assertTrue('HTTP_X_DOMAIN_NAME' not in
                                    env_result.keys())

                if MockGetAccessInfo.return_value.project_scoped and (
                        MockGetAccessInfo.return_value.domain_scoped):

                    self.assertEqual(env_result['HTTP_X_PROJECT_DOMAIN_ID'],
                                     MockGetAccessInfo.return_value.
                                     project_domain_id)
                    self.assertEqual(env_result['HTTP_X_PROJECT_DOMAIN_NAME'],
                                     MockGetAccessInfo.return_value.
                                     project_domain_name)
                else:
                    self.assertTrue('HTTP_X_PROJECT_DOMAIN_ID' not in
                                    env_result.keys())
                    self.assertTrue('HTTP_X_PROJECT_DOMAIN_NAME' not in
                                    env_result.keys())

    """
    def check_credentials(self, projectid, token, result):
        env = self.create_env(self.test_url,
                              project_id=projectid,
                              auth_token=token)
        self.auth(env, self.start_response)
        self.assertEqual(self.status, result)
    """

    def test_eom_auth_wrap(self):

        with mock.patch(
                'eom.auth._validate_client') as MockValidateClient:

            # Create a LookupError or KeyError when the X-Auth-Token
            # Header is not located
            env_no_token = {
                'HTTP_X_PROJECT_ID': 'valid_projectid'
            }
            self.auth(env_no_token, self.start_response)
            self.assertEqual(self.status, '412 Precondition Failed')

            # Create a LookupError or KeyError when the X-Project-ID
            # Header is not located
            env_no_projectid = {
                'HTTP_X_AUTH_TOKEN': 'valid_auth_token'
            }
            self.auth(env_no_projectid, self.start_response)
            self.assertEqual(self.status, '412 Precondition Failed')

            # Valid Headers from here on out
            env_valid = {}
            env_valid.update(env_no_token)
            env_valid.update(env_no_projectid)

            # Assume the client fails validation
            MockValidateClient.return_value = False
            self.auth(env_valid, self.start_response)
            self.assertEqual(self.status, '401 Unauthorized')

            # Client passes validation
            MockValidateClient.return_value = True
            self.auth(env_valid, self.start_response)
            self.assertEqual(self.status, '204 No Content')
