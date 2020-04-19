import pymongo
from datetime import datetime

from bson import ObjectId
from flask import Blueprint
import logging

from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_restful import Resource, reqparse, Api, fields, marshal_with

from src.new_backend.models import Collection, db
from .group_utils import get_group, add_user_to_group
from .user_utils import find_by_email, add_remove_group, get_user_by_email
from . import db_groups, db_users, db_group_papers

app = Blueprint('groups', __name__)
api = Api(app)
logger = logging.getLogger(__name__)


class Count(fields.Raw):
    def format(self, value):
        return len(value)


group_fields = {
    'id': fields.String(attribute='_id'),
    'name': fields.String,
    'created_at': fields.DateTime(dt_format='rfc822'),
    'color': fields.String,
}


def get_user_group_ids(current_user=None):
    if not current_user:
        current_user = get_jwt_identity()
    return find_by_email(current_user, fields={'groups': 1}).get('groups', [])


def get_user_groups():
    groups = get_user_group_ids()
    groups = db_groups.find({'_id': {'$in': [ObjectId(g) for g in groups]}}, {'users': 0}).sort('created_at',
                                                                                                pymongo.DESCENDING)
    return list(groups)


class Groups(Resource):
    method_decorators = [jwt_required]

    @marshal_with(group_fields)
    def get(self):
        return get_user_groups()

    @marshal_with(group_fields)
    def post(self):
        # Join to group in addition to getting the list
        current_user = get_jwt_identity()
        user_id = find_by_email(current_user, fields={'id': 1})

        parser = reqparse.RequestParser()
        parser.add_argument('id', help='This field cannot be blank', required=True)
        data = parser.parse_args()
        group, group_q = get_group(data['id'])
        if group and user_id['_id'] not in group.get('users', []):
            add_user_to_group(user_id_q=user_id, user_email=current_user, group_q=group_q)

        return get_user_groups()


class NewGroup(Resource):
    method_decorators = [jwt_required]

    @marshal_with(group_fields)
    def post(self):
        # UPGRADED
        current_user = get_jwt_identity()
        parser = reqparse.RequestParser()
        parser.add_argument('name', help='This field cannot be blank', required=True)
        parser.add_argument('color', required=False, type=str)
        data = parser.parse_args()
        user = get_user_by_email(current_user)
        collection = Collection(is_library=False, creation_date=datetime.utcnow(), name=data.get('name'),
                                color=data.get('color'), created_by=user.id)
        db.session.add(collection)
        db.session.commit()
        all_collections = Collection.query(Collection.users.has(user_id=user.id))
        return all_collections


extended_group_fields = dict(group_fields)
extended_group_fields['num_papers'] = fields.Integer


class Group(Resource):
    @marshal_with(extended_group_fields)
    def get(self, group_id: str):
        group, _ = get_group(group_id)
        group_papers = db_group_papers.find({'group_id': group_id})
        group['num_papers'] = group_papers.count()
        return group

    @jwt_required
    @marshal_with(group_fields)
    def delete(self, group_id: str):
        current_user = get_jwt_identity()
        user_id = find_by_email(current_user, fields={'id': 1})
        # Remove from user
        db_users.update_one(user_id, {'$pull': {'groups': ObjectId(group_id)}})

        # Remove from group
        group_id = {'_id': ObjectId(group_id)}
        db_groups.update_one(group_id, {'$pull': {'users': user_id['_id']}})
        return get_user_groups()

    @jwt_required
    @marshal_with(group_fields)
    def patch(self, group_id: str):
        current_user = get_jwt_identity()
        find_by_email(current_user, fields={'id': 1})
        # TODO check if created by the user?
        parser = reqparse.RequestParser()
        parser.add_argument('name', required=False, type=str)
        parser.add_argument('color', required=False, type=str)
        data = parser.parse_args()
        group, group_q = get_group(group_id)
        db_groups.update(group_q, {'$set': data})
        return get_user_groups()

    @jwt_required
    @marshal_with(group_fields)
    def post(self, group_id):
        current_user = get_jwt_identity()
        current_user = find_by_email(current_user, fields={'id': 1})
        parser = reqparse.RequestParser()
        parser.add_argument('paper_id', required=True, help="paper_id is missing")
        parser.add_argument('add', required=True, help="should specify if add (add=1) or remove (add=0)", type=bool)
        data = parser.parse_args()
        paper_id = data['paper_id']
        get_group(group_id)  # Validate that the group exists
        add_remove_group(group_id, paper_id, data['add'], str(current_user['_id']), False)
        return {'message': 'success'}


api.add_resource(Groups, '/all')
api.add_resource(NewGroup, '/new')
api.add_resource(Group, '/group/<group_id>')
