# Copyright (c) 2013 Rackspace, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from oslo_config import cfg
import redis

_CONF = cfg.CONF

REDIS_GROUP_NAME = 'eom:redis'
OPTIONS = [
    cfg.StrOpt('host'),
    cfg.StrOpt('port'),
]

_CONF.register_opts(OPTIONS, group=REDIS_GROUP_NAME)


def get_client():
    group = _CONF[REDIS_GROUP_NAME]
    pool = redis.ConnectionPool(host=group['host'], port=group['port'], db=0)
    return redis.Redis(connection_pool=pool)
