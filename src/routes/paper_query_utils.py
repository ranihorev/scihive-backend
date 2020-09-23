import datetime
import logging
import os
from src.routes.user_utils import get_user_optional
from typing import List
from flask_jwt_extended.utils import get_jwt_identity

from flask_restful import abort, fields, reqparse
from sqlalchemy import or_

from src.new_backend.models import Collection, Paper, Permission, User, db
from src.new_backend.scrapers.arxiv import fetch_entry

from .s3_utils import arxiv_to_s3

logger = logging.getLogger(__name__)

SCORE_META = {'$meta': 'textScore'}

PUBLIC_TYPES = ['public', 'anonymous']


paper_with_code_fields = {
    'github': fields.String(attribute='github_link'),
    'stars': fields.Integer(attribute='stars'),
    'paperswithcode': fields.String(attribute='link')
}

paper_list_item_fields = {
    'id': fields.String,
    'title': fields.String,
    'authors': fields.Nested({'name': fields.String}),
    'time_published': fields.DateTime(dt_format='rfc822', attribute="publication_date"),
    'abstract': fields.String(attribute="abstract"),
    'groups': fields.Raw(attribute='collection_ids', default=[]),
    'twitter_score': fields.Integer,
    'num_stars': fields.Integer,
    'code': fields.Nested(paper_with_code_fields, attribute='paper_with_code', allow_null=True),
    'comments_count': fields.Integer
}


def has_permissions_to_paper(paper: Paper, user: User) -> bool:
    return Permission.query.filter(Permission.paper_id == paper.id, Permission.user_id == User.id).first()


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


def get_paper_with_pdf(paper_id) -> Paper:
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


def add_groups_to_paper(paper: Paper):
    if get_jwt_identity():
        user = get_user_optional()
        paper.groups = db.session.query(Collection.id).filter(Collection.users.any(
            id=user.id), Collection.papers.any(id=paper.id)).all()
