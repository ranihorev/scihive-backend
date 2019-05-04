import logging
from bson import ObjectId
from flask_restful import abort
from werkzeug.security import generate_password_hash, check_password_hash

from . import revoked_tokens, db_users

logger = logging.getLogger(__name__)


def is_jti_blacklisted(jti):
    query = revoked_tokens.find_one({'jti': jti})
    return bool(query)


def save_revoked_token(jti):
    return revoked_tokens.insert_one({'jti': jti})


def save_user(email, password, username):
    return db_users.insert_one({'email': email, 'password': password, 'username': username})


def find_by_email(email, fields={'library': 0}):
    query = {'email': email}
    if fields:
        return db_users.find_one(query, fields)
    return db_users.find_one(query)


def generate_hash(password):
    return generate_password_hash(password)


def verify_hash(password, hash):
    return check_password_hash(hash, password)


def get_user_library(user):
    if not user:
        return []
    user_data = find_by_email(user, {})
    return user_data.get('library', [])


def add_to_library(op, email, paper_id):
    ops = {'save': '$addToSet', 'remove': '$pull'}
    user = find_by_email(email, fields={'_id': 1})
    try:
        new_values = {ops[op]: {'library': paper_id}}
    except KeyError:
        abort(500, message='Illegal action')
    return db_users.update_one(user, new_values)
