from eom import auth
from tests.util import app as example_app

# Get the separated Redis Server for Auth
auth_redis_client = auth.get_auth_redis_client()

app = auth.wrap(example_app, auth_redis_client)
