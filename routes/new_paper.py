import logging
import xml.etree.ElementTree as ET
import re
from datetime import datetime
from diskcache import Cache

cache = Cache('cache')

import requests
import werkzeug
from flask import Blueprint
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_restful import Resource, Api, reqparse, marshal_with, fields
from typing import NamedTuple, List, Tuple

from .user_utils import add_to_library
from . import db_papers, db_authors
from .s3_utils import upload_to_s3

app = Blueprint('new_paper', __name__)
api = Api(app)
logger = logging.getLogger(__name__)


def get_tag_text(tree, tag, default_value='') -> str:
    element = tree.find(f'.//{tag}')
    return element.text if element is not None else default_value


def get_all_tag_texts(tree, tag):
    element = tree.findall(f'.//{tag}')
    return [e.text for e in element]


class Author(NamedTuple):
    first_name: str
    last_name: str
    org: List[str]

    def get_name(self):
        return f'{self.first_name} + f{self.last_name}'


class AuthorMarshal(fields.Raw):
    def format(self, value):
        return dict(value._asdict())


def extract_paper_metadata(file_content) -> Tuple[str, List[Author], str]:
    grobid_res = requests.post('http://cloud.science-miner.com/grobid/api/processHeaderDocument',
                               data={'consolidateHeader': 1}, files={'input': file_content})
    content = re.sub(' xmlns="[^"]+"', '', grobid_res.text)
    tree = ET.fromstring(content)
    title = get_tag_text(tree, 'title')

    authors_tree = tree.findall('.//author')
    authors: List[Author] = []
    for author_tree in authors_tree:
        author = Author(first_name=get_tag_text(author_tree, 'forename'),
                        last_name=get_tag_text(author_tree, 'surname'),
                        org=get_all_tag_texts(author_tree, 'orgName'))
        authors.append(author)
    abstract: str = tree.find('.//abstract') or ''
    if abstract:
        if abstract.getchildren():
            abstract = abstract.getchildren()[0].text
        else:
            abstract = abstract.text

    return title, authors, abstract


class NewPaper(Resource):
    method_decorators = [jwt_required]

    @marshal_with({'title': fields.String, 'abstract': fields.String, 'id': fields.String, 'authors': fields.List(AuthorMarshal)})
    def post(self):
        current_user = get_jwt_identity()
        parser = reqparse.RequestParser()
        parser.add_argument('file', type=werkzeug.datastructures.FileStorage, location='files')
        data = parser.parse_args()
        file_content = data.file.stream.read()
        filename_md5, exists = upload_to_s3(data.file, file_content)
        # if exists:
        #     return {'exists': True}
        response, expire = cache.get(filename_md5, expire_time=True)
        if not response:
            title, authors, abstract = extract_paper_metadata(file_content)
            response = {'id': filename_md5, 'title': title, 'authors': authors, 'abstract': abstract}
            cache.set(filename_md5, response, expire=12*60*60)

        # paper = db_papers.find_one_and_update({'_id': filename_md5},
        #                              {
        #                                  '$set':
        #                                      {
        #                                          'title': title, 'summary': abstract, 'time_updated': datetime.now(),
        #                                          'authors': [{'name': a.get_name()} for a in authors],
        #                                          'time_published': datetime.now(),
        #                                          'is_searchable': False
        #                                      }
        #                              },
        #                              upsert=True)
        # for author in authors:
        #     db_authors.update({'_id': author.get_name()},
        #                       {'$addToSet': {'papers': filename_md5}, '$set': {'organization': author.org}}, True)
        # add_to_library('save', current_user, paper)
        return response


api.add_resource(NewPaper, "/add")
