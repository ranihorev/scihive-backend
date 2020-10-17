import logging
from logging.config import dictConfig

is_init = False

BASE_FORMAT = '%(asctime)s - %(name)-12s %(levelname)-8s %(message)s'


def logger_config(path='', info_filename='info.log', num_backups=5):
    global is_init
    if is_init:
        logging.warning('logger is already initialized')
        return

    logging.getLogger('boto3').setLevel(logging.WARNING)
    logging.getLogger('botocore').setLevel(logging.WARNING)
    logging.getLogger('engineio').setLevel(logging.WARNING)

    handlers = {
        "console": {
            "class": "logging.StreamHandler",
            "level": "DEBUG",
            "formatter": "f"
        },

        "info_file_handler": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "INFO",
            "formatter": "f",
            "filename": path + info_filename,
            "maxBytes": 10485760,
            "backupCount": num_backups,
            "encoding": "utf8"
        }

    }

    loggers = {
        "elasticsearch": {
            "level": "WARNING",
            "propagate": "no"
        },
        "urllib3": {
            "level": "WARNING",
            "propagate": "no"
        },
        "tweepy": {
            "level": "WARNING",
            "propagate": "no"
        },
        "prawcore": {
            "level": "WARNING",
            "propagate": "no"
        },
        "requests": {
            "level": "WARNING",
            "propagate": "no"
        },
    }

    root_handlers = ["console", "info_file_handler", ]

    logging_config = dict(
        version=1,
        disable_existing_loggers=False,
        formatters={
            'f': {'format': BASE_FORMAT},
            'syslog_f': {}
        },
        handlers=handlers,
        loggers=loggers,
        root={
            "level": "DEBUG",
            "handlers": root_handlers
        }
    )
    is_init = True
    dictConfig(logging_config)
