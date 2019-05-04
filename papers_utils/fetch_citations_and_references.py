import logging
from datetime import datetime
from time import sleep

import pymongo
import requests

from logger import logger_config
from utils import catch_exceptions

client = pymongo.MongoClient()
mdb = client.arxiv
db_papers = mdb.papers
sem_sch_papers = mdb.sem_sch_papers  # semantic scholar data
sem_sch_authors = mdb.sem_sch_authors  # semantic scholar data

logger_config(info_filename='citations_fetcher.log')
logger = logging.getLogger(__name__)

def send_query(p, is_arxiv):
    p_id = p['_id']
    prefix = "arXiv:" if is_arxiv else ""
    response = requests.get(f'https://api.semanticscholar.org/v1/paper/{prefix}{p_id}').json()
    if 'error' in response:
        logger.info(f'Error - {p_id} - {response}')
        return None

    authors = [{'id': a['authorId'], 'name': a['name']} for a in response['authors']]
    citations = [{'arxivId': c['arxivId'], 'paperId': c['paperId'], 'title': c['title']} for c in response['citations']]
    references = [{'arxivId': r['arxivId'], 'paperId': r['paperId'], 'title': r['title']} for r in
                  response['references']]
    return {
        '_id': response['arxivId'], 'paperId': response['paperId'], 'year': response['year'],
        'time_updated': p.get('time_updated', None), 'time_published': p.get('time_published', None),
        'title': response['title'], 'authors': authors, 'citations': citations, 'references': references,
        'last_rec_update': datetime.utcnow(), 'found': 1
    }


def fetch_paper_data(p, is_arxiv=True):
    p_id = p['_id']
    retries = 3
    res = None
    success = False

    for i in range(retries):
        try:
            res = send_query(p, is_arxiv)
            success = True
            break
        except Exception as e:
            logger.warning(f'Failed to fetch paper data - {e}')
            sleep(10)

    if not success:
        return None

    if not res:
        res = {'_id': p_id, 'title': p['title'], 'authors': p['authors'], 'last_rec_update': datetime.utcnow(),
               'time_updated': p['time_updated'],'time_published': p['time_published'], 'found': 0}
    return res


@catch_exceptions(logger=logger)
def update_all_papers(age_days=5):
    logger.info('Updating citations and references')
    min_days_to_update = age_days * 86400
    papers = list(db_papers.find())
    logger.info(f'Fetching {len(papers)} documents')
    for idx, p in enumerate(papers):
        if idx % 500 == 0:
            logger.info(f'Updating batch {idx}')
        cur_sem_sch = sem_sch_papers.find_one({'_id': p['_id']})
        if not cur_sem_sch or (datetime.utcnow() - cur_sem_sch['last_rec_update']).total_seconds() > min_days_to_update:
            res = fetch_paper_data(p)
            if res:
                sem_sch_papers.update({'_id': res['_id']}, {'$set': res}, True)
                for a in res['authors']:
                    sem_sch_authors.update({'_id': a['name']}, {}, True)
            else:
                logger.error('Failed to fetch paper data - {}'.format(p['_id']))
            sleep(5)
        else:
            logger.debug('Paper is already in DB')

    logger.info('Finished updating refs')


if __name__ == '__main__':
    update_all_papers()



