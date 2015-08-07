.. _bastion:

Bastion
=======

EOM Bastion provides the ability to by-pass a WSGI Middleware based on the URI being called.
For instance, one might want to by-pass EOM:Auth for a URI for a Health or Ping end-point in order
to ensure that devices (f.e load balancers) can access them at all times without having to deploy
credentials to those devices.

-------------
Configuration
-------------

.. code-block:: ini

	[eom:bastion]
	unrestricted_routes = /v1/pin, /v1/health
	log_config_file = /etc/eom/logging.conf
	log_config_disable_existing = False
