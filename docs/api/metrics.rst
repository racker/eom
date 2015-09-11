.. _metrics:

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

