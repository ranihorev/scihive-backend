from datetime import datetime
from enum import Enum
from typing import Optional
from flask import session
from flask_restful import abort, reqparse

from ..models import Collection, Paper, Permission, User, db


def get_paper_token_or_none():
    if session.get('paper_token'):
        return session.get('paper_token')
    parser = reqparse.RequestParser()
    parser.add_argument('token', required=False, location='args')
    data = parser.parse_args()
    return data.get('token')


def has_valid_token(paper: Paper, token: Optional[str] = None) -> bool:
    if not paper.token:
        return False
    if token and paper.token == token:
        return True
    return paper.token == get_paper_token_or_none()


class PermissionType(Enum):
    NONE = 0
    TOKEN = 1
    VIEWER = 2
    CREATOR = 3


def is_paper_creator(paper: Paper, user: Optional[User]) -> bool:
    return bool(user) and paper.uploaded_by_id == user.id


def get_paper_permission_type(paper: Paper, user: Optional[User], token: Optional[str] = None) -> PermissionType:
    """Returns the highest permission type available for the user"""
    if user:
        if is_paper_creator(paper, user):
            return PermissionType.CREATOR
        if Permission.query.filter(Permission.paper_id == paper.id, Permission.user_id == user.id).first():
            return PermissionType.VIEWER
    if has_valid_token(paper, token):
        return PermissionType.TOKEN
    return PermissionType.NONE


def has_permissions_to_paper(paper: Paper, user: Optional[User], check_token: bool = True, token: Optional[str] = None) -> bool:
    permission = get_paper_permission_type(paper, user, token=token)
    if permission == PermissionType.TOKEN:
        return check_token
    return permission != PermissionType.NONE


def enforce_permissions_to_paper(paper: Paper, user: Optional[User], check_token=True, token: Optional[str] = None) -> bool:
    if not paper.is_private:
        return True
    if not has_permissions_to_paper(paper, user, check_token=check_token, token=token):
        abort(403, message='Missing paper permissions')
    return True


def add_permissions_to_user(paper: Paper, user: User):
    permissions = Permission(paper_id=paper.id, user_id=user.id)
    db.session.add(permissions)
    shared_collection = Collection.query.filter(
        Collection.created_by_id == user.id, Collection.is_shared == True).first()
    if not shared_collection:
        shared_collection = Collection(creation_date=datetime.utcnow(), name="Shared",
                                       created_by_id=user.id, is_shared=True)
        shared_collection.users.append(user)
        db.session.add(shared_collection)
