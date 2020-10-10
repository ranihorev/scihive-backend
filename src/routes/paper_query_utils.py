import logging
from .user_utils import get_user_optional
from typing import List, Optional
from flask_jwt_extended.utils import get_jwt_identity

from flask_restful import abort, fields
from sqlalchemy import or_
from .file_utils import get_uploader

from ..models import Collection, Paper, Permission, User, db
from ..scrapers.arxiv import fetch_entry

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
    return Permission.query.filter(Permission.paper_id == paper.id, Permission.user_id == user.id).first()


def enforce_permissions_to_paper(paper: Paper, user: Optional[User]) -> bool:
    if not paper.is_private:
        return True
    if not user or (paper.uploaded_by_id != user.id and not has_permissions_to_paper(paper, user)):
        abort(403, message='Missing paper perimssions')
    return True


def abs_to_pdf(url):
    return url.replace('abs', 'pdf').replace('http', 'https') + '.pdf'


def get_paper_or_none(paper_id: str) -> Optional[Paper]:
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
        paper = fetch_entry(paper_id)
        if not paper:
            abort(404, message='Paper not found')

    if not paper.local_pdf:
        # TODO: expand this method to any source
        paper.local_pdf = get_uploader().upload_from_arxiv(paper.original_pdf)
        db.session.commit()

    return paper


def get_paper_user_groups(paper: Paper) -> List[Collection]:
    if get_jwt_identity():
        user = get_user_optional()
        return db.session.query(Collection.id).filter(Collection.users.any(
            id=user.id), Collection.papers.any(id=paper.id)).all()
    return []
