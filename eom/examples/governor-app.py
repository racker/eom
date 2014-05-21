from eom import governor
from eom.utils import redis_pool
from tests.util import app as example_app


redis_handler = redis_pool.get_connection()
# NOTE(TheSriram): wsgi app can be served via gunicorn governor-app:app
app = governor.wrap(example_app, redis_handler)
