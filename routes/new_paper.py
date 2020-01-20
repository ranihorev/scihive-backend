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

from .user_utils import add_to_library, add_user_data
from . import db_papers, db_authors
from .s3_utils import upload_to_s3, key_to_url, calc_md5

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
        return f'{self.first_name} {self.last_name}'


class AuthorMarshal(fields.Raw):
    def format(self, value):
        return {'name': value.get_name()}


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

    publish_date_raw = tree.find('.//date')
    if publish_date_raw is not None:
        try:
            publish_date = publish_date_raw.get('when')
            publish_date = datetime.strptime(publish_date, "%Y-%m-%d")
        except Exception as e:
            logger.error(f'Failed to extract date for {publish_date_raw.text}')
            publish_date = datetime.now()
    else:
        publish_date = datetime.now()

    return {'title': title or '', 'authors': authors, 'abstract': abstract, 'date': publish_date}


# Post only uploads the file. Patch adds the meta data and creates the record
class NewPaper(Resource):
    method_decorators = [jwt_required]

    @marshal_with(
        {'title': fields.String, 'abstract': fields.String, 'md5': fields.String, 'authors': fields.List(AuthorMarshal),
         'date': fields.DateTime(dt_format='rfc822')})
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('file', type=werkzeug.datastructures.FileStorage, location='files')
        data = parser.parse_args()
        file_stream = data.file.stream
        content = file_stream.read()
        filename_md5 = calc_md5(content)
        exists = upload_to_s3(filename_md5, file_stream)
        metadata, expire = cache.get(filename_md5, expire_time=True)
        if not metadata:
            metadata = extract_paper_metadata(content)
            metadata['md5'] = filename_md5
            cache.set(filename_md5, metadata, expire=12 * 60 * 60)
        return metadata

    def patch(self):
        # TODO: add input validation
        current_user = get_jwt_identity()
        parser = reqparse.RequestParser()
        parser.add_argument('md5', type=str, required=True)
        parser.add_argument('title', type=str, required=True)
        parser.add_argument('date', type=lambda x: datetime.strptime(x, '%Y-%m-%dT%H:%M:%S.%fZ'), required=True, dest="time_published")
        parser.add_argument('abstract', type=str, required=True, dest="summary")
        parser.add_argument('authors', type=dict, required=True, action="append")
        data = parser.parse_args()
        add_user_data(data, 'uploaded_by')
        data['created_at'] = datetime.utcnow()
        data['is_private'] = True
        data['link'] = key_to_url(data['md5'], with_prefix=True) + '.pdf'
        paper = db_papers.insert_one(data)
        paper = db_papers.find_one({'_id': paper.inserted_id})
        for author in data.authors:
            db_authors.update({'_id': author},
                              {'$addToSet': {'papers': str(paper['_id'])}}, True)
        add_to_library('save', current_user, paper)
        return {'paper_id': str(paper['_id'])}


api.add_resource(NewPaper, "/add")
