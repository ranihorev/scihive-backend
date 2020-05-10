import os

from flask import Flask
from dotenv import load_dotenv
# This is required to patch marshal
from flask_sqlalchemy import SQLAlchemy

from .logger import logger_config
from .patch_marshal import *

load_dotenv()
logger_config()

app = Flask(__name__)
app.url_map.strict_slashes = False

from . import main
