import os

import sqlalchemy as sa
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy_searchable import make_searchable
from sqlalchemy_utils import TSVectorType
from sqlalchemy_utils import ChoiceType
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy_continuum import make_versioned
from sqlalchemy.dialects.postgresql import ARRAY

from datetime import datetime
from .. import app

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DB_URI')

make_versioned(user_cls=None)

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
                                  db.Column('collection_id', db.Integer, db.ForeignKey('collection.id')),
                                  db.Column('date_added', db.DateTime(timezone=True),
                                            nullable=False, default=datetime.now, index=True)
                                  )

user_collection_table = db.Table('user_collection', db.metadata,
                                 db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
                                 db.Column('collection_id', db.Integer, db.ForeignKey('collection.id'))
                                 )


class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(80), nullable=False, index=True)
    username = db.Column(db.String(50), nullable=False)
    password = db.Column(db.String(100), nullable=False)
    collections = db.relationship("Collection", back_populates="users", secondary=user_collection_table)
    comments = db.relationship("Comment")
    old_id = db.Column(db.String(80), index=True)


class Paper(db.Model):
    __tablename__ = 'paper'
    __versioned__ = {
        'exclude': ['authors', 'tags', 'collections', 'comments', 'tweets']
    }

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String, nullable=False)
    link = db.Column(db.String, nullable=True)
    original_pdf = db.Column(db.String, nullable=True)
    local_pdf = db.Column(db.String, nullable=True)
    publication_date = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    abstract = db.Column(db.String, nullable=True)
    original_id = db.Column(db.String, nullable=True, index=True)
    last_update_date = db.Column(db.DateTime(timezone=True), nullable=False)
    is_private = db.Column(db.Boolean, nullable=True)
    authors = db.relationship("Author", back_populates="papers", secondary=paper_author_table, lazy='joined')
    tags = db.relationship("Tag", back_populates="papers", secondary=paper_tag_table)
    collections = db.relationship("Collection", back_populates="papers",
                                  secondary=paper_collection_table)
    search_vector = db.Column(TSVectorType('title', 'abstract'))
    comments = db.relationship("Comment", lazy='joined')
    tweets = db.relationship("Tweet")
    twitter_score = db.Column(db.Integer, default=0, index=True)
    num_stars = db.Column(db.Integer, default=0, index=True)
    references = db.Column(db.JSON)
    paper_with_code = db.relationship("PaperWithCode", uselist=False, lazy='joined')

    def __repr__(self):
        return f"{self.id} - {self.title}"

    @hybrid_property
    def comments_count(self):
        return len(self.comments)


class ArxivPaper(db.Model):
    __tablename__ = 'arxiv_paper'
    paper_id = db.Column(db.ForeignKey('paper.id'), primary_key=True)
    json_data = db.Column(db.JSON)


class Tag(db.Model):
    __tablename__ = 'tag'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, index=True)
    papers = db.relationship("Paper", back_populates="tags", secondary=paper_tag_table)
    source = db.Column(db.String(30), nullable=False)


class Author(db.Model):
    __tablename__ = 'author'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(80), nullable=False, index=True)
    first_name = db.Column(db.String(80), nullable=True)
    last_name = db.Column(db.String(80), nullable=True)
    organization = db.Column(ARRAY(db.String), nullable=True)
    papers = db.relationship("Paper", back_populates="authors", secondary=paper_author_table)


class Collection(db.Model):
    __tablename__ = 'collection'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    color = db.Column(db.String(30), nullable=True)
    papers = db.relationship("Paper", back_populates="collections", secondary=paper_collection_table)
    users = db.relationship("User", back_populates="collections", secondary=user_collection_table)
    creation_date = db.Column(db.DateTime(timezone=True), nullable=False)
    created_by_id = db.Column(db.ForeignKey('user.id'), nullable=False)
    created_by = db.relationship("User")
    is_uploads = db.Column(db.Boolean, nullable=True)
    old_id = db.Column(db.String(80), index=True)


class Comment(db.Model):
    TYPES = [
        (u'private', u'private'),
        (u'anonymous', u'anonymous'),
        (u'public', u'public'),
        (u'collection', u'group'),
    ]

    __tablename__ = 'comment'
    id = db.Column(db.Integer, primary_key=True)
    highlighted_text = db.Column(db.String, nullable=True)
    is_general = db.Column(db.Boolean, nullable=True)
    text = db.Column(db.String, nullable=False)
    paper_id = db.Column(db.ForeignKey('paper.id'))
    paper = db.relationship("Paper")
    creation_date = db.Column(db.DateTime(timezone=True), nullable=False)
    user_id = db.Column(db.ForeignKey('user.id'), nullable=True)
    user = db.relationship("User")
    position = db.Column(db.JSON)
    shared_with = db.Column(ChoiceType(TYPES), nullable=False)
    collection_id = db.Column(db.ForeignKey('collection.id'), nullable=True)
    collection = db.relationship("Collection")
    replies = db.relationship("Reply", lazy='joined')


class Reply(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    parent_id = db.Column(db.ForeignKey('comment.id'))
    parent = db.relationship("Comment")
    creation_date = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.now)
    text = db.Column(db.String, nullable=False)
    user_id = db.Column(db.ForeignKey('user.id'), nullable=True)
    user = db.relationship("User")


class RevokedToken(db.Model):
    __tablename__ = 'revoked_token'
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String, nullable=False)


class PaperWithCode(db.Model):
    __tablename__ = 'paper_with_code'
    id = db.Column(db.Integer, primary_key=True)
    paper_id = db.Column(db.ForeignKey('paper.id'))
    paper = db.relationship("Paper")
    github_link = db.Column(db.String(150), nullable=True)
    link = db.Column(db.String(150), nullable=False)
    stars = db.Column(db.Integer)
    framework = db.Column(db.String(50), nullable=True)
    last_update_date = db.Column(db.DateTime(timezone=True), nullable=False)


class Tweet(db.Model):
    __tablename__ = 'tweet'
    id = db.Column(db.String(50), primary_key=True)  # We assume a single paper per tweet
    paper_id = db.Column(db.ForeignKey('paper.id'))
    paper = db.relationship("Paper")
    insertion_date = db.Column(db.DateTime(timezone=True), nullable=False)
    creation_date = db.Column(db.DateTime(timezone=True), nullable=False)
    lang = db.Column(db.String(20))
    retweets = db.Column(db.Integer)
    likes = db.Column(db.Integer)
    replies = db.Column(db.Integer)
    user_screen_name = db.Column(db.String(200))
    user_name = db.Column(db.String(50))
    user_followers_count = db.Column(db.Integer)
    user_following_count = db.Column(db.Integer)
    text = db.Column(db.String)


sa.orm.configure_mappers()
db.create_all()
