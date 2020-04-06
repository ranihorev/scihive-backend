import os

from flask import Flask
from dotenv import load_dotenv
# This is required to patch marshal
from flask_sqlalchemy import SQLAlchemy

from .patch_marshal import *

load_dotenv()

app = Flask(__name__)
# app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DB_URI')
# db = SQLAlchemy(app)


from . import main

# with app.app_context():
