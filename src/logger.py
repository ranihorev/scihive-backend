import logging
from logging.config import dictConfig
import google.cloud.logging
import os
from google.cloud.logging.handlers import CloudLoggingHandler

is_init = False

BASE_FORMAT = '%(asctime)s - %(name)-12s %(levelname)-8s %(message)s'
is_google_cloud = os.environ.get('GOOGLE')
env = os.environ.get('FLASK_ENV', 'development')


def logger_config():
    global is_init
    if is_init:
        logging.warning('logger is already initialized')
        return

    root_module = __name__.split('.')[0]
    formatters = {
        'f': {'format': BASE_FORMAT},
        'json': {'format': '%(asctime)s %(name)s %(levelname)s %(message)s', "class": f'{root_module}.formatter.CustomJsonFormatter'}
    }

    handlers = {
        "console": {
            "class": "logging.StreamHandler",
            "level": "DEBUG",
            "formatter": "json"
        }
    }

    loggers = {
        "boto3": {
            "level": "WARNING",
        },
        "botocore": {
            "level": "WARNING",
        },
        "engineio": {
            "level": "WARNING",
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
        "socketio.server": {
            "level": "INFO" if env == 'development' else "WARNING"
        },
        "sqlalchemy": {
            "level": "WARNING",
        }
    }

    root_handlers = ["console"] if not is_google_cloud else []

    logging_config = dict(
        version=1,
        disable_existing_loggers=False,
        formatters=formatters,
        handlers=handlers if not is_google_cloud else [],
        loggers=loggers,
        root={
            "level": "INFO",
            "handlers": root_handlers
        }
    )
    is_init = True
    dictConfig(logging_config)

    # Setup google client
    if is_google_cloud:
        try:
            client = google.cloud.logging.Client()
            handler = CloudLoggingHandler(client)
            handler.setLevel(logging.INFO)
            root_logger = logging.getLogger('root')
            root_logger.addHandler(handler)
            logging.info('Google cloud logger was installed successfully')
        except Exception as e:
            print('Failed to add Google Cloud logger')
