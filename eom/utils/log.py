from logging import *
import logging.config

from oslo.config import cfg

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
        config.fileConfig(log_config_file,
                          disable_existing_loggers=disable_existing)
