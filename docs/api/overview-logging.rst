Logging EOM Modules
===================

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

