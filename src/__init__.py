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

load_dotenv(dotenv_path=os.environ.get('ENV_FILE'))
logger_config()

flask_app = Flask(__name__)
flask_app.url_map.strict_slashes = False
if os.environ.get('ENV', 'development') == 'development':
    flask_app.wsgi_app = EasyProfileMiddleware(flask_app.wsgi_app)

socketio_app = SocketIO(flask_app, cors_allowed_origins="*")

from . import main
