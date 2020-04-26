import pymongo
import requests
import csv
from io import StringIO
import logging
from dotenv import load_dotenv
import os

from .utils import catch_exceptions
from src.new_backend.models import Paper
from src.logger import logger_config

logger = logging.getLogger(__name__)

load_dotenv()


def fetch_data():
    user = os.environ.get('PAPERSWITHCODE_USER')
    password = os.environ.get('PAPERSWITHCODE_PASS')
    response = requests.get('https://paperswithcode.com/api/linkstars', auth=(user, password))
    content = response.content.decode('utf-8')
    f = StringIO(content)
    data = csv.DictReader(f, escapechar='\\')
    return data


def update_db(data):
    for row in data:
        try:
            arxiv_id = row['arxiv_id']
            paper = Paper.query.filter(original_id=arxiv_id).first()
            if not paper:
                logger.info(f'Paper not found - {arxiv_id}')
                continue
        except KeyError as e:
            logger.warning(f'arxiv_id is missing for row {row}')
            continue

        # if papers.find(cur_id).count() > 0:
        #     obj = {
        #         'github_link': row.get('github_link'),
        #         'extraction_conf': row.get('high_conf', '') == 'True',
        #         'conferences': row.get('proceeding', ''),
        #         'stars': int(row.get('stars', 0)),
        #         'framework': row.get('framework'),
        #         'datasets': row.get('datasets', '').split('|'),
        #         'tasks': row.get('tasks', '').split('|'),
        #         'paperswithcode_link': row.get('url', '')
        #     }
        #     try:
        #         papers.update(cur_id, {'$set': {'code': obj}})
        #     except Exception as e:
        #         logger.error('Failed to update paper {} - {}'.format(cur_id['_id'], e))
        # else:
        #     logger.info('Paper not found - {}'.format(cur_id['_id']))


@catch_exceptions(logger=logger)
def run():
    logger.info('Fetching data from papers with code')
    data = fetch_data()
    logger.info('Updating DB with data from papers with code')
    update_db(data)
    logger.info('Finished updating data from papers with code')
