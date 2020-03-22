from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
db = SQLAlchemy(app)


class Paper(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pub_date = db.Column(db.String(80), unique=False, nullable=True)
    title = db.Column(db.String, unique=True, nullable=False)
    abstract = db.Column(db.String, unique=True, nullable=False)
    authors
    original_id = db.Column(db.Integer)
    original_json = db.Column(db.String, unique=False, nullable=False)
