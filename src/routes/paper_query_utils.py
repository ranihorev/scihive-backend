import datetime
import logging
import os
from typing import List

from flask_jwt_extended import get_jwt_identity
from sqlalchemy import or_
from .s3_utils import arxiv_to_s3
from flask_restful import reqparse, fields, abort
from src.new_backend.models import Paper, db
from src.new_backend.scrapers.arxiv import fetch_entry

logger = logging.getLogger(__name__)

SCORE_META = {'$meta': 'textScore'}

PUBLIC_TYPES = ['public', 'anonymous']


paper_with_code_fields = {
    'github': fields.String(attribute='github_link'),
    'stars': fields.Integer(attribute='stars'),
    'paperswithcode': fields.String(attribute='link')
}


def abs_to_pdf(url):
    return url.replace('abs', 'pdf').replace('http', 'https') + '.pdf'


def get_paper_or_none(paper_id: str):
    query = [Paper.original_id == paper_id]
    try:
        query.append(Paper.id == int(paper_id))
    except:
        pass
    paper = Paper.query.filter(or_(*query)).first()
    return paper


def get_paper_or_404(paper_id: str):
    paper = get_paper_or_none(paper_id)
    if not paper:
        abort(404, message='Paper not found')
    return paper


def get_paper_with_pdf(paper_id):
    paper = get_paper_or_none(paper_id)
    if not paper:
        # Fetch from arxiv
        fetch_entry(paper_id)
        paper = get_paper_or_404(paper_id)

    if not paper.local_pdf:
        # TODO: expand this method to any source
        if not os.environ.get('S3_BUCKET_NAME'):
            logger.error('S3 Bucket name is missing')
        paper.local_pdf = arxiv_to_s3(paper.original_pdf)
        db.session.commit()

    return paper
