try:
    import uwsgi  # noqa
except ImportError:
    raise ImportError("These modules must be run in a uwsgi server process.")
