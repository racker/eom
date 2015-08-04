EOM: Emerging OpenStack WSGI Middleware
===========================================

:version: 0.5.0

Incubator project for general OpenStack API middleware.

So far, includes verb-based ACL enforcement and simple/efficient rate limiting.
Ideas and code should be contributed upstream to OpenStack, according to community interest.

**Table of Contents**

.. contents::
	:local:
	:depth: 2

========
Overview
========

EOM is a Python-based middleware for RESTful application servers built on and/or providing OpenStack APIs.
The functionality provided generally aims to comply with OpenStack project guidelines, making use of
functionality provided by OpenStack where possible in order to provide a series of tools for OpenStack API
projects.

-------------------
Configuration Files
-------------------

The configuration files for EOM are located in /etc/eom or ~/.eom. The primary configuration file is
eom.conf. This functionality is serviced through the OpenStack oslo.config functionality in accordance
with OpenStack guidelines.

Each project contained here has its own sections in the configuration files, and may provide some additional
configuration files.

Note that as of 0.6.1, each module must be specifically configured after it is imported into the WSGI app.
The following is an example of the EOM Auth module being loaded in this manner:

.. code-block:: python

    import eom.auth
    from oslo_config import cfg
    import myapp

    CONF = cfg.CONF
    CONF(project='mywsgiapp', args=[])
    eom.auth.configure(CONF)

    auth_redis_client = auth.get_auth_redis_client()

    app = eom.auth.wrap(myapp.app, auth_redis_client)

Failure to call the configuration function on the modules will still allow the functionality to run; however,
they may not have the expected settings.

-------------------
Logging EOM Modules
-------------------

The EOM WSGI Middleware modules have two settings to enable logging functionality via their configuration sections.

Configuration
-------------

.. code-block:: ini

    [eom:module]
    log_config_file = /etc/eom/logging.conf
    log_config_disable_existing = False

The value of the log_config_file is the path to a file containing the configuration to be loaded via the built-in
Python logging.config functionality, specifically logging.config.fileConfig(). Any file that can be loaded via the
ConfigParser can be utilized.

The value of log_config_disable_existing is a boolean value that determines whether or not the configurator clears
any existing logging handlers, etc before loading the specified configuration.

More information is available at https://docs.python.org/2/library/logging.config.html#logging.config.fileConfig.

====
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

=======
Bastion
=======

TBD

-------------
Configuration
-------------

.. code-block:: ini

	[eom:bastion]
	unrestricted_routes = /v1/pin, /v1/health
	log_config_file = /etc/eom/logging.conf
	log_config_disable_existing = False

========
Governor
========

EOM Governor provides rate limiting based on a leaky-bucket algorithm, while using redis for caching.

Before we go into the algorithm, there are a few things we need to know about

.. code-block:: ini

    count : This refers to number tokens in the bucket at a given point in time
    drain_velocity : factor by which tokens are removed from the bucket
    drain : The actual number of tokens going to be removed
            k * drain_velocity , where k is a positive real number
    throttle_milliseconds : the number of milliseconds needed to be slept, when the
                            bucket is full.
    limit : the max number of tokens that a bucket can accommodate at any given point
            in time
    route : python RegEx for a given endpoint that needs to be rate-limited
    methods : HTTP verbs
    rates_file : JSON file containing route, methods, limits and drain_velocity
    project_rates_file : JSON file with details on project id specific rate limiting

---------
Algorithm
---------

The first time a request is made to the wsgi app, which has been wrapped by the Governor, count is initialized to be 1
and current timestamp recorded in redis.

The timestamp that is used is shown below:

.. code-block:: python

    now = time.time()

The next time a request is made:

.. code-block:: python

    drain = (now - last_time) * rate.drain_velocity
    new_count = max(0.0, count - drain) + 1.0


'now' refers to the current time, and 'last_time' refers to time when the last request was made by the client.
'rate.drain_velocity' is left to configurable to the user, but is usually set to be the requisite limit in requests/second
For eg: rate.drain_velocity is to set to 300, if the rate limit is set to 300 requests/second.

drain is now calculated, and subtracted from count. The result is incremented by '1' to take into account the current request.

Similarly, as before the count and current time are now set in redis.

If count exceeds the limit at any point in time, The Governors sleeps for 'throttle_milliseconds' (forces back pressure
on clients) and returns HTTP 429 Too Many Requests.

.. code-block:: python

    HTTP/1.1 429 Too Many Requests
    Content-Length: 0


Sleeping allows (now - last_time) to be a higher value for the next request, causing higher drain and more tokens to be
removed from the bucket.

This procedure helps maintain the number of requests/sec to be the limit set in rates_file/project_rates_file.

-------------
Configuration
-------------

.. code-block:: ini

	[eom:governor]
	rates_file = /home/bmeyer/.eom/governor.json
	project_rates_file = /home/bmeyer/.eom/governor_project.json
	throttle_milliseconds = 5
	log_config_file = /etc/eom/logging.conf
	log_config_disable_existing = False

	[eom:redis]
	host = 192.168.3.11
	port = 6379

=======
Metrics
=======

EOM Metrics provides a way to collect statistical data on the end-points in the WSGI application via a StatsD collector service.

-------------
Configuration
-------------

.. code-block:: ini

    [eom:metrics]
    address = localhost
    port = 80
    path_regexes_keys = 'all'
    path_regexes_values = '^/'
    prefix = 'eom_metrics'
    app_name = 'eom_deployed_app'
    log_config_file = /etc/eom/logging.conf
    log_config_disable_existing = False

====
RBAC
====

EOM RBAC provides Role-based Access Control which defines rules on the types of resources a particular user has access to, and filters users accordingly.

-------------
Configuration
-------------

.. code-block:: ini

	[eom:rbac]
	acls_file=rbac.json
	log_config_file = /etc/eom/logging.conf
	log_config_disable_existing = False


The acls_file parameter specifies a JSON formatted file on the local system that provides the filter rules as follows:

.. code-block:: json

    {
        "resource": "health",
        "route": "/v1/health",
        "acl": {
            "read": ["observer"]
        }
    }


    resource : name of the resource

    route : a Python Regex that would match all the different combinations for a given endpoint

    acl : an access control list, with different roles being assigned to read, write and delete

Internally the RBAC middleware associates each of read, write and delete to their appropriate HTTP verb.
For eg: PUT is mapped to write

-------------------
How does RBAC work?
-------------------

The RBAC middleware relies on the X-Roles Header being set per request. This contains the roles assigned to the particular
user. Incidentally, loading up the EOM Auth middleware before setting up the RBAC middleware sets the X-Roles Header.

It is also to be noted that the RBAC middleware only checks those routes that are present in rbac.json, a request that does not match any given routes
will be passed on to the wsgi app that is next in the pipeline with no verification.

If the current request matches a route defined in a particular resource in rbac.json, the corresponding permissions are checked for the user.

Now, if the user possesses appropriate permissions to access the resource, the request is passed though. Otherwise, the request is denied with HTTP 403 Forbidden

.. code-block:: python

    HTTP/1.1 403 Forbidden
    Content-Length: 0

=====
uWSGI
=====

TBD

--------
Log Vars
--------

TBD

=======
Version
=======

TDB
