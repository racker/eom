from oslo_config import cfg

from eom import governor
from eom.utils import redis_pool
from tests.util import app as example_app

conf = cfg.CONF
conf(project='eom', args=[])

redis_client = redis_pool.get_client()
# NOTE(TheSriram): wsgi app can be served via gunicorn governor_app:app
app = governor.wrap(example_app, redis_client)
