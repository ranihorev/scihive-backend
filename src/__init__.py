import os

from flask import Flask
from dotenv import load_dotenv
# This is required to patch marshal
from flask_sqlalchemy import SQLAlchemy

from .patch_marshal import *

load_dotenv()

app = Flask(__name__)
app.url_map.strict_slashes = False

from . import main
