import datetime
import re
from flask import Blueprint, jsonify
import logging
import json
from flask_jwt_extended import jwt_optional, get_jwt_identity
from flask_restful import Api, Resource, reqparse, marshal_with, fields
from sqlalchemy_searchable import search

from src.new_backend.models import Paper, db
from src.routes.paper_query_utils import SORT_DICT, AGE_DICT
from src.utils import get_file_path
from . import db_authors, db_papers

app = Blueprint('paper_list', __name__)
api = Api(app)
logger = logging.getLogger(__name__)

query_parser = reqparse.RequestParser()
query_parser.add_argument('q', type=str, required=False, store_missing=False)


class Autocomplete(Resource):
    def get(self):
        MAX_ITEMS = 8
        args = query_parser.parse_args()
        q = args.get('q', '')

        if len(q) <= 1:
            return jsonify([])

        author_q = f'.*{q.replace(" ", ".*")}.*'
        authors = list(db_authors.find(
            {'_id': {'$regex': re.compile(author_q, re.IGNORECASE)}}).limit(MAX_ITEMS))
        authors = [{'name': a['_id'], 'type': 'author'} for a in authors]

        # TODO: the autocomplete doesn't support private papers (the id format is different)
        papers = list(db_papers.find(
            {'$and': [{'$or': [{'_id': q}, {'$text': {'$search': q}}]}, {'is_private': {'$exists': False}}]}).limit(
            MAX_ITEMS))
        papers = [{'name': p['title'], 'type': 'paper', 'id': p['_id']}
                  for p in papers]

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
        query_parser.add_argument('categories', type=str, required=False, location='args')
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
            query = query.filter(Paper.collections.has(collection_id=group_id))

        if author:
            query = query.filter(Paper.authors.any(name=author))
        papers_items = query.paginate(page=page_num, per_page=10)
        return {"count": papers_items.total, "papers": papers_items.items}

        # TODO: Migrate and remove beyond this point
        current_user = get_jwt_identity()
        user_data = None
        if current_user:
            user_data = find_by_email(current_user, fields={'groups': 1, 'library_id': 1})

        # Get arguments
        q = args['q']

        # group_id = args['group']

        # Calculates skip for pagination
        skips = page_size * (page_num - 1)

        agg_query = []
        filters = {}
        facet = {
            'papers': [
                {'$sort': get_sort(args)},
                {'$skip': skips},
                {'$limit': page_size},
            ],
        }

        if author:
            filters['authors.name'] = author

        if library and current_user:
            group_id = user_data.get('library_id')

        if age != 'all':
            dnow_utc = datetime.datetime.now()
            dminus = dnow_utc - datetime.timedelta(days=int(AGE_DICT[age]))
            filters['time_published'] = {'$gt': dminus}

        if categories:
            filters['tags.term'] = {"$in": categories.split(';')}

        if group_id:
            group_papers = list(db_group_papers.find(
                {'group_id': group_id}, {'paper_id': 1}))
            group_paper_ids = [fix_paper_id(p['paper_id'])
                               for p in group_papers]
            filters['_id'] = {'$in': group_paper_ids}
            if args.get('sort') == 'date_added':
                facet['papers'] = [{'$lookup': create_papers_groups_lookup([group_id], 'group')},
                                   {'$unwind': '$group'}] + \
                    facet['papers']
        else:
            filters['is_private'] = {'$exists': False}

        if q:
            filters['$text'] = {'$search': q}

        if current_user:
            user_data = find_by_email(current_user, fields={
                'groups': 1, 'library_id': 1})
            group_ids = user_data.get('groups', [])
            library_id = user_data.get('library_id')
            group_ids = [str(g) for g in group_ids]
            if library_id:
                group_ids.append(library_id)
            facet['papers'].insert(
                0, {'$lookup': create_papers_groups_lookup(group_ids, 'groups')})

        if page_num == 1:
            facet['count'] = [
                {"$count": "count"}
            ]

        agg_query += [
            {'$match': filters},
            {'$facet': facet},
        ]

        results = db_papers.aggregate(agg_query)

        results = list(results)[0]

        # Adds stats to query
        papers = include_stats(results.get('papers'), user=current_user)
        count = -1
        if 'count' in results:
            if not results['count']:
                count = 0
            else:
                count = results['count'][0]['count']

        return {'papers': papers, 'count': count}
        return papers


categories = json.load(
    open(get_file_path(__file__, '../relevant_arxiv_categories.json'), 'r'))


class Categories(Resource):
    def get(self):
        return categories


api.add_resource(Categories, "/categories")
api.add_resource(Autocomplete, "/autocomplete")
api.add_resource(Papers, "/all")
