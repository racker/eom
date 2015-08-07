Log Vars
========

The EOM uWSGI logvar_mapper module provides the means to capture information from the WSGI/HTTP Headers being submitted by WSGI, prior Middleware, and the client
to the logs.

Configuration
-------------

.. code-block:: ini

	[eom:uwsgi:mapper]
	options_file = uwsgi_logvar_mapper.json

The options_file parameter specifies a JSON formatted file on the local system that profiles the mapping functionality as follows:

.. code-block:: json

	{
		"map": {
			"X-Project-Id": "project",
			"X-Forwarded-For": "lb_ip"
		}
	}

	map: a JSON dictionary of keys mapping the header value to an easier to use value used in the log specifications

