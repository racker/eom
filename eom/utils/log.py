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

import logging.config
from logging import getLogger as logging_getLogger

from oslo_config import cfg

LOG_APP_OPTIONS = [
    cfg.StrOpt('log_config_file', default=None),
    cfg.BoolOpt('log_config_disable_existing', default=True)
]


def register(config, app_section):
    config.register_opts(LOG_APP_OPTIONS, group=app_section)


def setup(config, app_section):
    log_config_file = config[app_section]['log_config_file']
    disable_existing = config[app_section]['log_config_disable_existing']

    if log_config_file is not None:
        logging.config.fileConfig(log_config_file,
                                  disable_existing_loggers=disable_existing)


def getLogger(*args, **kwargs):
    return logging_getLogger(*args, **kwargs)
