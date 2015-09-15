.. _bastion:

Bastion
=======

EOM Bastion provides the ability to by-pass a WSGI Middleware based on the URI being called.
For instance, one might want to by-pass EOM:Auth for a URI for a Health or Ping end-point in order
to ensure that devices (f.e load balancers) can access them at all times without having to deploy
credentials to those devices.
Additionally, if the ```gate_headers``` option is provided, bastion will deny access to the gated app
for any request that includes ALL of the headers specified by the option. ```gate_headers``` should be
a comma-separated list of wsgi 'HTTP_' headers.

-------------
Configuration
-------------

.. code-block:: ini

	[eom:bastion]
	unrestricted_routes = /v1/pin, /v1/health
	log_config_file = /etc/eom/logging.conf
	log_config_disable_existing = False
	gate_headers = HTTP_X_FORWARDED_FOR
