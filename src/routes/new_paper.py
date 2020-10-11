import logging
from ..scrapers.arxiv import fetch_entry
from ..scrapers.utils import parse_arxiv_url
import xml.etree.ElementTree as ET
import re
from datetime import datetime
from diskcache import Cache
import requests
import werkzeug
from flask import Blueprint
from flask_jwt_extended import jwt_required
from flask_restful import Resource, Api, reqparse, marshal_with, fields, abort
from typing import NamedTuple, List, Tuple, Any, Dict

from .file_utils import get_uploader
from ..models import Author, Collection, Paper, db, User
from .user_utils import get_user_by_email
from sqlalchemy.orm.exc import NoResultFound
from urllib.parse import urlparse

cache = Cache('cache')

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


def extract_paper_metadata(file_content) -> Tuple[bool, Dict[str, Any]]:
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

    def _handle_non_arxiv_paper(self, data, user: User):
        # Let's stream directly from the link instead of buffering the file
        if data.link:
            response = requests.get(data.link, stream=True)
            content_type = response.headers.get('content-type')
            file_stream = response.raw
        else:
            file_stream = data.file.stream
            content_type = data.file.content_type

        if 'application/pdf' not in content_type:
            abort(404, message='Invalid file type')

        # Upload the file
        file_content, file_hash, pdf_link = get_uploader().upload_from_file(file_stream)

        # get paper meta data
        metadata, _ = cache.get(file_hash, expire_time=True)
        if not metadata:
            success, metadata = extract_paper_metadata(file_content)
            if success:
                cache.set(file_hash, metadata, expire=24 * 60 * 60)

        # Create paper
        paper = Paper(title=metadata['title'], original_pdf=pdf_link, local_pdf=pdf_link, publication_date=metadata['date'],
                      abstract=metadata['abstract'], last_update_date=datetime.now(), is_private=True, original_id=file_hash, uploaded_by_id=user.id)
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
        return paper

    def _handle_arxiv_paper(self, link: str, user: User):
        try:
            paper_id, _ = parse_arxiv_url(link)
        except (AttributeError, ValueError):
            abort(404, message="Invalid link - Arxiv ID does not exist")

        paper = fetch_entry(paper_id)
        if not paper:
            abort(404, message='Invalid link - Failed to fetch file from Arxiv')

        paper.uploaded_by_id = user.id
        paper.is_private = True
        db.session.commit()

        return paper

    @marshal_with({'id': fields.String})
    def post(self):
        user = get_user_by_email()
        parser = reqparse.RequestParser()
        parser.add_argument('file', type=werkzeug.datastructures.FileStorage, location='files')
        parser.add_argument('link', type=str)
        data = parser.parse_args()
        if not data.file and not data.link:
            abort(401, messsage='Missing content')

        if data.link and 'arxiv.org' in urlparse(data.link).netloc:
            paper = self._handle_arxiv_paper(data.link, user)
        else:
            paper = self._handle_non_arxiv_paper(data, user)

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
