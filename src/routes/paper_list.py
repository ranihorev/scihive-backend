import datetime
import json
import logging
import re

from flask import Blueprint, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_optional
from flask_restful import Api, Resource, fields, inputs, marshal_with, reqparse
from sqlalchemy import or_
from sqlalchemy_searchable import search

from src.new_backend.models import (Author, Collection, Paper, db,
                                    paper_collection_table)
from src.routes.user_utils import get_user
from src.utils import get_file_path
from .paper_query_utils import paper_with_code_fields

app = Blueprint('paper_list', __name__)
api = Api(app)
logger = logging.getLogger(__name__)


class Autocomplete(Resource):
    def get(self):
        MAX_ITEMS = 8
        query_parser = reqparse.RequestParser()
        query_parser.add_argument('q', type=str, required=True, location='args')
        args = query_parser.parse_args()
        q = args.get('q', '')

        if len(q) < 1:
            return []

        authors = Author.query.filter(Author.name.ilike(f'%{q}%')).limit(MAX_ITEMS).all()
        authors = [{'name': a.name, 'type': 'author'} for a in authors]

        papers = []
        try:
            paper_id = int(q)
            paper_by_id = Paper.query.filter(or_(Paper.id == q, Paper.original_id == q)
                                             ).filter(Paper.is_private.isnot(True)).first()
            if paper_by_id:
                papers.append(paper_by_id)
        except ValueError:
            pass

        papers = papers + search(Paper.query, q).filter(Paper.is_private.isnot(True)).all()
        papers = [{'name': p.title, 'type': 'paper', 'id': p.id} for p in papers]

        papers_len = len(papers)
        authors_len = len(authors)
        if papers_len + authors_len > MAX_ITEMS:
            if papers_len > int(MAX_ITEMS / 2) and authors_len > int(MAX_ITEMS / 2):
                authors = authors[:int(MAX_ITEMS / 2)]
                papers = papers[:int(MAX_ITEMS / 2)]
            else:
                if authors_len > papers_len:
                    authors = authors[:(MAX_ITEMS - papers_len)]
                else:
                    papers = papers[:(MAX_ITEMS - authors_len)]

        return papers + authors


papers_fields = {
    'id': fields.String,
    'title': fields.String,
    'saved_in_library': fields.Boolean,
    'authors': fields.Nested({'name': fields.String}),
    'time_published': fields.DateTime(dt_format='rfc822', attribute="publication_date"),
    'abstract': fields.String(attribute="abstract"),
    'groups': fields.Raw(attribute='collection_ids', default=[]),
    'twitter_score': fields.Integer,
    'num_stars': fields.Integer,
    'code': fields.Nested(paper_with_code_fields, attribute='paper_with_code', allow_null=True)
}

papers_list_fields = {
    'papers': fields.Nested(papers_fields),
    'count': fields.Integer,
}


SORT_DICT = {
    'tweets': Paper.twitter_score.desc(),
    'date': Paper.publication_date.desc(),
    'score': None,  # sort is handles in the query itself
    'bookmarks': Paper.num_stars.desc(),
    'date_added': paper_collection_table.c.date_added.desc()
}

AGE_DICT = {'day': 1, '3days': 3, 'week': 7, 'month': 30, 'year': 365, 'all': -1}


def sort_query(query, args):
    sort = args.get('sort', 'date')
    sort_by = SORT_DICT.get(sort)
    if sort_by is not None:
        if sort == 'date_added':
            query = query.join(paper_collection_table)
        query = query.order_by(sort_by, Paper.id.asc())  # We sort be id as well to stabilize the order
    return query


def add_collections(papers, user):
    paper_ids = [p.id for p in papers]
    collections = db.session.query(Collection.id.label('collection_id'), paper_collection_table.c.paper_id.label('paper_id')).join(paper_collection_table).filter(
        paper_collection_table.c.paper_id.in_(paper_ids), Collection.users.any(id=user.id)).all()
    # Convert to a dict with list of collections
    paper_to_collections = {}
    for c in collections:
        paper_to_collections.setdefault(c.paper_id, []).append(str(c.collection_id))

    # assign to papers
    for p in papers:
        p.collection_ids = paper_to_collections.get(p.id, [])

    return papers


class Papers(Resource):
    method_decorators = [jwt_optional]

    @marshal_with(papers_list_fields)
    def get(self):
        query_parser = reqparse.RequestParser()
        # query_parser.add_argument('q', type=str, required=False)
        query_parser.add_argument('author', type=str, required=False, location='args')
        query_parser.add_argument('page_num', type=int, required=False, default=1, location='args')
        query_parser.add_argument('sort', type=str, required=False, choices=list(
            SORT_DICT.keys()), store_missing=False, location='args')
        query_parser.add_argument('age', type=str, required=False, choices=list(
            AGE_DICT.keys()), default='week', location='args')
        query_parser.add_argument('library', type=inputs.boolean, required=False, default=False, location='args')
        query_parser.add_argument('group', type=str, required=False, location='args')
        query_parser.add_argument('q', type=str, required=False, location='args')
        args = query_parser.parse_args()

        page_num = args.get('page_num', 0)
        q = args.get('q', '')
        author = args.get('author', '')
        age = args.get('age', 'all')

        user = get_user()

        query = db.session.query(Paper)
        if q:
            query = search(query, q, sort=True)

        if age != 'all':  # TODO: replace with integer
            dnow_utc = datetime.datetime.now()
            dminus = dnow_utc - datetime.timedelta(days=int(AGE_DICT[age]))
            query = query.filter(Paper.publication_date >= dminus)

        group_id = args.get('group')
        if group_id:
            query = query.filter(Paper.collections.any(id=group_id))

        is_library = args.get('library')
        if is_library and user:
            query = query.filter(Paper.collections.any(Collection.users.any(id=user.id)))

        if not group_id and not is_library:
            query = query.filter(Paper.is_private.isnot(True))

        if author:
            query = query.filter(Paper.authors.any(name=author))

        query = sort_query(query, args)

        paginated_result = query.paginate(page=page_num, per_page=10)
        papers = paginated_result.items
        if user:
            papers = add_collections(paginated_result.items, user)

        return {"count": paginated_result.total, "papers": papers}


api.add_resource(Autocomplete, "/autocomplete")
api.add_resource(Papers, "/all")
