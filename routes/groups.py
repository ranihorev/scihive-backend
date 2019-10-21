import pymongo
from datetime import datetime

from bson import ObjectId
from flask import Blueprint
import logging

from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_restful import Resource, reqparse, Api, fields, marshal_with, abort

from .group_utils import get_group, add_user_to_group
from .user_utils import find_by_email
from . import db_groups, db_users

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
    'num_papers': Count(attribute='papers'),
}


def get_user_groups():
    current_user = get_jwt_identity()
    groups = find_by_email(current_user, fields={'groups': 1}).get('groups', [])
    groups = db_groups.find({'_id': {'$in': [ObjectId(g) for g in groups]}}, {'users': 0}).sort('created_at', pymongo.DESCENDING)
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
            add_user_to_group(user_id_q=user_id, group=group, group_q=group_q)

        return get_user_groups()


class NewGroup(Resource):
    method_decorators = [jwt_required]

    @marshal_with(group_fields)
    def post(self):
        current_user = get_jwt_identity()
        parser = reqparse.RequestParser()
        parser.add_argument('name', help='This field cannot be blank', required=True)
        parser.add_argument('color', required=False, type=str)
        data = parser.parse_args()
        data['created_at'] = datetime.utcnow()
        user_id = find_by_email(current_user, fields={'id': 1})
        data['created_by'] = user_id['_id']
        data['users'] = [user_id['_id']]
        new_group = db_groups.insert_one(data)
        db_users.update_one(user_id, {'$addToSet': {'groups': new_group.inserted_id}})
        return get_user_groups()


class Group(Resource):

    @marshal_with(group_fields)
    def get(self, group_id: str):
        group, _ = get_group(group_id)
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
        user_id = find_by_email(current_user, fields={'id': 1})
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
        parser = reqparse.RequestParser()
        parser.add_argument('paper_id', required=True, help="paper_id is missing")
        parser.add_argument('add', required=True, help="should specify if add (add=1) or remove (add=0)", type=bool)
        data = parser.parse_args()
        paper_id = data['paper_id']
        group, group_q = get_group(group_id)
        op = '$addToSet' if data['add'] else '$pull'
        db_groups.update(group_q, {op: {'papers': paper_id}})
        return {'message': 'success'}


api.add_resource(Groups, '/all')
api.add_resource(NewGroup, '/new')
api.add_resource(Group, '/group/<group_id>')
