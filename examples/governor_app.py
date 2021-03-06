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

from eom import governor
from eom.utils import redis_pool
from tests.util import app as example_app

conf = cfg.CONF
conf(project='eom', args=[])

governor.configure(conf)

redis_client = redis_pool.get_client()
# NOTE(TheSriram): wsgi app can be served via gunicorn governor_app:app
app = governor.wrap(example_app, redis_client)
