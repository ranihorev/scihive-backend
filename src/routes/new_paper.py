import io
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
from flask_restful import Resource, Api, reqparse, marshal_with, fields, abort
from typing import NamedTuple, List, Tuple

from .s3_utils import upload_to_s3, key_to_url, calc_md5
from src.new_backend.models import Author, Collection, Paper, db
from src.routes.user_utils import get_user
from sqlalchemy.orm.exc import NoResultFound

app = Blueprint('new_paper', __name__)
api = Api(app)
logger = logging.getLogger(__name__)


def get_tag_text(tree, tag, default_value='') -> str:
    element = tree.find(f'.//{tag}')
    return element.text if element is not None else default_value


def get_all_tag_texts(tree, tag):
    element = tree.findall(f'.//{tag}')
    return [e.text for e in element]


class AuthorObj(NamedTuple):
    first_name: str
    last_name: str
    org: List[str]

    def get_name(self):
        return f'{self.first_name} {self.last_name}'


class AuthorMarshal(fields.Raw):
    def format(self, value):
        return {'name': value.get_name()}


def extract_paper_metadata(file_content) -> Tuple[str, List[AuthorObj], str]:
    try:
        grobid_res = requests.post('http://cloud.science-miner.com/grobid/api/processHeaderDocument',
                                   data={'consolidateHeader': 1}, files={'input': file_content})
        if grobid_res.status_code == 503:
            raise Exception('Grobid is unavailable')
        content = re.sub(' xmlns="[^"]+"', '', grobid_res.text)
        tree = ET.fromstring(content)
    except Exception as e:
        logger.error(f'Failed to extract metadata for paper - {e}')
        return False, {'title': '', 'authors': [], 'abstract': '', 'date': datetime.now()}

    title = get_tag_text(tree, 'title')

    authors_tree = tree.findall('.//author')
    authors: List[AuthorObj] = []
    for author_tree in authors_tree:
        author = AuthorObj(first_name=get_tag_text(author_tree, 'forename'),
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

    return True, {'title': title or '', 'authors': authors, 'abstract': abstract, 'date': publish_date}


# Post only uploads the file. Patch adds the meta data and creates the record
class NewPaper(Resource):
    method_decorators = [jwt_required]

    @marshal_with({'id': fields.String})
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('file', type=werkzeug.datastructures.FileStorage, location='files')
        parser.add_argument('link', type=str)
        data = parser.parse_args()
        if not data.file and not data.link:
            abort(401, messsage='Missing content')

        if data.link:
            res = requests.get(data.link)
            file_stream = io.BytesIO(res.content)
        else:
            file_stream = data.file.stream

        # Upload to s3
        content = file_stream.read()
        filename_md5 = calc_md5(content)
        upload_to_s3(filename_md5, file_stream)

        # get paper meta data
        metadata, expire = cache.get(filename_md5, expire_time=True)
        if not metadata:
            success, metadata = extract_paper_metadata(content)
            metadata['md5'] = filename_md5
            if success:
                cache.set(filename_md5, metadata, expire=24 * 60 * 60)

        # Create paper
        pdf_link = key_to_url(metadata['md5'], with_prefix=True) + '.pdf'
        paper = Paper(title=metadata['title'], original_pdf=pdf_link, local_pdf=pdf_link, publication_date=metadata['date'],
                      abstract=metadata['abstract'], last_update_date=datetime.now(), is_private=True)
        db.session.add(paper)

        # Create authors
        for current_author in metadata['authors']:
            try:
                author = Author.query.filter(
                    Author.first_name == current_author.first_name, Author.last_name == current_author.last_name).one()
            except NoResultFound:
                author = Author(name=f'{current_author.first_name} {current_author.last_name}',
                                first_name=current_author.first_name, last_name=current_author.last_name, organization=current_author.org)
                db.session.add(author)
            author.papers.append(paper)

        user = get_user()
        # Check if user has a collection for uploads (and that they are still in that group)
        uploads_collection = Collection.query.filter(
            Collection.created_by_id == user.id, Collection.users.any(id=user.id), Collection.is_uploads == True).first()
        if not uploads_collection:
            # Create
            uploads_collection = Collection(creation_date=datetime.utcnow(),
                                            name="Uploads", created_by_id=user.id, is_uploads=True)
            uploads_collection.users.append(user)

        uploads_collection.papers.append(paper)
        db.session.commit()

        return {'id': paper.id}


api.add_resource(NewPaper, "/add")
