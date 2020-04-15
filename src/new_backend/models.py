import os

import sqlalchemy as sa
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy_searchable import make_searchable
from sqlalchemy_utils import TSVectorType

from .. import app

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DB_URI')

db = SQLAlchemy(app)
migrate = Migrate(app, db)

make_searchable(db.metadata)

paper_author_table = db.Table('paper_author', db.metadata,
                              db.Column('paper_id', db.Integer, db.ForeignKey('paper.id')),
                              db.Column('author_id', db.Integer, db.ForeignKey('author.id'))
                              )

paper_tag_table = db.Table('paper_tag', db.metadata,
                           db.Column('paper_id', db.Integer, db.ForeignKey('paper.id')),
                           db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'))
                           )

paper_collection_table = db.Table('paper_collection', db.metadata,
                                  db.Column('paper_id', db.Integer, db.ForeignKey('paper.id')),
                                  db.Column('collection_id', db.Integer, db.ForeignKey('collection.id'))
                                  )

user_collection_table = db.Table('user_collection', db.metadata,
                                 db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
                                 db.Column('collection_id', db.Integer, db.ForeignKey('collection.id'))
                                 )


class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(80), nullable=False)
    username = db.Column(db.String(50), nullable=False)
    password = db.Column(db.String(100), nullable=False)
    collections = db.relationship("Collection", back_populates="users", secondary=paper_collection_table)


class Paper(db.Model):
    __tablename__ = 'paper'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    link = db.Column(db.String, nullable=False)
    pdf_link = db.Column(db.String, nullable=False)
    publication_date = db.Column(db.DateTime, nullable=False)
    abstract = db.Column(db.String, nullable=True)
    original_id = db.Column(db.String, nullable=False)
    last_update_date = db.Column(db.DateTime, nullable=False)
    authors = db.relationship("Author", back_populates="papers", secondary=paper_author_table)
    tags = db.relationship("Tag", back_populates="papers", secondary=paper_tag_table)
    collections = db.relationship("Collection", back_populates="papers", secondary=paper_collection_table)
    search_vector = db.Column(TSVectorType('title', 'abstract'))

    def __repr__(self):
        return f"{self.id} - {self.title}"


class ArxivPaper(db.Model):
    __tablename__ = 'arxiv_paper'
    paper = db.Column(db.ForeignKey('paper.id'), primary_key=True)
    json_data = db.Column(db.JSON)


class Tag(db.Model):
    __tablename__ = 'tag'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    papers = db.relationship("Paper", back_populates="tags", secondary=paper_tag_table)
    source = db.Column(db.String(30), nullable=False)


class Author(db.Model):
    __tablename__ = 'author'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    papers = db.relationship("Paper", back_populates="authors", secondary=paper_author_table)


class Collection(db.Model):
    __tablename__ = 'collection'
    id = db.Column(db.Integer, primary_key=True)
    is_library = db.Column(db.Boolean)
    name = db.Column(db.String(100), nullable=False)
    color = db.Column(db.String(30), nullable=True)
    papers = db.relationship("Paper", back_populates="collections", secondary=paper_collection_table)
    users = db.relationship("User", back_populates="collections", secondary=paper_collection_table)
    creation_date = db.Column(db.DateTime, nullable=False)
    created_by = db.Column(db.ForeignKey('user.id'), nullable=False)


class Comment(db.Model):
    __tablename__ = 'comment'
    id = db.Column(db.Integer, primary_key=True)
    highlighted_text = db.Column(db.String, nullable=True)
    text = db.Column(db.String, nullable=False)
    paper = db.Column(db.ForeignKey('paper.id'))
    creation_date = db.Column(db.DateTime, nullable=False)
    user = db.Column(db.ForeignKey('user.id'))
    position = db.Column(db.JSON)


class RevokedToken(db.Model):
    __tablename__ = 'revoked_token'
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String, nullable=False)


sa.orm.configure_mappers()
db.create_all()
