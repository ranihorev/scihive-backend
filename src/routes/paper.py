import logging
from datetime import datetime
from enum import Enum

from flask import Blueprint
from flask_jwt_extended import get_jwt_identity, jwt_optional, jwt_required
from flask_restful import Api, Resource, abort, fields, marshal_with, reqparse

from src.new_backend.models import Author, Collection, Paper, db

from .acronym_extractor import extract_acronyms
from .latex_utils import REFERENCES_VERSION, extract_references_from_latex
from .paper_query_utils import (Github, get_paper_with_pdf)
from .user_utils import get_user
from src.routes.s3_utils import key_to_url

app = Blueprint('paper', __name__)
api = Api(app)
logger = logging.getLogger(__name__)


class ItemState(Enum):
    existing = 1
    updated = 2
    new = 3


paper_fields = {
    'id': fields.String,
    'url': fields.String(attribute='local_pdf'),
    'title': fields.String,
    'authors': fields.Nested({'name': fields.String}),
    'time_published': fields.DateTime(attribute='publication_date', dt_format='rfc822'),
    'abstract': fields.String,
    'code': Github(attribute='code'),
    'groups': fields.Nested({'id': fields.Integer, 'name': fields.String}),
    'is_editable': fields.Boolean(attribute='is_private', default=False)
}


class PaperResource(Resource):
    method_decorators = [jwt_optional]

    @marshal_with(paper_fields)
    def get(self, paper_id):
        current_user = get_jwt_identity()
        paper = get_paper_with_pdf(paper_id)
        if current_user:
            user = get_user()
            paper.groups = Collection.query.filter(Collection.users.any(
                id=user.id), Collection.papers.any(id=paper.id)).all()
        return paper


def get_visibility(comment):
    if isinstance(comment['visibility'], dict):
        return comment['visibility'].get('type', '')
    return comment['visibility']


def add_metadata(comments):
    current_user = get_jwt_identity()

    def add_single_meta(comment):
        comment['canEdit'] = (current_user and current_user == comment['user'].get('email', -1))
        if get_visibility(comment) == 'anonymous':
            comment['user']['username'] = 'Anonymous'

    if isinstance(comments, list):
        for c in comments:
            add_single_meta(c)
    else:
        add_single_meta(comments)


def get_paper_item(paper, item, latex_fn, version=None, force_update=False):
    state = ItemState.existing
    if not paper:
        abort(404, message='Paper not found')
    new_value = old_value = getattr(paper, item)

    if force_update or not old_value or (version is not None and float(old_value.get('version', 0)) < version):
        state = ItemState.new if not old_value else ItemState.updated

        try:
            new_value = latex_fn(paper.original_id)
            setattr(paper, item, new_value)
        except Exception as e:
            logger.error(f'Failed to retrieve {item} for {paper.id} - {e}')
            abort(500, message=f'Failed to retrieve {item}')
    return new_value, old_value, state


class PaperReferencesResource(Resource):
    method_decorators = [jwt_optional]

    def get(self, paper_id):
        query_parser = reqparse.RequestParser()
        query_parser.add_argument('force', type=str, required=False)
        paper = Paper.query.get_or_404(paper_id)

        # Rani: how to address private papers?
        if paper.is_private:
            return []

        force_update = bool(query_parser.parse_args().get('force'))
        references, _, _ = get_paper_item(paper, 'references', extract_references_from_latex, REFERENCES_VERSION,
                                          force_update=force_update)
        return references['data']


# class PaperAcronymsResource(Resource):
#     method_decorators = [jwt_optional]

#     def _update_acronyms_counter(self, acronyms, inc_value=1):
#         for short_form, long_form in acronyms.items():
#             db_acronyms.update({'short_form': short_form}, {'$inc': {f'long_form.{long_form}': inc_value}}, True)

#     def _enrich_matches(self, matches, short_forms):
#         additional_matches = db_acronyms.find({"short_form": {"$in": short_forms}})
#         for m in additional_matches:
#             cur_short_form = m.get('short_form')
#             if m.get('verified'):
#                 matches[cur_short_form] = m.get('verified')
#             elif cur_short_form in matches:
#                 pass
#             else:
#                 long_forms = m.get('long_form')
#                 if long_forms:
#                     most_common = max(long_forms,
#                                       key=(lambda key: long_forms[key] if isinstance(long_forms[key], int) else 0))
#                     matches[cur_short_form] = most_common
#         return matches

#     def get(self, paper_id):
#         new_acronyms, old_acronyms, state = get_paper_item(paper_id, 'acronyms', extract_acronyms)
#         if state == ItemState.new:
#             self._update_acronyms_counter(new_acronyms["matches"])
#         elif state == ItemState.updated:
#             self._update_acronyms_counter(old_acronyms["matches"], -1)
#             self._update_acronyms_counter(new_acronyms["matches"], 1)
#         matches = self._enrich_matches(new_acronyms['matches'], new_acronyms['short_forms'])
#         return matches


class EditPaperResource(Resource):
    method_decorators = [jwt_required]

    @marshal_with(paper_fields)
    def post(self):
        current_user = get_jwt_identity()
        parser = reqparse.RequestParser()
        parser.add_argument('id', type=str, required=False)
        parser.add_argument('title', type=str, required=True)
        parser.add_argument('date', type=lambda x: datetime.strptime(x, '%Y-%m-%dT%H:%M:%S.%fZ'), required=True,
                            dest="publication_date")
        parser.add_argument('md5', type=str, required=False)
        parser.add_argument('abstract', type=str, required=True)
        parser.add_argument('authors', type=str, required=True, action="append")
        paper_data = parser.parse_args()

        if 'id' not in paper_data and 'md5' not in paper_data:
            abort(403)

        # If the paper didn't exist in our database (or it's a new version), we add it
        paper = db.session.query(Paper).filter(Paper.id == paper_data['id']).first()

        paper_data['pdf_link'] = key_to_url(paper_data['md5'], with_prefix=True) + '.pdf'
        paper_data['last_update_date'] = datetime.utcnow()
        paper_data['is_private'] = True

        if not paper:
            paper = Paper(title=paper_data['title'], pdf_link=paper_data['pdf_link'], publication_date=paper_data['publication_date'],
                          abstract=paper_data['abstract'], last_update_date=paper_data['last_update_date'], is_private=paper_data['is_private'])
            db.session.add(paper)
        else:
            paper.title = paper_data['title']
            paper.pdf_link = paper_data['pdf_link']
            paper.publication_date = paper_data['publication_date']
            paper.abstract = paper_data['abstract']

        for author_name in paper_data['authors']:
            existing_author = db.session.query(Author).filter(Author.name == author_name).first()

            if not existing_author:
                new_author = Author(name=author_name)
                new_author.papers.append(paper)
                db.session.add(new_author)

        db.session.commit()

        return {'paper_id': str(paper.id)}


# api.add_resource(PaperAcronymsResource, "/<paper_id>/acronyms")
# Done (untested)
api.add_resource(PaperResource, "/<paper_id>")
api.add_resource(PaperReferencesResource, "/<paper_id>/references")
api.add_resource(EditPaperResource, "/edit")
