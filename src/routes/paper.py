import logging
from datetime import datetime
from enum import Enum

import pytz
from flask import Blueprint
from flask_jwt_extended import get_jwt_identity, jwt_optional, jwt_required
from flask_restful import Api, Resource, abort, fields, marshal_with, reqparse

from src.new_backend.models import Author, Collection, Paper, db
from src.routes.s3_utils import key_to_url

from .acronym_extractor import extract_acronyms
from .latex_utils import REFERENCES_VERSION, extract_references_from_latex
from .paper_query_utils import get_paper_with_pdf, paper_with_code_fields
from .user_utils import get_user

app = Blueprint('paper', __name__)
api = Api(app)
logger = logging.getLogger(__name__)


paper_fields = {
    'id': fields.String,
    'url': fields.String(attribute='local_pdf'),
    'title': fields.String,
    'authors': fields.Nested({'name': fields.String, 'id': fields.String}),
    'time_published': fields.DateTime(attribute='publication_date', dt_format='rfc822'),
    'abstract': fields.String,
    'code': fields.Nested(paper_with_code_fields, attribute='paper_with_code', allow_null=True),
    'groups': fields.Nested({'id': fields.Integer, 'name': fields.String}),
    'is_editable': fields.Boolean(attribute='is_private', default=False)
}


class ItemState(Enum):
    existing = 1
    updated = 2
    new = 3


def add_groups_to_paper(paper: Paper):
    user = get_user()
    if user:
        paper.groups = Collection.query.filter(Collection.users.any(
            id=user.id), Collection.papers.any(id=paper.id)).all()


class PaperResource(Resource):
    method_decorators = [jwt_optional]

    @marshal_with(paper_fields)
    def get(self, paper_id):
        paper = get_paper_with_pdf(paper_id)
        add_groups_to_paper(paper)
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

def validateAuthor(value):
    if not isinstance(value, dict):
        raise TypeError('Author must be an object')
    if not value.get('name'):
        raise ValueError('Author name is missing')
    return value


class EditPaperResource(Resource):
    method_decorators = [jwt_required]

    @marshal_with(paper_fields)
    def post(self, paper_id):
        current_user = get_jwt_identity()
        parser = reqparse.RequestParser()
        parser.add_argument('title', type=str, required=True)
        parser.add_argument('date', type=lambda x: datetime.strptime(x, '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=pytz.UTC), required=True,
                            dest="publication_date")
        parser.add_argument('abstract', type=str, required=True)
        parser.add_argument('authors', type=validateAuthor, required=False, action="append")
        parser.add_argument('removed_authors', type=str, required=False, action="append", default=[])
        paper_data = parser.parse_args()

        paper = Paper.query.get_or_404(paper_id)

        if not paper.is_private:
            abort(403, 'Only uploaded papers can be edited')

        paper.last_update_date = datetime.utcnow()

        paper.title = paper_data['title']
        paper.publication_date = paper_data['publication_date']
        paper.abstract = paper_data['abstract']

        for author_id in paper_data['removed_authors']:
            author = Author.query.get(author_id)
            paper.authors.remove(author)

        for author_data in (paper_data.get('authors') or []):
            author_name = author_data.get('name')
            author_id = author_data.get('id')
            if author_id:
                author = Author.query.get_or_404(author_id)
                author.name = author_name
            else:
                new_author = Author(name=author_name)
                new_author.papers.append(paper)
                db.session.add(new_author)

        db.session.commit()
        add_groups_to_paper(paper)
        return paper


# api.add_resource(PaperAcronymsResource, "/<paper_id>/acronyms")
# Done (untested)
api.add_resource(PaperResource, "/<paper_id>")
api.add_resource(PaperReferencesResource, "/<paper_id>/references")
api.add_resource(EditPaperResource, "/<paper_id>/edit")
