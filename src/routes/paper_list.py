import datetime
import re
from flask import Blueprint, jsonify
import logging
import json
from flask_jwt_extended import jwt_optional, get_jwt_identity
from flask_restful import Api, Resource, reqparse, marshal_with, fields
from sqlalchemy_searchable import search
from sqlalchemy import or_

from src.new_backend.models import Author, Collection, Paper, db
from src.routes.paper_query_utils import SORT_DICT, AGE_DICT
from src.utils import get_file_path
from src.routes.user_utils import get_user_by_email

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
    'summary': fields.String(attribute="abstract"),
}

papers_list_fields = {
    'papers': fields.Nested(papers_fields),
    'count': fields.Integer,
}


def get_sort(args):
    field = args.get('sort', 'date')
    options = {
        "date": Paper.publication_date.desc(),
    }
    return options.get(field)


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
        query_parser.add_argument('library', type=bool, required=False, default=False, location='args')
        query_parser.add_argument('group', type=str, required=False, location='args')
        args = query_parser.parse_args()

        page_num = args.get('page_num', 0)
        q = args.get('q', '')
        author = args.get('author', '')
        age = args.get('age', 'all')

        query = db.session.query(Paper)
        if q:
            query = search(query, q)

        if age != 'all':  # TODO: replace with integer
            dnow_utc = datetime.datetime.now()
            dminus = dnow_utc - datetime.timedelta(days=int(AGE_DICT[age]))
            query = query.filter(Paper.publication_date >= dminus)

        group_id = args.get('group')
        if group_id:
            query = query.filter(Paper.collections.any(id=group_id))

        is_library = args.get('library')
        if is_library:
            user = get_user_by_email()
            query = query.filter(Paper.collections.any(Collection.users.any(id=user.id)))

        if not group_id and not is_library:
            query.filter(Paper.is_private.isnot(True))

        if author:
            query = query.filter(Paper.authors.any(name=author))
        papers_items = query.paginate(page=page_num, per_page=10)

        return {"count": papers_items.total, "papers": papers_items.items}


api.add_resource(Autocomplete, "/autocomplete")
api.add_resource(Papers, "/all")
