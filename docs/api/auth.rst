.. _auth:

Auth
====

EOM Auth is an authentication middleware that performs all operations against OpenStack Keystone APIs entirely
as the potentially Authenticated User.

-----------------
Why Use EOM Auth?
-----------------

The big advantage of using EOM Auth over Keystone Middleware is that it does not need the Admin Token that is
presently part of the central design of Keystone Middleware. This is in part because Keystone Middleware and
similar tools use the Keystone Token Validation API which requires the special Admin Token in order to validate
an incoming Token.

In contrast, EOM Auth essentially performs an authentication using credentials that the requester provided
(tenant/project id and authentication token). If the authentication succeeds, then the header data is extracted
and inserted; if it fails, then it fails to the API requester with an appropriate response.

----------------------
Requester Requirements
----------------------

Unlike Keystone Middleware, which requires and forces that only the X-Auth-Token header be provided; EOM Auth
also requires that the X-Project-ID header be specified. If the requisite headers are missing, then EOM Auth
will respond with a 412 Precondition Failed error. If the headers are present but it is unable to authenticate
then it will respond with a 401 Unauthorized error.

-------------
Configuration
-------------

EOM Auth has a small configuration consisting of two sections: (i) auth, (ii) caching.

Auth
----

EOM Auth needs only a couple values in the auth section of the eom.conf file to operate:

.. code-block:: ini

	[eom:auth]
	auth_url = 'https://openstack.keystone.url/v2.0'
	blacklist_ttl = 3600000
	log_config_file = /etc/eom/logging.conf
	log_config_disable_existing = False

The auth_url specifies the full Keystone API including version. All calls made are in the context of the user
being authenticated. To minimize calls, successful authentication information is cached.

As a security precaution, if an authentication fails then the token is blacklisted for an administratively
defined time period specified by blacklist_ttl. The value is stored in milliseconds.

Caching
-------

In order to enhance performance and reduce load on Keystone, EOM Auth will cache certain data. Presently
this is supported using Redis and configured in the auth_redis section of the eom.conf file.

.. code-block:: ini

	[auth_redis]
	host = 127.0.0.1
	port = 6379
	redis_db = 0
	password = None
	ssl_enabled = False
	ssl_certfile = None
	ssl_cert_reqs = None
	ssl_ca_certs = None

EOM Auth supports Redis having authentication and SSL encrypted traffic though by default it is turned off.
The only required fields are the host and port.

----------
Provisions
----------
APIs that use EOM Auth require that the requester provide the X-Project-Id and X-Auth-Token headers which
provide a Tenant+Token authentication. For valid tokens the EOM Auth middleware then inserts all the same
information that the Keystone Middleware does with the exception that any deprecated field (as of 2014-10)
is not included. The currently supported list of headers are in all cases:

- X-Identity-Status
- X-User-ID
- X-User-Name
- X-User-Domain-ID
- X-Roles

Where available the following is also provided:

- X-Service-Catalog (encoded as Base64 UTF-8 data JSON)
- X-Project-ID
- X-Project-Name
- X-Domain-ID
- X-Domain-Name
- X-Project-Domain-ID
- X-Project-Domain-Name
