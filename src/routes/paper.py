import logging
from datetime import datetime
from enum import Enum
import threading
from typing import List, Optional
from cerberus import Validator
from flask import session
from sqlalchemy.sql.functions import user
import pytz
from flask import Blueprint, send_from_directory
from flask_jwt_extended import jwt_optional, jwt_required
from flask_restful import Api, Resource, abort, fields, marshal_with, reqparse
from secrets import token_urlsafe

from ..models import Author, Collection, Paper, db, User, Permission

from .notifications.index import new_invite_notification
from .permissions_utils import PermissionType, add_permissions_to_user, get_paper_token_or_none, has_permissions_to_paper, get_paper_permission_type, is_paper_creator
from .file_utils import LOCAL_FILES_DIRECTORY, s3_available
from .latex_utils import REFERENCES_VERSION, extract_references_from_latex
from .paper_query_utils import get_paper_user_groups, get_paper_with_pdf, paper_with_code_fields
from .user_utils import get_jwt_email, get_user_optional, get_user_by_email
from .paper_query_utils import get_paper_or_404

app = Blueprint('paper', __name__)
api = Api(app)
logger = logging.getLogger(__name__)

paper_fields = {
    'id': fields.String,
    'url': fields.String(attribute='local_pdf'),
    'title': fields.String,
    'authors': fields.Nested({'name': fields.String, 'id': fields.String}),
    'time_published': fields.DateTime(attribute='publication_date', dt_format='rfc822'),
    'abstract': fields.String,
    'code': fields.Nested(paper_with_code_fields, attribute='paper_with_code', allow_null=True),
    'groups': fields.List(fields.String(attribute='id'), attribute='groups'),
    'is_editable': fields.Boolean(attribute='is_private', default=False),
    'arxiv_id': fields.String(attribute='original_id', default=''),
}

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


class PaperReferencesResource(Resource):
    method_decorators = [jwt_optional]

    def get(self, paper_id):
        query_parser = reqparse.RequestParser()
        query_parser.add_argument('force', type=str, required=False)
        paper = get_paper_or_404(paper_id)

        # Rani: how to address private papers?
        if paper.is_private:
            return []

        force_update = bool(query_parser.parse_args().get('force'))
        references, _, _ = get_paper_item(paper, 'references', extract_references_from_latex, REFERENCES_VERSION,
                                          force_update=force_update)
        return references['data']


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
        parser.add_argument('authors', type=validateAuthor, required=False, action="append")
        parser.add_argument('removed_authors', type=str, required=False, action="append", default=[])
        paper_data = parser.parse_args()

        paper = Paper.query.get_or_404(paper_id)

        if not paper.is_private:
            abort(403, 'Only uploaded papers can be edited')

        paper.last_update_date = datetime.utcnow()

        paper.title = paper_data['title']
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
        raise ValueError(user_validator.errors)
    return value


class PaperInvite(Resource):
    method_decorators = [jwt_required]

    def _validate_request_by_creator(self, paper: Paper):
        current_user: User = get_user_optional()
        if not paper.uploaded_by == current_user:
            abort(403, message="Only the creator of the doc can update permissions")

    def _throw_if_no_permissions(self, paper: Paper, current_user: User):
        # TODO: merge with permissions_utils function
        if has_permissions_to_paper(paper, current_user, check_token=False):
            return True
        abort(403, message="User is not allowed to add permissions")

    def _get_or_create_user(self, user_data) -> User:
        email: str = user_data['email']
        user: Optional[user] = User.query.filter_by(email=email).first()
        if not user:
            name: str = user_data['name']
            name_parts = name.rsplit(' ', 1)
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
        self._throw_if_no_permissions(paper, current_user)

        users: List[User] = []
        for u in data['users']:
            users.append(self._get_or_create_user(u))
        db.session.commit()

        for u in users:
            if not has_permissions_to_paper(paper, u, check_token=False):
                add_permissions_to_user(paper, u)
                # TODO: Switch to task queue later
                threading.Thread(target=new_invite_notification, args=(
                    u.id, paper_id, current_user_name, data['message'])).start()
        db.session.commit()
        return {"message": "success"}

    def delete(self, paper_id):
        parser = reqparse.RequestParser()
        parser.add_argument('email', type=str, required=True, location='json')
        data = parser.parse_args()
        paper: Paper = Paper.query.get_or_404(paper_id)
        current_user = get_user_by_email()
        self._throw_if_no_permissions(paper, current_user)
        deleted_user = get_user_by_email(data.get('email'))

        Permission.query.filter(Permission.user_id == deleted_user.id, Permission.paper_id == paper_id).delete()
        shared_collection: Collection = Collection.query.filter(
            Collection.created_by_id == deleted_user.id, Collection.is_shared == True).first()
        if shared_collection:
            shared_collection.papers.remove(paper)
        db.session.commit()
        return {"message": "success"}


class PaperSharingToken(Resource):
    method_decorators = [jwt_required]

    def _validate_permissions(self, paper: Paper):
        current_user = get_user_by_email()
        if is_paper_creator(paper, current_user):
            return
        abort(404, message='No permissions')

    def get(self, paper_id):
        paper: Paper = Paper.query.get_or_404(paper_id)
        self._validate_permissions(paper)
        return {'token': paper.token}

    def post(self, paper_id):
        parser = reqparse.RequestParser()
        parser.add_argument('enable', type=bool, required=True, location='json')
        data = parser.parse_args()
        paper: Paper = Paper.query.get_or_404(paper_id)
        if data.get('enable'):
            paper.token = token_urlsafe()
        else:
            paper.token = None
        db.session.commit()
        return {'token': paper.token}


api.add_resource(PaperSharingToken, "/<paper_id>/token")
api.add_resource(PaperInvite, "/<paper_id>/invite")
api.add_resource(PaperResource, "/<paper_id>")
api.add_resource(PaperGroupsResource, "/<paper_id>/groups")
api.add_resource(PaperReferencesResource, "/<paper_id>/references")
api.add_resource(EditPaperResource, "/<paper_id>/edit")

# We only want this endpoint if we're using local filesystem to store PDFs
if not s3_available:
    @app.route('/files/<path:path>')
    def serve_local_files(path):
        return send_from_directory(LOCAL_FILES_DIRECTORY, path)
