from flask import Flask
# This is required to patch marshal
from .patch_marshal import *

app = Flask(__name__)

with app.app_context():
    from . import main
