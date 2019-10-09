from bson import ObjectId
from flask_restful import abort

from . import db_groups, db_users


def get_group(group_id: str):
    try:
        group_q = {'_id': ObjectId(group_id)}
    except Exception as e:
        abort(404, message='Invalid group id')
    group = db_groups.find_one(group_q)
    if not group:
        abort(404, messsage='Group not found')
    return group, group_q


def add_user_to_group(user_id_q, group_q):
    db_users.update_one(user_id_q, {'$addToSet': {'groups': group_q['_id']}})
    db_groups.update(group_q, {'$addToSet': {'users': user_id_q['_id']}})