import redis

from oslo.config import cfg

CONF = cfg.CONF

REDIS_GROUP_NAME = 'eom:redis'
OPTIONS = [
    cfg.StrOpt('host'),
    cfg.StrOpt('port'),
]

CONF.register_opts(OPTIONS, group=REDIS_GROUP_NAME)


def get_connection():
    group = CONF[REDIS_GROUP_NAME]
    pool = redis.ConnectionPool(host=group['host'], port=group['port'], db=0)
    r = redis.Redis(connection_pool=pool)
    return r
