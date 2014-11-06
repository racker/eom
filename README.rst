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

	[auth]
	auth_url = 'https://openstack.keystone.url/v2.0'
	blacklist_ttl = 3600000 

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
	restricted_routes = /v1/pin, /v1/health

========
Governor
========

TBD

-------------
Configuration
-------------

.. code-block:: ini

	[eom:governor]
	rates_file = /home/bmeyer/.eom/governor.json
	project_rates_file = /home/bmeyer/.eom/governor_project.json
	throttle_milliseconds = 5

	[eom:redis]
	host = 192.168.3.11
	port = 6379

=======
Metrics
=======

TBD

====
RBAC
====

RBAC (Role Based Access Control) defines rules on the type of resources a particular user has access to.
EOM has a rbac middleware, which allows for the above type of filtering.

-------------
Configuration
-------------

.. code-block:: ini

	[eom:rbac]
	acls_file=rbac.json


The filters are of the form specified in rbac.json

.. code-block:: json

    {
        "resource": "health",
        "route": "/v1/health",
        "acl": {
            "read": ["observer"]
        }
    }


    resource : name of the resource

    route : a regex that would match all the different combinations for a given endpoint

    acl : an access control list, with different roles being assigned to read, write and delete

Internally the rbac middleware associates each of read, write and delete to their appropriate HTTP verb.
For eg: PUT is mapped to write

-------------------
How does RBAC work?
-------------------

The rbac middleware relies on the X-Roles Header being set per request. This contains the roles assigned to the particular
user. Incidentally, loading up the eom auth middleware before setting up the rbac middleware sets the X-Roles Header.

It is also to be noted that the rbac middleware only checks those routes that are present in rbac.json, a request that does not match any given routes
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



