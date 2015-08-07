.. _rbac:

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


