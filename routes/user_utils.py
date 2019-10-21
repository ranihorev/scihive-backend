import logging
from bson import ObjectId
from flask_restful import abort
from werkzeug.security import generate_password_hash, check_password_hash

from . import revoked_tokens, db_users, db_papers

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


def add_to_library(op, email, paper):
    ops = {'save': '$addToSet', 'remove': '$pull'}
    paper_id = paper['_id']
    user = find_by_email(email, fields={'_id': 1, 'library': 1})
    try:
        new_values = {ops[op]: {'library': paper_id}}
    except KeyError:
        abort(500, message='Illegal action')

    if (op == 'save' and paper_id in user.get('library', [])) or (op == 'remove' and paper_id not in user.get('library', [])):
        return False

    db_users.update_one({'_id': user['_id']}, new_values)
    # TODO change this to addtoset or pull of users list
    total_bookmarks = paper.get("total_bookmarks", 0) + 1 if op == 'save' else -1
    db_papers.update_one({'_id': paper_id}, {'$set': {'total_bookmarks': max(0, total_bookmarks)}})
    return True


def add_papers_to_library(user_id_q, papers):
    user = db_users.find_one(user_id_q, {'_id': 1, 'library': 1})
    new_papers = [p for p in papers if p not in user.get('library', [])]
    db_users.update_one(user_id_q, {'$addToSet': {'library': {'$each': new_papers}}})
    db_papers.update({'_id': {'$in': new_papers}}, {'$inc': {'total_bookmarks': 1}})
