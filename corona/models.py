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

class Paper(Base):
    __tablename__ = 'paper'
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    published_at = Column(Date, nullable=False)
    abstract = Column(String, nullable=True)
    authors = relationship("Author", back_populates="papers", secondary=paper_author_table)
    original_id = Column(String, nullable=False)
    json_data = Column(JSON)

    def __repr__(self):
        return "test"


class Author(Base):
    __tablename__ = 'author'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    papers = relationship("Paper", back_populates="authors", secondary=paper_author_table)


Base.metadata.create_all(bind=engine)

