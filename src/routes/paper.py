import logging
from datetime import datetime
from enum import Enum
from secrets import token_urlsafe
from typing import List, Optional

import pytz
from cerberus import Validator
from flask import Blueprint, send_from_directory, session
from flask_jwt_extended import jwt_optional, jwt_required
from flask_restful import Api, Resource, abort, fields, marshal_with, reqparse

from ..models import (Author, Collection, MetadataState, Paper, Permission,
                      User, db)
from .file_utils import LOCAL_FILES_DIRECTORY, s3_available
from .metadata_utils import METADATA_VERSION, extract_paper_metadata
from .notifications.index import new_invite_notification
from .paper_query_utils import (get_paper_or_404, get_paper_user_groups,
                                get_paper_with_pdf, paper_fields)
from .permissions_utils import (PermissionType, add_permissions_to_user,
                                enforce_permissions_to_paper,
                                get_paper_permission_type,
                                get_paper_token_or_none,
                                has_permissions_to_paper, is_paper_creator)
from .user_utils import get_jwt_email, get_user_by_email, get_user_optional
from .utils import start_background_task

app = Blueprint('paper', __name__)
api = Api(app)
logger = logging.getLogger(__name__)

user_fields = {
    'username': fields.String(),
    'first_name': fields.String(),
    'last_name': fields.String(),
    'email': fields.String(),
}


class ItemState(Enum):
    existing = 1
    updated = 2
    new = 3


class PaperGroupsResource(Resource):
    method_decorators = [jwt_required]

    @marshal_with({'groups': fields.List(fields.String)})
    def get(self, paper_id):
        paper = Paper.query.get_or_404(paper_id)
        groups = [g.id for g in get_paper_user_groups(paper)]
        return {'groups': groups}


class PaperResource(Resource):
    method_decorators = [jwt_optional]

    @marshal_with(paper_fields)
    def get(self, paper_id):
        paper = get_paper_with_pdf(paper_id)
        logger.info(f'Fetching paper - {paper.id} - private: {paper.is_private}')
        if paper.is_private:
            user = get_user_optional()
            permission = get_paper_permission_type(paper, user)
            if permission == PermissionType.NONE:
                abort(
                    403, message=f'You do not have permissions to view this paper. Please contact the owner - {paper.uploaded_by.username}')
            elif permission == PermissionType.TOKEN:
                if user:
                    add_permissions_to_user(paper, user)
                    db.session.commit()

                session['paper_token'] = get_paper_token_or_none()

        is_metadata_missing = not paper.metadata_state or paper.metadata_state == MetadataState.missing
        is_metatdata_old = paper.metadata_state == MetadataState.ready and (
            paper.metadata_version or 0) < METADATA_VERSION

        if is_metadata_missing or is_metatdata_old:
            start_background_task(target=extract_paper_metadata, paper_id=paper.id)
        paper.groups = get_paper_user_groups(paper)
        return paper


def get_visibility(comment):
    if isinstance(comment['visibility'], dict):
        return comment['visibility'].get('type', '')
    return comment['visibility']


def add_metadata(comments):
    current_user = get_jwt_email()

    def add_single_meta(comment):
        comment['canEdit'] = (current_user and current_user == comment['user'].get('email', -1))
        if get_visibility(comment) == 'anonymous':
            comment['user']['username'] = 'Anonymous'

    if isinstance(comments, list):
        for c in comments:
            add_single_meta(c)
    else:
        add_single_meta(comments)


def get_paper_item(paper, item, latex_fn, version=None, force_update=False):
    state = ItemState.existing
    if not paper:
        abort(404, message='Paper not found')
    new_value = old_value = getattr(paper, item)

    if force_update or not old_value or (version is not None and float(old_value.get('version', 0)) < version):
        state = ItemState.new if not old_value else ItemState.updated

        try:
            new_value = latex_fn(paper.original_id)
            setattr(paper, item, new_value)
        except Exception as e:
            logger.error(f'Failed to retrieve {item} for {paper.id} - {e}')
            abort(500, message=f'Failed to retrieve {item}')
    return new_value, old_value, state


def validateAuthor(value):
    if not isinstance(value, dict):
        raise TypeError('Author must be an object')
    if not value.get('name'):
        raise ValueError('Author name is missing')
    return value


class EditPaperResource(Resource):
    method_decorators = [jwt_required]

    @marshal_with(paper_fields)
    def post(self, paper_id):
        parser = reqparse.RequestParser()
        parser.add_argument('title', type=str, required=True)
        parser.add_argument('date',
                            type=lambda x: datetime.strptime(x, '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=pytz.UTC),
                            required=True,
                            dest="publication_date")
        parser.add_argument('abstract', type=str, required=True)
        parser.add_argument('doi', type=str, required=True)
        parser.add_argument('authors', type=validateAuthor, required=False, action="append")
        parser.add_argument('removed_authors', type=str, required=False, action="append", default=[])
        paper_data = parser.parse_args()

        paper = Paper.query.get_or_404(paper_id)

        if not paper.is_private:
            abort(403, message='Only uploaded papers can be edited')

        paper.last_update_date = datetime.utcnow()

        paper.title = paper_data['title']
        paper.doi = paper_data['doi']
        paper.publication_date = paper_data['publication_date']
        paper.abstract = paper_data['abstract']

        for author_id in paper_data['removed_authors']:
            author = Author.query.get(author_id)
            paper.authors.remove(author)

        for author_data in (paper_data.get('authors') or []):
            author_name = author_data.get('name')
            author_id = author_data.get('id')
            if author_id:
                author = Author.query.get_or_404(author_id)
                author.name = author_name
            else:
                new_author = Author(name=author_name)
                new_author.papers.append(paper)
                db.session.add(new_author)

        db.session.commit()
        paper.groups = get_paper_user_groups(paper)
        return paper


email_regex = '^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
schema = {'name': {'type': 'string'}, 'email': {'type': 'string', 'regex': email_regex, 'required': True}}


def validateUsersList(value):
    user_validator = Validator()
    valid = user_validator.validate(value, schema)
    if not valid:
        email = value.get('email', '')
        raise ValueError(f'Email address is invalid - {email}')
    return value


class PaperInvite(Resource):
    method_decorators = [jwt_required]

    def _validate_request_by_creator(self, paper: Paper):
        current_user: User = get_user_optional()
        if not paper.uploaded_by == current_user:
            abort(403, message="Only the creator of the doc can update permissions")

    def _abort_if_no_permissions(self, paper: Paper, current_user: User):
        # TODO: merge with permissions_utils function
        if has_permissions_to_paper(paper, current_user, check_token=False):
            return True
        abort(403, message="User is not allowed to add permissions")

    def _get_or_create_user(self, user_data) -> User:
        email: str = user_data['email'].lower()
        user: Optional[User] = User.query.filter_by(email=email).first()
        if not user:
            name: str = user_data.get('name') or ''
            name_parts = name.rsplit(' ', 1)
            if not name:
                try:
                    name = email.split('@')[0]
                    name_parts = name.split('.') if '.' in name else name.split('_')
                except Exception as e:
                    logger.error(e)

            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) >= 2 else ''
            username = name.replace(' ', '') if name else email.split('@')[0]
            user: User = User(first_name=first_name, last_name=last_name,
                              username=username, email=email, pending=True)
            db.session.add(user)
        return user

    @marshal_with({"author": fields.Nested(user_fields), "users": fields.Nested(user_fields)})
    def get(self, paper_id):
        paper: Paper = Paper.query.get_or_404(paper_id)
        current_user: User = get_user_by_email()
        permissions: List[Permission] = db.session.query(Permission).filter(Permission.paper_id == paper_id).all()
        users = [p.user for p in permissions]
        if paper.is_private and (current_user not in users and paper.uploaded_by != current_user):
            abort(403, message="Only authorized users can view permissions")
        return {"author": paper.uploaded_by, "users": users}

    def post(self, paper_id):
        # Check if paper exists
        parser = reqparse.RequestParser()
        parser.add_argument('users', type=validateUsersList, required=True, action='append', location='json')
        parser.add_argument('message', type=str, required=True, location='json')
        data = parser.parse_args()
        current_user = get_user_by_email()
        current_user_name = current_user.first_name or current_user.username
        paper: Paper = get_paper_or_404(paper_id)
        self._abort_if_no_permissions(paper, current_user)

        users: List[User] = []
        for u in data['users']:
            users.append(self._get_or_create_user(u))
        db.session.commit()

        for u in users:
            if not has_permissions_to_paper(paper, u, check_token=False):
                add_permissions_to_user(paper, u)
                # TODO: Switch to task queue later
                logger.info(f'Sending email to user - {u.username}')
                start_background_task(target=new_invite_notification, user_id=u.id,
                                      paper_id=paper_id, invited_by_name=current_user_name, message=data['message'])
        db.session.commit()
        return {"message": "success"}

    def delete(self, paper_id):
        parser = reqparse.RequestParser()
        parser.add_argument('email', type=str, required=True, location='json')
        data = parser.parse_args()
        paper: Paper = Paper.query.get_or_404(paper_id)
        current_user = get_user_by_email()
        self._abort_if_no_permissions(paper, current_user)
        deleted_user = get_user_by_email(data.get('email'))

        Permission.query.filter(Permission.user_id == deleted_user.id, Permission.paper_id == paper_id).delete()
        shared_collection: Collection = Collection.query.filter(
            Collection.created_by_id == deleted_user.id, Collection.is_shared == True).first()
        if shared_collection:
            try:
                shared_collection.papers.remove(paper)
            except ValueError:
                logger.warning(f'Failed to remove paper {paper_id} from shared collection - {shared_collection.id}')
        db.session.commit()
        return {"message": "success"}


class PaperSharingToken(Resource):
    method_decorators = [jwt_required]

    def get(self, paper_id):
        paper: Paper = Paper.query.get_or_404(paper_id)
        user = get_user_by_email()
        if paper.is_private:
            enforce_permissions_to_paper(paper, user, check_token=False)

        return {'token': paper.token, 'canEdit': get_paper_permission_type(paper, user) == PermissionType.CREATOR}

    def post(self, paper_id):
        parser = reqparse.RequestParser()
        parser.add_argument('enable', type=bool, required=True, location='json')
        data = parser.parse_args()
        paper: Paper = Paper.query.get_or_404(paper_id)
        if not is_paper_creator(paper, get_user_by_email()):
            abort(403, message='Only the creator of the paper can share change link sharing settings')
        if data.get('enable'):
            paper.token = token_urlsafe()
        else:
            paper.token = None
        db.session.commit()
        return {'token': paper.token, 'canEdit': True}


api.add_resource(PaperSharingToken, "/<paper_id>/token")
api.add_resource(PaperInvite, "/<paper_id>/invite")
api.add_resource(PaperResource, "/<paper_id>")
api.add_resource(PaperGroupsResource, "/<paper_id>/groups")
api.add_resource(EditPaperResource, "/<paper_id>/edit")

# We only want this endpoint if we're using local filesystem to store PDFs
if not s3_available:
    @app.route('/files/<path:path>')
    def serve_local_files(path):
        return send_from_directory(LOCAL_FILES_DIRECTORY, path)
