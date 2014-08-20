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
# WITHOUT WARRANTIES OR ONDITIONS OF ANY KIND, either express or
# implied.
#
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import re
import types

from oslo.config import cfg
import simplejson as json
import redis

LOG = logging.getLogger(__name__)
CONF = cfg.CONF

OPT_GROUP_NAME = 'eom:auth'
OPTION_AUTH_URL = 'auth_url'
OPTION_REGION = 'region'

CONF.register_opt(cfg.StrOpt(OPTION_AUTH_URL), group=OPT_GROUP_NAME)
CONF.register_opt(cfg.StrOpt(OPTION_REGION), group=OPT_GROUP_NAME)

REDIS_GROUP_NAME = 'eom:auth_redis'
REDIS_OPTIONS = [
    cfg.StrOpt('host'),
    cfg.StrOpt('port'),
]

CONF.register_opts(REDIS_OPTIONS, group=REDIS_GROUP_NAME)

class InvalidKeystoneClient(Exception):
    pass


class InvalidAccessInformation(Exception):
    pass


class UnknownAuthenticationDataVersion(Exception):
    pass


def _tuple_to_cache_key(t):
    """Convert a tuple to a cache key
    """
    key = '(%(s_data))' % {
        's_data' : ','.join(t)
    }
    return key


def _send_data_to_cache(redis_client, url, access_info):
    """Stores the authentication data to memcache

    :param redis_client: redis.Redis object connected to the redis cache
    :param url: URL used for authentication
    :param access_info: keystoneclient.access.AccessInfo containing
        the auth data

    :returns: True on success, otherwise False
    """
    try:
        # Convert the access_info dictionary into a string for storage
        data = {}
        data.update(access_info)
        cache_data = json.dumps(data)

        tenant = access_info.tenant_id
        token = access_info.token

        # Guild the cache key and store the value
        # Use the token's expiration time for the cache expiration
        cache_key = _tuple_to_cache_key((tenant, token, url))
        redis_client.set(cache_key, cache_data)
        redis_client.pexpire(cache_key, access_info.expires)
        
        return True

    except Exception:
        return False


def _retrieve_data_from_cache(redis_client, url, tenant, token):
    """Retrieve the authentication data from memcache

    :param redis_client: redis.Redis object connected to the redis cache
    :param url: URL used for authentication
    :param tenant: tenant id of the user
    :param token: auth_token for the user

    :returns: a keystoneclient.access.AccessInfo on success or None
    """
    try:
        # Try to get the data from the cache
        cache_key_tuple = (tenant, token, url)
        cache_key = _tuple_to_cache_key((tenant, token, url))
        cached_data = redis_client.get(cache_key)

        if cached_data is not None:
            try:
                # Convert the stored dictionary as a string back to a
                # dictionary
                data = json.loads(cached_data)

                # Check the data's version field to determine which version of
                # the access information object we should instantiate
                if data['version'] == 'v2.0':
                    # Keystone v2 data
                    from keystoneclient.access import AccessInfoV2
                    return AccessInfoV2(data)

                elif data['version'] == 'v3.0':
                    # Keystone V3 data
                    from keystoneclient.access import AccessInfoV3
                    return AccessInfoV3(data)

                else:
                    # Don't know what it is.
                    # Did keystone release a new version?
                    msg = _('Access Version (%(s_version)) Unknown.') % {
                        's_version': data['version']
                    }
                    LOG.error(msg)
                    return None

            except Exception:
                # The cached object didn't match what we expected
                msg = _('Authentication Data does not contain a version.')
                LOG.error(msg)
                return None

        else:
            # It wasn't cached
            return None

    except Exception:
        # Error while accessing redis
        return None

_
def _retrieve_data_from_keystone(redis_client, url, tenant, token):
    """Retrieve the authentication data from OpenStack Keystone

    :param redis_client: redis.Redis object connected to the redis cache
    :param url: Keystone Identity URL to authenticate against
    :param tenant: tenant id of user data to retrieve
    :param token: auth_token for the tenant_id

    :returns: a keystoneclient.access.AccessInfo on success or None on error
    """
    from keystoneclient.client import Client 
    import keystoneclient.exceptions
    try:
        keystone = Client(tenant_id=tenant, token=token, auth_url=url)

    except Exception as ex:
        msg = _('Failed to retrieve Keystone client - %(s_except)') % {
            's_except': str(ex)
        }
        LOG.debug(msg)
        return None

    # Now try to authenticate the user and get the user information using
    # only the data provided, no special administrative tokens required
    try:
        access_info = keystone.get_raw_token_from_identity_service(
            auth_url=url, tenant_id=tenant, token=token)

        # cache the data so it is easier to access next time
        _send_data_to_cache(redis_client, url, access_info)

        return access_info

    except keystoneClient.exceptions.AuthorizationFailure as ex:
        # Provided data was invalid
        msg = _('Failed to authenticate against %(s_url) - %(s_except)') % {
            's_url' : auth_url,
            's_except' : str(ex)
        }
        LOG.debug( msg )
        return None


def _get_access_info(redis_client, url, tenant, token):
    """Retrieve the access information regarding the specified user

    :param redis_client: redis.Redis object connected to the redis cache
    :param url: Keystone Identity URL to authenticate against
    :param tenant: tenant id of user data to retrieve
    :param token: auth_token for the tenant_id

    :returns: keystoneclient.access.AccessInfo for the user on success
              None on error
    """

    # Check cache
    access_info =  _retrieve_data_from_cache(redis_client,
                                            url,
                                            tenant,
                                            token)

    # Check if we failed to get it from the cache and
    # retrieve from keystone instead
    if access_info is None:
        access_info = _retrieve_data_from_keystone(redis_client,
                                                  url,
                                                  tenant,
                                                  token)

    # Validate we have an access object and 
    # Make sure it's not already expired
    if access_info is not None:
        if access_info.will_expire_soon():
            del access_info
            access_info = None

    # Return the access data
    return access_info


def _validate_client(redis_client, url, tenant, token, env, region):
    """Retrieve the access information for the user and update
    env with the appropriate values

    :param redis_client: redis.Redis object connected to the redis cache
    :param url: Keystone Identity URL to authenticate against
    :param tenant: tenant id of user data to retrieve
    :param token: auth_token for the tenant_id
    :param env: environment variable dictionary for the client connection

    :returns: True on success, otherwise False
    """
    try:
        # Try to get the client's access infomration
        access_info = _get_access_info(redis_client, url, tenant, token, env)
        if access_info is None:
            return False

        # provided data was valid, insert the information into the environment
        env['HTTP_X_IDENTITY_STATUS'] = 'Confirmed'

        env['HTTP_X_USER_ID'] = access_info.user_id
        env['HTTP_X_USER_NAME'] = access_info.username
        env['HTTP_X_USER_DOMAIN_ID'] = access_info.user_domain_id
        env['HTTP_X_USER_DOMAIN_NAME'] = access_info.user_domain_name
        env['HTTP_X_ROLES'] = access_info.role_names
        if access_info.has_service_catalog():
            env['HTTP_X_SERVICE_CATALOG'] = \
                json.dumps(access_info.service_catalog.catalog)

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
        if access_info.project_scoped and \
            access_info.domain_scoped:
            env['HTTP_X_PROJECT_DOMAIN_ID'] = access_info.project_domain_id
            env['HTTP_X_PROJECT_DOMAIN_NAME'] = access_info.project_domain_name

        return True

    except Exception:
        msg = _('Error while trying to authenticate against %(s_url)')
        LOG.debug( msg % { 's_url' : auth_url })
        return False


def wrap(app, redis_client):
    """Wrap a WSGI app with Authentication middleware.

    Takes configuration from oslo.config.cfg.CONF.

    :param app: WSGI app to wrap
    :param redis_client: redis.Redis object connected to the redis cache

    :returns: a new  WSGI app that wraps the original
    """

    group = CONF[OPT_GROUP_NAME]
    auth_url = group[OPTION_AUTH_URL]
    region = group[OPTION_REGION]

    # WSGI callable
    def middleware(env, start_response):
        token = env['HTTP_X_AUTH_TOKEN']
        tenant = env['HTTP_X_PROJECT_ID']

        # validate the client and fill out the environment it's valid
        if _validate_client(redis_client, auth_url, tenant, token, env, region):
            LOG.debug(_('Auth Token validated.'))
            return app(env, start_response)

        else:
            # Validation failed for some reason, just error out as a 403
            LOG.error(_('Auth Token validation failed.'))
            return _http_forbidden(start_response)

    return middleware
