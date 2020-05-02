import datetime
import logging
import os
from typing import List

from flask_jwt_extended import get_jwt_identity

from .s3_utils import arxiv_to_s3
from flask_restful import reqparse, fields, abort
from src.new_backend.models import Paper, db
from src.new_backend.scrapers.arxiv import fetch_entry

logger = logging.getLogger(__name__)

SCORE_META = {'$meta': 'textScore'}
SORT_DICT = {
    'tweets': 'twtr_sum',
    'date': 'time_published',
    'score': 'score',
    'bookmarks': 'total_bookmarks',
    'date_added': 'group.date'
}
AGE_DICT = {'day': 1, '3days': 3, 'week': 7, 'month': 30, 'year': 365, 'all': -1}

PUBLIC_TYPES = ['public', 'anonymous']

query_parser = reqparse.RequestParser()
query_parser.add_argument('q', type=str, required=False)
query_parser.add_argument('author', type=str, required=False)
query_parser.add_argument('page_num', type=int, required=False, default=1)
query_parser.add_argument('sort', type=str, required=False, choices=list(SORT_DICT.keys()), store_missing=False)
query_parser.add_argument('age', type=str, required=False, choices=list(AGE_DICT.keys()), default='week')
query_parser.add_argument('categories', type=str, required=False)
query_parser.add_argument('group', type=str, required=False)


class TwitterUrl(fields.Raw):
    def format(self, objs):
        links = []
        for obj in objs:
            link = 'https://twitter.com/' + obj['tname'] + '/status/' + obj['tid']
            score = obj['likes'] + 2 * obj['rt'] + 4 * obj.get('replies', 0)
            links.append({'link': link, 'name': obj['tname'], 'score': score})
        return links


class Github(fields.Raw):
    def format(self, obj):
        if not obj.get('github_link'):
            return None
        return {
            'github': obj['github_link'],
            'stars': obj.get('stars', 0),
            'paperswithcode': obj.get('paperswithcode_link')
        }


def abs_to_pdf(url):
    return url.replace('abs', 'pdf').replace('http', 'https') + '.pdf'


def get_paper_or_none(paper_id: str):
    return Paper.query.filter(Paper.id == paper_id).first()


def get_paper_with_pdf(paper_id):
    paper = get_paper_or_none(paper_id)
    if not paper:
        # Fetch from arxiv
        fetch_entry(paper_id)
        paper = get_paper_or_none(paper_id)
        if not paper:
            abort(404, message='Paper not found')

    return paper
