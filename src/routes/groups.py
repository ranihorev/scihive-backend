import logging
from datetime import datetime
import threading
from sqlalchemy import func
from flask import Blueprint
from flask_jwt_extended import jwt_required
from flask_restful import (Api, Resource, abort, fields, inputs, marshal_with,
                           reqparse)
from typing import List
from ..models import Collection, Paper, db, User, paper_collection_table

from .user_utils import get_jwt_email, get_user_by_email

app = Blueprint('groups', __name__)
api = Api(app)
logger = logging.getLogger(__name__)


class Count(fields.Raw):
    def format(self, value):
        return len(value)


group_fields = {
    'id': fields.String,
    'name': fields.String,
    'color': fields.String,
}

detailed_group_fields = {
    **group_fields,
    "num_papers": fields.Integer,
    'created_at': fields.DateTime(dt_format='rfc822', attribute='creation_date'),
}


def get_user_groups(user: User) -> List[Collection]:
    return Collection.query.filter(Collection.users.any(email=user.email)).all()


class GroupsDetailed(Resource):
    method_decorators = [jwt_required]

    @marshal_with(detailed_group_fields)
    def get(self):
        email = get_jwt_email()
        user_filter = Collection.users.any(email=email)
        data = db.session.query(Collection, func.count(paper_collection_table.c.paper_id).label(
            'num_papers')).filter(user_filter).join(paper_collection_table).group_by(Collection.id).all()
        collections = []
        for collection, num_papers in data:
            collection.num_papers = num_papers
            collections.append(collection)
        return collections


class Groups(Resource):
    method_decorators = [jwt_required]

    @marshal_with(group_fields)
    def get(self):
        email = get_jwt_email()
        return db.session.query(Collection).filter(Collection.users.any(email=email)).all()

    @marshal_with(group_fields)
    def post(self):
        # Join to group in addition to getting the list
        user = get_user_by_email()
        parser = reqparse.RequestParser()
        parser.add_argument('id', help='This field cannot be blank', required=True)
        data = parser.parse_args()
        group = Collection.query.get_or_404(data.get('id'))
        group.users.append(user)
        db.session.commit()
        return get_user_groups(user)


class NewGroup(Resource):
    method_decorators = [jwt_required]

    @marshal_with({'groups': fields.List(fields.Nested(group_fields)), 'new_id': fields.String})
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('name', help='This field cannot be blank', required=True)
        parser.add_argument('color', required=False, type=str)
        parser.add_argument('paper_id', required=False, type=str)
        data = parser.parse_args()
        user = get_user_by_email(get_jwt_email())
        collection = Collection(creation_date=datetime.utcnow(), name=data.get('name'),
                                color=data.get('color'), created_by_id=user.id)
        collection.users.append(user)
        db.session.add(collection)
        db.session.commit()
        all_collections = get_user_groups(user)
        paper_id = data.get('paper_id')
        if paper_id:
            paper = Paper.query.get_or_404(paper_id)
            collection.papers.append(paper)
            db.session.commit()
        response = {'groups': all_collections, 'new_id': collection.id}
        return response


extended_group_fields = dict(group_fields)
extended_group_fields['num_papers'] = fields.Integer


def update_num_stars(paper_id: int):
    # TODO: optimize this:
    paper = Paper.query.get(paper_id)
    paper.num_stars = len(paper.collections)
    db.session.commit()


class Group(Resource):
    @marshal_with(extended_group_fields)
    def get(self, group_id: str):
        group = Collection.query.get_or_404(group_id)
        group_dict = group.__dict__
        group_dict['num_papers'] = len(group.papers)
        return group_dict

    @jwt_required
    @marshal_with(group_fields)
    def delete(self, group_id: str):
        group: Collection = Collection.query.get_or_404(group_id)
        user = get_user_by_email()
        if group.created_by_id == user.id and (group.is_shared or group.is_uploads):
            # Can not leave these collections
            return get_user_groups(user)

        try:
            group.users.remove(user)
            db.session.commit()
        except ValueError:
            pass
        return get_user_groups(user)

    @jwt_required
    @marshal_with(group_fields)
    def patch(self, group_id: str):
        user = get_user_by_email()
        group = Collection.query.get_or_404(group_id)
        if group.created_by != user:
            abort(403, message="Only group owner can edit group")
        parser = reqparse.RequestParser()
        parser.add_argument('name', required=False, type=str)
        parser.add_argument('color', required=False, type=str)
        data = parser.parse_args()
        for key in data:
            setattr(group, key, data[key])
        db.session.commit()
        return get_user_groups(user)

    @jwt_required
    @marshal_with(group_fields)
    def post(self, group_id):
        parser = reqparse.RequestParser()
        parser.add_argument('paper_id', required=True, help="paper_id is missing")
        parser.add_argument('add', required=True,
                            help="should specify if add (add=1) or remove (add=0)", type=inputs.boolean)
        data = parser.parse_args()
        user = get_user_by_email()
        paper = Paper.query.get_or_404(data.get('paper_id'))
        group: Collection = Collection.query.get_or_404(group_id)
        if (data.get('add')):
            group.papers.append(paper)
        else:
            try:
                group.papers.remove(paper)
            except ValueError:
                pass

        db.session.commit()
        threading.Thread(target=update_num_stars, args=(paper.id,)).start()

        paper_groups = Collection.query.filter(Collection.papers.any(
            id=paper.id), Collection.users.any(id=user.id)).all()
        return paper_groups


api.add_resource(Groups, '/all')
api.add_resource(GroupsDetailed, '/all/detailed')
api.add_resource(NewGroup, '/new')
api.add_resource(Group, '/group/<group_id>')
