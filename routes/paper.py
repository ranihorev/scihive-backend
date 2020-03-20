import logging
import pymongo
from datetime import datetime

from routes.query_utils import fix_paper_id
from .user_utils import add_user_data, find_by_email
from .acronym_extractor import extract_acronyms
from .paper_query_utils import include_stats, get_paper_with_pdf, Github, get_paper_by_id, PUBLIC_TYPES
from .latex_utils import extract_references_from_latex, REFERENCES_VERSION
from . import db_papers, db_comments, db_acronyms, db_group_papers
from bson import ObjectId
from flask import Blueprint
from flask_jwt_extended import jwt_optional, get_jwt_identity, jwt_required
from flask_restful import Resource, Api, reqparse, abort, fields, marshal_with
import uuid
from enum import Enum

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


EMPTY_FIELD_MSG = 'This field cannot be blank'

new_reply_parser = reqparse.RequestParser()
new_reply_parser.add_argument('text', help='This field cannot be blank', type=str, location='json', required=True)

paper_fields = {
    'url': fields.String(attribute='pdf_link'),
    'saved_in_library': fields.Boolean,
    'title': fields.String,
    'authors': fields.Nested({'name': fields.String}),
    'time_published': fields.DateTime(dt_format='rfc822'),
    'summary': fields.String,
    'code': Github(attribute='code'),
    'groups': fields.Raw,
    'is_editable': fields.Boolean(attribute='is_private', default=False)
}


class Paper(Resource):
    method_decorators = [jwt_optional]

    @marshal_with(paper_fields)
    def get(self, paper_id):
        current_user = get_jwt_identity()
        paper = get_paper_with_pdf(paper_id)
        paper['groups'] = []
        if current_user:
            user = find_by_email(current_user, {"_id": 1})
            paper['groups'] = list(db_group_papers.find({'paper_id': fix_paper_id(paper_id), 'user': str(user['_id'])}, {'group_id': 1, 'is_library': 1}))
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
            return obj;
        return {'type': obj}


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
    'isGeneral': fields.Boolean,
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
            visibility_filter = {'$or': [{'visibility.type': {'$in': PUBLIC_TYPES}},
                                         {'visibility': {'$in': PUBLIC_TYPES}}, ] + user_filter}
        comments = list(db_comments.find({'$and': [{'pid': paper_id}, visibility_filter]}))
        add_metadata(comments)
        return comments


class NewComment(Resource):
    method_decorators = [jwt_optional]

    @marshal_with(comment_fields, envelope='comment')
    def post(self, paper_id):
        # TODO Validate paper id
        new_comment_parser = reqparse.RequestParser()
        new_comment_parser.add_argument('comment', help=EMPTY_FIELD_MSG, type=dict, location='json')
        new_comment_parser.add_argument('content', help=EMPTY_FIELD_MSG, type=dict, location='json')
        new_comment_parser.add_argument('position', type=dict, location='json')
        new_comment_parser.add_argument('isGeneral', type=bool, location='json')
        new_comment_parser.add_argument('visibility', help=EMPTY_FIELD_MSG, type=visibilityObj, location='json',
                                        required=True)
        data = new_comment_parser.parse_args()
        isGeneral = data['isGeneral'] is not None
        if not isGeneral and (data['position'] is None or data['content'] is None):
            abort(401, message='position or content are missing for non-general comment')

        if isGeneral:
            del data['position']
            del data['content']
        else:
            del data['isGeneral']

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
            abort(401, messsage='Unauthorized to get comment')
        comment = db_comments.find_one(comment_id)
        if not comment:
            abort(404, messsage='Comment not found')

        if not 'user' in comment or comment['user']['email'] != current_user:
            abort(401, messsage='Unauthorized to get comment')
        return comment

    @marshal_with(comment_fields, envelope='comment')
    def patch(self, paper_id, comment_id):
        comment_id = {'_id': ObjectId(comment_id)}
        self._get_comment(comment_id)
        edit_comment_parser = reqparse.RequestParser()
        edit_comment_parser.add_argument('comment', help=EMPTY_FIELD_MSG, type=str, location='json', required=False)
        edit_comment_parser.add_argument('visibility', help=EMPTY_FIELD_MSG, type=visibilityObj, location='json',
                                         required=True)
        data = edit_comment_parser.parse_args()
        new_values = {"$set": {'comment.text': data['comment'], 'visibility': data['visibility']}}
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


def get_paper_item(paper_id, item, latex_fn, version=None, force_update=False):
    paper = get_paper_by_id(paper_id)
    state = ItemState.existing
    if not paper:
        abort(404, message='Paper not found')
    new_value = old_value = paper.get(item)
    if force_update or not old_value or (version is not None and float(old_value.get('version', 0)) < version):
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
        query_parser = reqparse.RequestParser()
        query_parser.add_argument('force', type=str, required=False)
        paper = get_paper_by_id(paper_id, {'is_private': 1})
        if paper.get('is_private'):
            return []
        force_update = bool(query_parser.parse_args().get('force'))
        references, _, _ = get_paper_item(paper_id, 'references', extract_references_from_latex, REFERENCES_VERSION,
                                          force_update=force_update)
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
                    most_common = max(long_forms,
                                      key=(lambda key: long_forms[key] if isinstance(long_forms[key], int) else 0))
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


class EditPaper(Resource):
    method_decorators = [jwt_required]

    @marshal_with(paper_fields)
    def post(self, paper_id):
        current_user = get_jwt_identity()
        parser = reqparse.RequestParser()
        parser.add_argument('title', type=str, required=True)
        parser.add_argument('date', type=lambda x: datetime.strptime(x, '%Y-%m-%dT%H:%M:%S.%fZ'), required=True,
                            dest="time_published")
        parser.add_argument('abstract', type=str, required=True, dest="summary")
        parser.add_argument('authors', type=dict, required=True, action="append")
        data = parser.parse_args()
        paper_id = fix_paper_id(paper_id)
        old_data = db_papers.find_one(paper_id, {'_id': 0, 'title': 1, 'time_published': 1, 'summary': 1, 'authors': 1})
        changes = {}
        for key in old_data:
            if data.get(key) != old_data.get(key):
                changes[key] = old_data.get(key)

        if changes:
            changes['stored_at'] = datetime.utcnow()
            changes['changed_by'] = current_user
            db_papers.update_one({'_id': fix_paper_id(paper_id)}, {'$set': data, '$push': {'history': changes}})
        resp = get_paper_with_pdf(paper_id)
        return resp


api.add_resource(EditPaper, "/<paper_id>/edit")
api.add_resource(PaperAcronyms, "/<paper_id>/acronyms")
api.add_resource(Comments, "/<paper_id>/comments")
api.add_resource(PaperReferences, "/<paper_id>/references")
api.add_resource(NewComment, "/<paper_id>/new_comment")
api.add_resource(Comment, "/<paper_id>/comment/<comment_id>")
api.add_resource(Reply, "/<paper_id>/comment/<comment_id>/reply")
api.add_resource(Paper, "/<paper_id>")
