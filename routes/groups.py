import pymongo
from datetime import datetime

from bson import ObjectId
from flask import Blueprint
import logging

from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_restful import Resource, reqparse, Api, fields, marshal_with

from .user_utils import find_by_email
from . import db_groups, db_users

app = Blueprint('groups', __name__)
api = Api(app)
logger = logging.getLogger(__name__)

group_fields = {
    'id': fields.String(attribute='_id'),
    'name': fields.String,
    'created_at': fields.DateTime(dt_format='rfc822'),
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
        try:
            group_q = {'_id': ObjectId(data['id'])}
        except Exception as e:
            logger.warning('Illegal group id {}'.format(data['id']))
            return get_user_groups()

        group = db_groups.find_one(group_q)
        if group and user_id['_id'] not in group.get('users', []):
            db_users.update_one(user_id, {'$addToSet': {'groups': ObjectId(data['id'])}})
            db_groups.update(group_q, {'$addToSet': {'users': user_id['_id']}})

        return get_user_groups()


class Group(Resource):
    method_decorators = [jwt_required]

    @marshal_with(group_fields)
    def post(self):
        current_user = get_jwt_identity()
        parser = reqparse.RequestParser()
        parser.add_argument('name', help='This field cannot be blank', required=True)
        data = parser.parse_args()
        data['created_at'] = datetime.utcnow()
        user_id = find_by_email(current_user, fields={'id': 1})
        data['created_by'] = user_id['_id']
        data['users'] = [user_id['_id']]
        new_group = db_groups.insert_one(data)
        db_users.update_one(user_id, {'$addToSet': {'groups': new_group.inserted_id}})
        return get_user_groups()

    @marshal_with(group_fields)
    def delete(self):
        current_user = get_jwt_identity()
        user_id = find_by_email(current_user, fields={'id': 1})
        parser = reqparse.RequestParser()
        parser.add_argument('id', help='This field cannot be blank', required=True)
        data = parser.parse_args()
        # Remove from user
        db_users.update_one(user_id, {'$pull': {'groups': ObjectId(data['id'])}})

        # Remove from group
        group_id = {'_id': ObjectId(data['id'])}
        db_groups.update_one(group_id, {'$pull': {'users': user_id['_id']}})
        return get_user_groups()


api.add_resource(Groups, '/all')
api.add_resource(Group, '/group')