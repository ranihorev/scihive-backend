import requests
import csv
from io import StringIO
import logging
import os

from .utils import catch_exceptions
from ..models import Paper, PaperWithCode, db
from datetime import datetime

logger = logging.getLogger(__name__)


def fetch_data():
    user = os.environ.get('PAPERSWITHCODE_USER')
    password = os.environ.get('PAPERSWITHCODE_PASS')
    response = requests.get('https://paperswithcode.com/api/linkstars', auth=(user, password))
    content = response.content.decode('utf-8')
    f = StringIO(content)
    data = csv.DictReader(f, escapechar='\\')
    return data


def update_db(data):
    now = datetime.utcnow()
    for row in data:
        try:
            arxiv_id = row['arxiv_id']
            paper = Paper.query.filter(Paper.original_id == arxiv_id).first()
            if not paper:
                logger.info(f'Paper not found - {arxiv_id}')
                continue
        except KeyError as e:
            logger.warning(f'arxiv_id is missing for row {row}')
            continue

        stars = int(row.get('stars', 0))
        if not paper.paper_with_code:
            obj = PaperWithCode(paper_id=paper.id, github_link=row.get('github_link'), link=row.get(
                'url', ''), stars=stars, framework=row.get('framework'), last_update_date=now)
            db.session.add(obj)
        else:
            if paper.paper_with_code.stars != stars:
                paper.paper_with_code.stars = stars
                paper.paper_with_code.last_update_date = now

        db.session.commit()


@catch_exceptions(logger=logger)
def run():
    logger.info('Fetching data from papers with code')
    data = fetch_data()
    logger.info('Updating DB with data from papers with code')
    update_db(data)
    logger.info('Finished updating data from papers with code')
