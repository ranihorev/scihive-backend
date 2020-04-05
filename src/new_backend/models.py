import os

from sqlalchemy import *
from sqlalchemy.orm import (scoped_session, sessionmaker, relationship,
                            backref)
from sqlalchemy.ext.declarative import declarative_base, DeferredReflection

engine = create_engine(os.environ.get('DB_URI'), convert_unicode=True)
db_session = scoped_session(sessionmaker(autocommit=False,
                                         autoflush=False,
                                         bind=engine))

Base = declarative_base()
# We will need this for querying
Base.metadata.bind = engine
Base.query = db_session.query_property()

paper_author_table = Table('paper_author', Base.metadata,
                           Column('paper_id', Integer, ForeignKey('paper.id')),
                           Column('author_id', Integer, ForeignKey('author.id'))
                           )

paper_tag_table = Table('paper_tag', Base.metadata,
                        Column('paper_id', Integer, ForeignKey('paper.id')),
                        Column('tag_id', Integer, ForeignKey('tag.id'))
                        )

paper_collection_table = Table('paper_collection', Base.metadata,
                               Column('paper_id', Integer, ForeignKey('paper.id')),
                               Column('collection_id', Integer, ForeignKey('collection.id'))
                               )


class User(Base):
    __tablename__ = 'user'
    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)
    email = Column(String(80), nullable=False)
    username = Column(String(50), nullable=False)
    password = Column(String(100), nullable=False)


class Paper(Base):
    __tablename__ = 'paper'
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    link = Column(String, nullable=False)
    pdf_link = Column(String, nullable=False)
    publication_date = Column(Date, nullable=False)
    abstract = Column(String, nullable=True)
    original_id = Column(String, nullable=False)
    last_update_date = Column(Date, nullable=False)
    authors = relationship("Author", back_populates="papers", secondary=paper_author_table)
    tags = relationship("Author", back_populates="papers", secondary=paper_tag_table)
    collections = relationship("Collection", back_populates="papers", secondary=paper_collection_table)

    def __repr__(self):
        return "test"


class ArxivPaper(Base):
    __tablename__ = 'arxiv_paper'
    paper = ForeignKey('paper.id', primary_key=True)
    json_data = Column(JSON)


class Tag(Base):
    __tablename__ = 'tag'
    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)
    papers = relationship("Paper", back_populates="tags", secondary=paper_tag_table)
    source = Column(String(30), nullable=False)


class Author(Base):
    __tablename__ = 'author'
    id = Column(Integer, primary_key=True)
    name = Column(String(80), nullable=False)
    papers = relationship("Paper", back_populates="authors", secondary=paper_author_table)


class Collection(Base):
    __tablename__ = 'collection'
    id = Column(Integer, primary_key=True)
    is_library = Column(Boolean, primary_key=True)
    name = Column(String(100), nullable=False)
    color = Column(String(30), nullable=True)
    papers = relationship("Paper", back_populates="collections", secondary=paper_collection_table)
    creation_date = Column(Date, nullable=False)


class Comment(Base):
    __tablename__ = 'comment'
    id = Column(Integer, primary_key=True)
    highlighted_text = Column(String, nullable=True)
    text = Column(String, nullable=False)
    paper = ForeignKey('paper.id')
    creation_date = Column(Date, nullable=False)
    user = ForeignKey('user.id')
    position = Column(JSON)


Base.metadata.create_all(bind=engine)
