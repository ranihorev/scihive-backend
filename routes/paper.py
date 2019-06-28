import logging
import pymongo
from datetime import datetime

from .acronym_extractor import extract_acronyms, ACRONYM_VERSION
from .paper_query_utils import include_stats, get_paper_with_pdf
from .latex_utils import extract_references_from_latex, REFERNCES_VERSION
from . import db_papers, db_comments, db_acronyms
from bson import ObjectId
from flask import Blueprint
from flask_jwt_extended import jwt_optional, get_jwt_identity
from flask_restful import Resource, Api, reqparse, abort, fields, marshal_with
import uuid
from enum import Enum

from routes.user import find_by_email

app = Blueprint('paper', __name__)
api = Api(app)
logger = logging.getLogger(__name__)

tot_votes = 0
last_reddit_update = None


class ItemState(Enum):
    existing = 1
    updated = 2
    new = 3


def visibilityObj(obj):
    choices = ('public', 'private', 'anonymous', 'group')
    vis_type = obj.get('type')
    if vis_type not in choices:
        raise ValueError('Visibility value is incorrect')
    if vis_type == 'group' and not obj.get('id'):
        raise ValueError('Group id is missing')
    return obj


new_comment_parser = reqparse.RequestParser()
new_comment_parser.add_argument('comment', help='This field cannot be blank', type=dict, location='json', required=False)
new_comment_parser.add_argument('content', help='This field cannot be blank', type=dict, location='json', required=True)
new_comment_parser.add_argument('position', help='This field cannot be blank', type=dict, location='json', required=True)
new_comment_parser.add_argument('visibility', help='This field cannot be blank', type=visibilityObj, location='json', required=True)

edit_comment_parser = reqparse.RequestParser()
edit_comment_parser.add_argument('comment', help='This field cannot be blank', type=str, location='json', required=False)

new_reply_parser = reqparse.RequestParser()
new_reply_parser.add_argument('text', help='This field cannot be blank', type=str, location='json', required=True)


def add_user_data(data):
    current_user = get_jwt_identity()
    if current_user:
        current_user = find_by_email(current_user)
        data['user'] = {'email': current_user['email'], 'username': current_user['username']}
    else:
        data['user'] = {'username': 'Guest'}


paper_fields = {
    'url': fields.String(attribute='pdf_link'),
    'saved_in_library': fields.Boolean,
    'title': fields.String,
}


class Paper(Resource):
    method_decorators = [jwt_optional]

    @marshal_with(paper_fields)
    def get(self, paper_id):
        paper = get_paper_with_pdf(paper_id)
        paper = include_stats([paper], user=get_jwt_identity())[0]

        return paper


replies_fields = {
    'id': fields.String,
    'user': fields.String(attribute='user.username'),
    'text': fields.String,
    'createdAt': fields.DateTime(dt_format='rfc822', attribute='created_at'),
}


class UsernameField(fields.Raw):
    def format(self, obj):
        return ''


class VisibilityField(fields.Raw):
    def format(self, obj):
        if isinstance(obj, dict):
            return obj.get('type', 'public')
        return obj


comment_fields = {
    'id': fields.String(attribute='_id'),
    'content': fields.Raw,
    'comment': fields.Raw,
    'position': fields.Raw,
    'user': fields.String(attribute='user.username'),
    'canEdit': fields.Boolean(),
    'createdAt': fields.DateTime(dt_format='rfc822', attribute='created_at'),
    'replies': fields.List(fields.Nested(replies_fields)),
    'visibility': VisibilityField,
}


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


PUBLIC_TYPES = ['public', 'anonymous']


class Comments(Resource):
    method_decorators = [jwt_optional]

    @marshal_with(comment_fields, envelope='comments')
    def get(self, paper_id):
        current_user = get_jwt_identity()
        user_filter = [{'user.email': current_user}] if current_user else []
        parser = reqparse.RequestParser()
        parser.add_argument('group', required=False)
        group_id = parser.parse_args().get('group')
        if group_id:
            visibility_filter = {'$or': [{'visibility.id': group_id}] + user_filter}
        else:
            visibility_filter = {'$or': [{'visibility.type': {'$in': PUBLIC_TYPES}}, {'visibility': {'$in': PUBLIC_TYPES}}, ] + user_filter}
        comments = list(db_comments.find({'$and': [{'pid': paper_id}, visibility_filter]}).sort([
            ('position.pageNumber', pymongo.ASCENDING),
            ('position.boundingRect.y1', pymongo.ASCENDING)]))
        add_metadata(comments)
        return comments


class NewComment(Resource):
    method_decorators = [jwt_optional]

    @marshal_with(comment_fields, envelope='comment')
    def post(self, paper_id):
        # TODO Validate paper id
        data = new_comment_parser.parse_args()
        data['pid'] = paper_id
        data['created_at'] = datetime.utcnow()
        add_user_data(data)
        visibility = data['visibility']
        if visibility['type'] != 'public' and not get_jwt_identity():
            abort(401, message='Please log in to submit non-public comments')

        comment = db_comments.insert_one(data)
        data['id'] = str(comment.inserted_id)
        add_metadata(data)
        return data


class Comment(Resource):
    method_decorators = [jwt_optional]

    def _get_comment(self, comment_id):
        current_user = get_jwt_identity()
        if not current_user:
            abort(401, messsage='Unauthorized to delete')
        comment = db_comments.find_one(comment_id)
        if not comment:
            abort(404, messsage='Comment not found')

        if not 'user' in comment or comment['user']['email'] != current_user:
            abort(401, messsage='Unauthorized to delete')
        return comment

    @marshal_with(comment_fields, envelope='comment')
    def patch(self, paper_id, comment_id):
        comment_id = {'_id': ObjectId(comment_id)}
        self._get_comment(comment_id)
        data = edit_comment_parser.parse_args()
        new_values = {"$set": {'comment.text': data['comment']}}
        db_comments.update_one(comment_id, new_values)
        comment = db_comments.find_one(comment_id)
        add_metadata(comment)
        return comment

    def delete(self, paper_id, comment_id):
        comment_id = {'_id': ObjectId(comment_id)}
        self._get_comment(comment_id)
        # TODO Add error handling
        db_comments.delete_one(comment_id)
        return {'message': 'success'}


class Reply(Resource):
    method_decorators = [jwt_optional]

    def _get_comment(self, comment_id):
        comment = db_comments.find_one(comment_id)
        if not comment:
            abort(404, messsage='Comment not found')
        return comment

    @marshal_with(comment_fields, envelope='comment')
    def post(self, paper_id, comment_id):
        comment_id = {'_id': ObjectId(comment_id)}
        self._get_comment(comment_id)
        data = new_reply_parser.parse_args()
        data['created_at'] = datetime.utcnow()
        data['id'] = str(uuid.uuid4())
        add_user_data(data)
        new_values = {"$push": {'replies': data}}
        db_comments.update_one(comment_id, new_values)
        comment = self._get_comment(comment_id)
        add_metadata(comment)
        return comment


def get_paper_item(paper_id, item, latex_fn, version=None):
    paper = db_papers.find_one(paper_id)
    state = ItemState.existing
    if not paper:
        abort(404, message='Paper not found')
    new_value = old_value = paper.get(item)
    if not old_value or (version is not None and float(old_value.get('version', 0)) < version):
        state = ItemState.new if not old_value else ItemState.updated
        try:
            new_value = latex_fn(paper_id)
            db_papers.update({'_id': paper_id}, {"$set": {item: new_value}})
        except Exception as e:
            logger.error(f'Failed to retrieve {item} for {paper_id} - {e}')
            abort(500, message=f'Failed to retrieve {item}')
    return new_value, old_value, state


class PaperReferences(Resource):
    method_decorators = [jwt_optional]

    def get(self, paper_id):
        references, _, _ = get_paper_item(paper_id, 'references', extract_references_from_latex, REFERNCES_VERSION)
        return references['data']


class PaperAcronyms(Resource):
    method_decorators = [jwt_optional]

    def _update_acronyms_counter(self, acronyms, inc_value=1):
        for short_form, long_form in acronyms.items():
            db_acronyms.update({'short_form': short_form}, {'$inc': {f'long_form.{long_form}': inc_value}}, True)

    def _enrich_matches(self, matches, short_forms):
        additional_matches = db_acronyms.find({"short_form": {"$in": short_forms}})
        for m in additional_matches:
            cur_short_form = m.get('short_form')
            if m.get('verified'):
                matches[cur_short_form] = m.get('verified')
            elif cur_short_form in matches:
                pass
            else:
                long_forms = m.get('long_form')
                if long_forms:
                    most_common = max(long_forms, key=long_forms.get)
                    matches[cur_short_form] = most_common
        return matches

    def get(self, paper_id):
        new_acronyms, old_acronyms, state = get_paper_item(paper_id, 'acronyms', extract_acronyms)
        if state == ItemState.new:
            self._update_acronyms_counter(new_acronyms["matches"])
        elif state == ItemState.updated:
            self._update_acronyms_counter(old_acronyms["matches"], -1)
            self._update_acronyms_counter(new_acronyms["matches"], 1)
        matches = self._enrich_matches(new_acronyms['matches'], new_acronyms['short_forms'])
        return matches


api.add_resource(PaperAcronyms, "/<paper_id>/acronyms")
api.add_resource(Comments, "/<paper_id>/comments")
api.add_resource(PaperReferences, "/<paper_id>/references")
api.add_resource(NewComment, "/<paper_id>/new_comment")
api.add_resource(Comment, "/<paper_id>/comment/<comment_id>")
api.add_resource(Reply, "/<paper_id>/comment/<comment_id>/reply")
api.add_resource(Paper, "/<paper_id>")





