import logging
import uuid
from datetime import datetime
from flask_jwt_extended import get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash

from . import revoked_tokens, db_users, db_papers, db_group_papers

logger = logging.getLogger(__name__)


def is_jti_blacklisted(jti):
    query = revoked_tokens.find_one({'jti': jti})
    return bool(query)


def save_revoked_token(jti):
    return revoked_tokens.insert_one({'jti': jti})


def save_user(email, password, username):
    return db_users.insert_one(
        {'email': email, 'password': password, 'username': username, 'library_id': str(uuid.uuid4())})


def find_by_email(email, fields=None):
    query = {'email': email}
    validate_library_id = not fields or (isinstance(fields, dict) and fields.get('library_id') == 1)

    if not fields:
        fields = {'library': 0}
    user = db_users.find_one(query, fields)

    if validate_library_id and not user.get('library_id'):
        library_id = str(uuid.uuid4())
        db_users.update_one({'_id': user['_id']}, {'$set': {'library_id': library_id}})
        user['library_id'] = library_id
    return user


def generate_hash(password):
    return generate_password_hash(password)


def verify_hash(password, hash):
    return check_password_hash(hash, password)


def add_remove_group(group_id: str, paper_id: str, should_add: str, user_id: str, is_library: bool):
    query = {'group_id': group_id, 'paper_id': paper_id}

    if should_add:
        db_group_papers.update_one(query, {'$set': {'date': datetime.now(), 'user': user_id, 'is_library': is_library}},
                                   upsert=True)
    else:
        db_group_papers.delete_one(query)


def add_to_library(op: str, user_email: str, paper):
    paper_id = paper['_id']
    user = find_by_email(user_email, {'library_id': 1})

    add_remove_group(user['library_id'], paper_id, op == 'save', str(user['_id']), True)
    # TODO change this to addtoset or pull of users list
    total_bookmarks = paper.get("total_bookmarks", 0) + 1 if op == 'save' else -1
    db_papers.update_one({'_id': paper_id}, {'$set': {'total_bookmarks': max(0, total_bookmarks)}})
    return True


def add_papers_to_library(user_email, papers):
    user = find_by_email(user_email, {'library_id': 1})
    existing_papers = db_group_papers.find({'paper_id': {'$in': papers}, 'group_id': user['library_id']},
                                           {'paper_id': 1})
    existing_papers = [p['paper_id'] for p in existing_papers]
    new_papers = [p for p in papers if p not in existing_papers]
    for paper_id in new_papers:
        add_remove_group(group_id=user['library_id'], paper_id=paper_id, should_add=True, user_id=str(user['_id']),
                         is_library=True)
    db_papers.update({'_id': {'$in': new_papers}}, {'$inc': {'total_bookmarks': 1}})


def add_user_data(data, key='user'):
    current_user = get_jwt_identity()
    if current_user:
        current_user = find_by_email(current_user)
        data[key] = {'email': current_user['email'], 'username': current_user['username']}
    else:
        data[key] = {'username': 'Guest'}