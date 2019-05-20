import logging
import os

import pymongo
from datetime import datetime

from tasks.fetch_papers import fetch_entry
from .s3_utils import arxiv_to_s3
from .paper_query_utils import include_stats
from .latex_utils import extract_data_from_latex
from . import db_papers, db_comments
from bson import ObjectId
from flask import Blueprint
from flask_jwt_extended import jwt_optional, get_jwt_identity
from flask_restful import Resource, Api, reqparse, abort, fields, marshal_with
import uuid

from routes.user import find_by_email

app = Blueprint('paper', __name__)
api = Api(app)
logger = logging.getLogger(__name__)


MAX_ITEMS = 20

tot_votes = 0
last_reddit_update = None


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


def abs_to_pdf(url):
    return url.replace('abs', 'pdf').replace('http', 'https') + '.pdf'


paper_fields = {
    'url': fields.String(attribute='pdf_link'),
    'saved_in_library': fields.Boolean,
    'title': fields.String,
}


class Paper(Resource):
    method_decorators = [jwt_optional]

    @marshal_with(paper_fields)
    def get(self, paper_id):
        paper = db_papers.find_one(paper_id)
        if not paper:
            # Fetch from arxiv
            paper = fetch_entry(paper_id)
            paper['_id'] = paper['id']
            if not paper:
                abort(404, message='Paper not found')
        pdf_url = abs_to_pdf(paper['link'])

        if os.environ.get('S3_BUCKET_NAME'):
            pdf_url = arxiv_to_s3(pdf_url)

        paper['pdf_link'] = pdf_url
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


def add_metadata(comments):
    current_user = get_jwt_identity()

    def add_single_meta(comment):
        comment['canEdit'] = (current_user and current_user == comment['user'].get('email', -1))
        if comment['visibility'] == 'anonymous':
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


class PaperSection(Resource):
    method_decorators = [jwt_optional]

    def get(self, paper_id):
        paper = db_papers.find_one(paper_id)
        if not paper:
            abort(404, message='Paper not found')
        sections = paper.get('sections')
        if not sections:
            try:
                sections = extract_data_from_latex(paper_id)
                db_papers.update({'_id': paper_id}, {"$set": {'sections': sections}})
            except Exception as e:
                logger.error(f'Failed to retrieve sections for {paper_id} - {e}')
                abort(500, message='Failed to retrieve sections')
        return sections


api.add_resource(Comments, "/<paper_id>/comments")
api.add_resource(PaperSection, "/<paper_id>/sections")
api.add_resource(NewComment, "/<paper_id>/new_comment")
api.add_resource(Comment, "/<paper_id>/comment/<comment_id>")
api.add_resource(Reply, "/<paper_id>/comment/<comment_id>/reply")
api.add_resource(Paper, "/<paper_id>")





