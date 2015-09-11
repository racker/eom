Configuration Files
===================

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

