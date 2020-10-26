import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import urlparse

import requests
import werkzeug
from flask import Blueprint
from flask_jwt_extended import jwt_required
from flask_restful import Api, Resource, abort, fields, marshal_with, reqparse

from ..models import Collection, MetadataState, Paper, User, db
from ..scrapers.arxiv import fetch_entry
from ..scrapers.utils import parse_arxiv_url
from .file_utils import get_uploader
from .user_utils import get_user_by_email

app = Blueprint('new_paper', __name__)
api = Api(app)
logger = logging.getLogger(__name__)


# Post only uploads the file. Patch adds the meta data and creates the record
class NewPaper(Resource):
    method_decorators = [jwt_required]

    def _handle_non_arxiv_paper(self, data, user: User):
        upload_via = 'link' if bool(data.link) else 'file'
        logger.info(f'Uploading private paper via {upload_via}')
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
        _, file_hash, pdf_link = get_uploader().upload_from_file(file_stream)
        logger.info(f'Uploaded file {pdf_link}')

        # Create paper
        time_now = datetime.now()
        paper = Paper(title='Untitled', original_pdf=pdf_link, local_pdf=pdf_link, publication_date=time_now,
                      last_update_date=time_now, is_private=True, original_id=file_hash, uploaded_by_id=user.id,
                      metadata_state=MetadataState.missing)
        db.session.add(paper)
        db.session.commit()
        return paper

    def _handle_arxiv_paper(self, link: str, user: User):
        logger.info('Uploading private paper from arxiv')
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

        logger.info('Paper created successfully')
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
