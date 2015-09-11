.. _governor:

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

