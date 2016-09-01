# Copyright (c) 2014 Rackspace, Inc.
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

import base64
import datetime
import functools
import hashlib

from keystoneclient import access
from keystoneclient import exceptions
from keystoneclient.v2_0 import client as keystonev2_client
import msgpack
from oslo_config import cfg
import redis
from redis import connection
import requests
import simplejson as json
import six

from eom.utils import log as logging

MAX_CACHE_LIFE_DEFAULT = int((datetime.datetime.max -
                              datetime.datetime.utcnow()).total_seconds() - 30)

AUTH_GROUP_NAME = 'eom:auth'
AUTH_OPTIONS = [
    cfg.StrOpt(
        'auth_url',
        help='Identity url to authenticate tokens.'
    ),
    cfg.BoolOpt(
        'alternate_validation',
        default=False,
        help=(
            'Validate tokens using a less expensive call to keystone. '
            'The service catalog is omitted and cannot be forwarded when '
            'this option is set to True.'
        )
    ),
    cfg.IntOpt(
        'blacklist_ttl',
        help='Time to live in milliseconds for tokens marked as unauthorized.'
    ),
    cfg.IntOpt(
        'max_cache_life',
        help='Time to live in seconds for valid tokens.',
        # default value is the maximum number of seconds
        # that the datetime module can manage, with a buffer
        # of 30 seconds so we won't brush up against the end
        # or overflow when adding to utcnow() later on
        default=MAX_CACHE_LIFE_DEFAULT
    ),
    cfg.IntOpt(
        'retry_after',
        default=60,
        help=(
            'seconds to wait before retrying the request '
            'again upon getting (503 Service Unavailable) error.'
        )
    )
]

REDIS_GROUP_NAME = 'eom:auth_redis'
REDIS_OPTIONS = [
    cfg.StrOpt('host'),
    cfg.StrOpt('port'),
    cfg.IntOpt('redis_db', default=0),
    cfg.StrOpt('password', default=None),
    cfg.BoolOpt('ssl_enable', default=False),
    cfg.StrOpt('ssl_keyfile', default=None),
    cfg.StrOpt('ssl_certfile', default=None),
    cfg.StrOpt('ssl_cert_reqs', default=None),
    cfg.StrOpt('ssl_ca_certs', default=None),
]


class InvalidKeystoneClient(Exception):
    pass


class InvalidAccessInformation(Exception):
    pass


class UnknownAuthenticationDataVersion(Exception):
    pass


class Auth(object):
    """Authentication middleware that uses OpenStack Keystone APIs."""

    def __init__(self, app, conf):
        self.app = app
        self._redis_client = None

        conf.register_opts(AUTH_OPTIONS, group=AUTH_GROUP_NAME)
        conf.register_opts(REDIS_OPTIONS, group=REDIS_GROUP_NAME)

        logging.register(conf, AUTH_GROUP_NAME)
        logging.setup(conf, AUTH_GROUP_NAME)

        self.logger = logging.getLogger(__name__)

        self._auth_conf = conf[AUTH_GROUP_NAME]
        self._redis_conf = conf[REDIS_GROUP_NAME]

        self.packer = msgpack.Packer(encoding='utf-8', use_bin_type=True)
        self.unpacker = functools.partial(msgpack.unpackb, encoding='utf-8')

    @property
    def redis_client(self):
        """Get a Redis Client connection from the pool

        uses the eom:auth_redis settings
        """

        if self._redis_conf['ssl_enable']:
            pool = redis.ConnectionPool(
                host=self._redis_conf['host'],
                port=self._redis_conf['port'],
                db=self._redis_conf['redis_db'],
                password=self._redis_conf['password'],
                ssl_keyfile=self._redis_conf['ssl_keyfile'],
                ssl_certfile=self._redis_conf['ssl_certfile'],
                ssl_cert_reqs=self._redis_conf['ssl_cert_reqs'],
                ssl_ca_certs=self._redis_conf['ssl_ca_certs'],
                connection_class=connection.SSLConnection
            )
        else:
            pool = redis.ConnectionPool(
                host=self._redis_conf['host'],
                port=self._redis_conf['port'],
                password=self._redis_conf['password'],
                db=self._redis_conf['redis_db']
            )

        return redis.Redis(connection_pool=pool)

    @staticmethod
    def _tuple_to_cache_key(t):
        """Convert a tuple to a cache key."""
        key_data = '(%(s_data)s)' % {
            's_data': ','.join(t)
        }
        if six.PY3:
            key_data = key_data.encode('utf-8')

        key = hashlib.sha1()
        key.update(key_data)
        return key.hexdigest()

    @staticmethod
    def _blacklist_cache_key(t):
        """Convert token to a cache key for blacklists"""
        key_data = 'blacklist%(s_data)s' % {
            's_data': t
        }
        if six.PY3:
            key_data = key_data.encode('utf-8')

        key = hashlib.sha1()
        key.update(key_data)
        return key.hexdigest()

    def _blacklist_token(self, token):
        """Stores the token to the blacklist data in the cache

        :param token: auth_token for the user

        :returns: True on success, otherwise False
        """
        try:
            cache_data = self.packer.pack(True)
            cache_key = self._blacklist_cache_key(token)

            self.redis_client.set(cache_key, cache_data)
            self.redis_client.pexpire(
                cache_key,
                self._auth_conf['blacklist_ttl']
            )
            return True

        except Exception as ex:
            msg = 'Failed to cache the data - Exception: {0}'.format(str(ex))
            self.logger.error(msg)
            return False

    def _is_token_blacklisted(self, token):
        """Determines if the token is in the cached blacklist data

        :param token: auth_token for the user

        :returns: True on success, otherwise False
        """
        cached_data = None
        cached_key = None
        try:
            cached_key = self._blacklist_cache_key(token)

            cached_data = self.redis_client.get(cached_key)
        except Exception as ex:
            self.logger.debug(
                (
                    'Failed to retrieve data to cache for key {0} '
                    'Exception: {1}'
                ).format(cached_key, str(ex))
            )
            cached_data = None

        if cached_data is None:
            return False
        else:
            return True

    @staticmethod
    def _get_expiration_time(service_catalog_expiration, max_cache_life):
        """Determines the cache expiration time

        :param service_catalog_expiration: DateTime object containing the
               expiration time from the service catalog
        :param max_cache_life: time in seconds for the maximum time a cache
            entry should remain in the cache of valid data

        :returns: DateTime object with the time that the cache should be
                  expired at. This is the nearest time of either the
                  expiration of the service catalog or the combination of
                  the current time and the max_cache_life parameter
        """
        class UtcTzInfo(datetime.tzinfo):

            def utcoffset(self, dt):
                return datetime.timedelta(0)

            def tzname(self, dt):
                return 'UTC'

            def dst(self, dt):
                return datetime.timedelta(0)

        # calculate the time based on the max_cache_life
        now = datetime.datetime.utcnow()
        max_expire_time = now + datetime.timedelta(seconds=max_cache_life)

        if service_catalog_expiration.tzinfo is not None:  # pragma: no cover
            max_expire_time = max_expire_time.replace(tzinfo=UtcTzInfo())

        # return the nearest time to now
        return min(service_catalog_expiration, max_expire_time)

    def _send_data_to_cache(self, access_info, max_cache_life):
        """Stores the authentication data to cache

        :param access_info: keystoneclient.access.AccessInfo containing
            the auth data
        :param max_cache_life: time in seconds a cache entry should remain in
            the cache of valid data

        :returns: True on success, otherwise False
        """
        try:
            # serialize cache data
            cache_data = self.packer.pack(access_info)

            tenant = access_info.tenant_id
            token = access_info.auth_token

            # Build the cache key and store the value
            cache_key = self._tuple_to_cache_key(
                (tenant, token, self._auth_conf['auth_url'])
            )
            self.redis_client.set(cache_key, cache_data)

            # Get the cache expiration time
            cache_expiration_time = self._get_expiration_time(
                access_info.expires,
                max_cache_life
            )

            self.redis_client.pexpireat(cache_key, cache_expiration_time)

            return True

        except Exception as ex:
            msg = 'Failed to cache the data - Exception: {0}'.format(str(ex))
            self.logger.error(msg)
            return False

    def _retrieve_data_from_cache(self, tenant, token):
        """Retrieve the authentication data from cache

        :param tenant: tenant id of the user
        :param token: auth_token for the user

        :returns: a keystoneclient.access.AccessInfo on success or None
        """
        cached_data = None
        cache_key = None
        try:
            # Try to get the data from the cache
            cache_key_tuple = (tenant, token, self._auth_conf['auth_url'])
            cache_key = self._tuple_to_cache_key(cache_key_tuple)
            cached_data = self.redis_client.get(cache_key)
        except Exception as ex:
            self.logger.debug(
                (
                    'Failed to retrieve data to cache for key {0}'
                    'Exception: {1}'
                ).format(cache_key, str(ex))
            )
            return None

        if cached_data is not None:
            # So 'data' can be used in the exception handler...
            data = None

            try:
                data = self.unpacker(cached_data)
                return access.AccessInfoV2(data)

            except Exception as ex:
                # The cached object didn't match what we expected
                msg = (
                    'Stored data does not contain any credentials - '
                    'Exception: {0}; Data: {1}'
                ).format(str(ex), data)
                self.logger.error(msg)
                return None
        else:
            self.logger.debug('No data in cache for key {0}'.format(cache_key))
            # It wasn't cached
            return None

    def _retrieve_data_from_keystone(self, tenant, token, max_cache_life):
        """Retrieve the authentication data from OpenStack Keystone

        :param tenant: tenant id of user data to retrieve
        :param token: auth_token for the tenant_id
        :param max_cache_life: time in seconds for the maximum time a cache
            entry should remain in the cache of valid data

        :returns: a keystoneclient.access.AccessInfo on success or
            None on error
        """
        try:
            # Try to authenticate the user and get the user information using
            # only the data provided, no special administrative tokens
            # required. When using the alternative validation method, the
            # service catalog identity does not return a service catalog for
            # valid tokens.

            if self._auth_conf.alternate_validation is True:
                _url = self._auth_conf['auth_url'].rstrip('/') + '/tokens'
                validation_url = _url + '/{0}'.format(token)
                headers = {
                    'Accept': 'application/json',
                    'X-Auth-Token': token
                }
                resp = requests.get(validation_url, headers=headers)
                if resp.status_code >= 400:
                    self.logger.debug(
                        'Request returned failure status: {0}'.format(
                            resp.status_code))
                    raise exceptions.from_response(resp, 'GET', _url)

                try:
                    resp_data = resp.json()['access']
                except (KeyError, ValueError):
                    raise exceptions.InvalidResponse(response=resp)

                access_info = access.AccessInfoV2(**resp_data)
            else:
                keystone = keystonev2_client.Client(
                    tenant_id=tenant,
                    token=token,
                    auth_url=self._auth_conf['auth_url']
                )
                access_info = keystone.get_raw_token_from_identity_service(
                    auth_url=self._auth_conf['auth_url'],
                    tenant_id=tenant,
                    token=token
                )

            # cache the data so it is easier to access next time
            self._send_data_to_cache(access_info, max_cache_life)

            return access_info

        except (
            exceptions.AuthorizationFailure,
            exceptions.Unauthorized
        ) as ex:
            # re-raise 413 here and later on respond with 503
            if 'HTTP 413' in str(ex):
                raise exceptions.RequestEntityTooLarge(
                    method='POST',
                    url=self._auth_conf['auth_url'],
                    http_status=413
                )
            # Provided data was invalid and authorization failed
            msg = 'Failed to authenticate against {0} - {1}'.format(
                self._auth_conf['auth_url'],
                str(ex)
            )
            self.logger.debug(msg)

            # Blacklist the token
            self._blacklist_token(token)
            return None
        except exceptions.RequestEntityTooLarge:
            self.logger.debug(
                'Request entity too large error from authentication server.'
            )
            raise
        except Exception as ex:
            # Provided data was invalid or something else went wrong
            msg = 'Failed to authenticate against {0} - {1}'.format(
                self._auth_conf['auth_url'],
                str(ex)
            )
            self.logger.debug(msg)

            return None

    def _get_access_info(self, tenant, token, max_cache_life):
        """Retrieve the access information regarding the specified user

        :param tenant: tenant id of user data to retrieve
        :param token: auth_token for the tenant_id
        :param max_cache_life: time in seconds for the maximum time a cache
            entry should remain in the cache of valid data

        :returns: keystoneclient.access.AccessInfo for the user on success
                  None on error
        """

        # Check cache
        access_info = self._retrieve_data_from_cache(tenant, token)

        if access_info is not None:
            if access_info.will_expire_soon():
                self.logger.info('Token has expired')
                del access_info
                access_info = None

        # Check if we failed to get it from the cache and
        # retrieve from keystone instead
        if access_info is None:
            self.logger.debug(
                'Failed to retrieve token from cache. Trying Keystone')
            access_info = self._retrieve_data_from_keystone(
                tenant,
                token,
                max_cache_life
            )
        else:
            self.logger.debug('Retrieved token from cache.')

        # Validate we have an access object and
        # Make sure it's not already expired
        if access_info is not None:
            if access_info.will_expire_soon():
                self.logger.info('Token has expired')
                del access_info
                access_info = None

        # Return the access data
        return access_info

    def _validate_client(self, tenant, token, env, max_cache_life):
        """Update the env with the access information for the user

        :param tenant: tenant id of user data to retrieve
        :param token: auth_token for the tenant_id
        :param env: environment variable dictionary for the client connection
        :param max_cache_life: time in seconds for the maximum time a cache
        entry should remain in the cache of valid data

        :returns: True on success, otherwise False
        """

        def _management_url(*args, **kwargs):
            return self._auth_conf['auth_url']

        def patch_management_url():
            from keystoneclient import service_catalog
            service_catalog.ServiceCatalog.url_for = _management_url

        patch_management_url()

        try:
            if self._is_token_blacklisted(token):
                return False

            # Try to get the client's access information
            access_info = self._get_access_info(
                tenant,
                token,
                max_cache_life
            )

            if access_info is None:
                self.logger.debug(
                    'Unable to get Access info for {0}'.format(tenant))
                return False

            # provided data was valid,
            # insert the information into the environment
            env['HTTP_X_IDENTITY_STATUS'] = 'Confirmed'

            env['HTTP_X_USER_ID'] = access_info.user_id
            env['HTTP_X_USER_NAME'] = access_info.username
            env['HTTP_X_USER_DOMAIN_ID'] = access_info.user_domain_id
            env['HTTP_X_USER_DOMAIN_NAME'] = access_info.user_domain_name
            env['HTTP_X_ROLES'] = ','.join(
                role for role in access_info.role_names
            )
            if access_info.has_service_catalog():
                # Convert the service catalog to JSON
                service_catalog_data = json.dumps(
                    access_info.service_catalog.catalog)

                # convert service catalog to unicode to try to help
                # prevent encode/decode errors under python2
                if six.PY2:  # pragma: no cover
                    u_service_catalog_data = (
                        service_catalog_data.decode('utf-8')
                    )
                else:  # pragma: no cover
                    u_service_catalog_data = service_catalog_data

                # Convert the JSON string data to strict UTF-8
                utf8_data = u_service_catalog_data.encode(
                    encoding='utf-8', errors='strict')

                # Store it as Base64 for transport
                env['HTTP_X_SERVICE_CATALOG'] = base64.b64encode(utf8_data)

                try:
                    decode_check = base64.b64decode(
                        env['HTTP_X_SERVICE_CATALOG']
                    )

                except Exception:
                    self.logger.debug('Failed to decode the data properly')
                    return False

                if decode_check != utf8_data:
                    self.logger.debug(
                        'Decode Check: decoded data does not match '
                        'encoded data'
                    )
                    return False

            # Project Scoped V3 or Tenant Scoped v2
            # This can be assumed since we validated using X_PROJECT_ID
            # and therefore have at least a v2 Tenant Scoped Token
            if access_info.project_scoped:
                env['HTTP_X_PROJECT_ID'] = access_info.project_id
                env['HTTP_X_PROJECT_NAME'] = access_info.project_name

            # Domain-Scoped V3
            if access_info.domain_scoped:
                env['HTTP_X_DOMAIN_ID'] = access_info.domain_id
                env['HTTP_X_DOMAIN_NAME'] = access_info.domain_name

            # Project-Scoped V3 - X_PROJECT_NAME is only unique
            # within the domain
            if access_info.project_scoped and access_info.domain_scoped:
                env['HTTP_X_PROJECT_DOMAIN_ID'] = access_info.project_domain_id
                env['HTTP_X_PROJECT_DOMAIN_NAME'] = (
                    access_info.project_domain_name
                )

            return True

        except exceptions.RequestEntityTooLarge:
            self.logger.debug(
                'Request entity too large error from authentication server.'
            )
            raise

        except Exception as ex:
            msg = (
                'Error while trying to authenticate against {0} - {1}'
            ).format(
                self._auth_conf['auth_url'],
                str(ex)
            )
            self.logger.debug(msg)
            return False

    @staticmethod
    def _http_precondition_failed(start_response):
        """Responds with HTTP 412."""
        start_response('412 Precondition Failed', [('Content-Length', '0')])
        return []

    @staticmethod
    def _http_unauthorized(start_response):
        """Responds with HTTP 401."""
        start_response('401 Unauthorized', [('Content-Length', '0')])
        return []

    def _http_service_unavailable(self, start_response, delta):
        """Responds with HTTP 503."""
        response_headers = [
            ('Content-Length', '0'),
            ('Retry-After', delta or str(self._auth_conf.retry_after))
        ]
        start_response('503 Service Unavailable', response_headers)
        return []

    def __call__(self, env, start_response):
        """Wrap a WSGI app with Authentication middleware.

        :returns: a new  WSGI app that wraps the original
        """

        # blacklist_ttl = self._auth_conf['blacklist_ttl']
        max_cache_life = self._auth_conf['max_cache_life']

        self.logger.debug('Auth URL: {0:}'.format(self._auth_conf['auth_url']))

        try:
            token = env['HTTP_X_AUTH_TOKEN']
            tenant = env['HTTP_X_PROJECT_ID']

            # validate the client and fill out the environment it's valid
            if self._validate_client(
                tenant,
                token,
                env,
                max_cache_life
            ):
                self.logger.debug('Auth Token validated.')
                return self.app(env, start_response)

            else:
                # Validation failed for some reason, just error out as a 401
                self.logger.error('Auth Token validation failed.')
                return self._http_unauthorized(start_response)
        except (KeyError, LookupError):
            # Header failure, error out with 412
            self.logger.error('Missing required headers.')
            return self._http_precondition_failed(start_response)

        except exceptions.RequestEntityTooLarge as exc:
            self.logger.error(
                'Request too large, client should retry after {0}.'.format(
                    exc.retry_after
                )
            )
            return self._http_service_unavailable(
                start_response, exc.retry_after
            )
