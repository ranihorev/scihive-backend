import os
from flask import Flask
from dotenv import load_dotenv
# This is required to patch marshal
# noinspection PyUnresolvedReferences
from flask_sqlalchemy import SQLAlchemy
from easy_profile import EasyProfileMiddleware
import os
from flask_socketio import SocketIO
from .logger import logger_config
from .patch_marshal import *
import logging

load_dotenv(dotenv_path=os.environ.get('ENV_FILE'))
logger_config()
app_logger = logging.getLogger(__name__)

env = os.environ.get('FLASK_ENV', 'development')

flask_app = Flask(__name__)
cors_allowed_origins = os.environ.get('FRONTEND_URL')
if not cors_allowed_origins:
    app_logger.warning('Falling back to allow all origins. Not recommended in production!')
    cors_allowed_origins = '*'

flask_app.url_map.strict_slashes = False
if env == 'development':
    flask_app.wsgi_app = EasyProfileMiddleware(flask_app.wsgi_app)

socketio_app = SocketIO(flask_app, cors_allowed_origins=[cors_allowed_origins])


from . import main
