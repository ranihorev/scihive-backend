import re
from flask import Blueprint, jsonify
import logging
from flask_jwt_extended import jwt_optional
from flask_restful import Api, Resource, reqparse, marshal_with

from .paper_utils import get_papers, papers_list_fields
from . import db_authors, db_papers

app = Blueprint('paper_list', __name__)
api = Api(app)
logger = logging.getLogger(__name__)


query_parser = reqparse.RequestParser()
query_parser.add_argument('q', type=str, required=False)
query_parser.add_argument('author', type=str, required=False)
query_parser.add_argument('page_num', type=int, required=False)
query_parser.add_argument('sort', type=str, required=False)


class Autocomplete(Resource):
    def get(self):
        MAX_ITEMS = 8
        args = query_parser.parse_args()
        q = args.get('q', '')

        if len(q) <= 1:
            return jsonify([])

        author_q = f'.*{q.replace(" ", ".*")}.*'
        authors = list(db_authors.find({'_id': {'$regex': re.compile(author_q, re.IGNORECASE)}}).limit(MAX_ITEMS))
        authors = [{'name': a['_id'], 'type': 'author'} for a in authors]

        papers = list(db_papers.find({'$or': [{'_id': q}, {'$text': {'$search': q}}]}).limit(MAX_ITEMS))
        papers = [{'name': p['title'], 'type': 'paper', 'id': p['_id']} for p in papers]

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


class Papers(Resource):
    method_decorators = [jwt_optional]

    @marshal_with(papers_list_fields)
    def get(self):
        papers = get_papers()
        return papers


api.add_resource(Autocomplete, "/autocomplete")
api.add_resource(Papers, "/all")
