"""
Queries arxiv API and downloads papers (the query is a parameter).
The script is intended to enrich an existing database pickle (by default db.p),
so this file will be loaded first, and then new results will be added to it.
"""
import logging
import re

import dateutil.parser
import time
import random
import argparse
import urllib.request
import feedparser
from ..models import Paper, Author, db
from .utils import catch_exceptions
from src.logger import logger_config

logger = logging.getLogger(__name__)
BASE_URL = 'http://export.arxiv.org/api/query?' # base api query url
DEF_QUERY = 'cat:cs.CV+OR+cat:cs.AI+OR+cat:cs.LG+OR+cat:cs.CL+OR+cat:cs.NE+OR+cat:stat.ML'


def encode_feedparser_dict(d):
    """
    helper function to get rid of feedparser bs with a deep copy.
    I hate when libs wrap simple things in their own classes.
    """
    if isinstance(d, feedparser.FeedParserDict) or isinstance(d, dict):
        j = {}
        for k in d.keys():
            j[k] = encode_feedparser_dict(d[k])
        return j
    elif isinstance(d, list):
        l = []
        for k in d:
            l.append(encode_feedparser_dict(k))
        return l
    else:
        return d

def parse_arxiv_url(url):
    """
    examples is http://arxiv.org/abs/1512.08756v2
    we want to extract the raw id and the version
    """
    match = re.search(r"/(?P<id>(\d{4}\.\d{4,5})|([a-zA-Z\-.]+/\d{6,10}))(v(?P<version>\d+))?$", url)
    return match.group('id').replace('/', '_'), int(match.group('version') or 0)

def handle_entry(e):
    paper_data = encode_feedparser_dict(e)

    # Count of added and skipper papers
    added = 0
    skipped = 0

    # Extract just the raw arxiv id and version for this paper
    rawid, version = parse_arxiv_url(paper_data['id'])
    paper_data['_rawid'] = rawid
    paper_data['_version'] = version

    # If the paper didn't exist in our database (or it's a new version), we add it
    existing_paper = db.session.query(Paper).filter(Paper.original_id == rawid).first()
    paper_data['time_updated'] = dateutil.parser.parse(paper_data['updated'])
    paper_data['time_published'] = dateutil.parser.parse(paper_data['published'])

    # TO DO: Create arXiv object as well

    if not existing_paper:
        # Creating a new paper in database
        # TO DO: Where is the PDF stored??
        new_paper = Paper(title=paper_data['title'], link=paper_data['link'], pdf_link=paper_data['link'], publication_date=paper_data['time_published'], abstract=paper_data['summary'], original_id=paper_data['_rawid'], last_update_date=paper_data['time_updated'])
        added = 1

        # Adding new authors to the paper
        # for author in paper_data['authors']:
        #     existing_author = db.session.query(Author).filter(Author.name == author['name']).first()

        #     if not existing_author:
        #         new_author = Author(name=author)
        #         new_author.papers.append(new_paper)
        #         db.session.add(new_author)

        db.session.add(new_paper)
    elif existing_paper.last_update_date < paper_data['time_published']:
        # Updating the existing paper in the database
        existing_paper.title = paper_data['title']
        existing_paper.abstract = paper_data['abstract']
        existing_paper.link = paper_data['link']
        existing_paper.original_id = paper_data['_rawid']
        existing_paper.last_update_date = paper_data['time_updated']
        existing_paper.publication_date = paper_data['time_published']
        added = 1
    else:
        skipped = 1

    db.session.commit()

    return paper_data, added, skipped

# Is this method redundant?
def fetch_entry(paper_id):
    paper_id = paper_id.replace('_', '/')
    try:
        with urllib.request.urlopen(f'{BASE_URL}id_list={paper_id}') as url:
            response = url.read()
        parse = feedparser.parse(response)
        paper, added, skipped = handle_entry(parse.entries[0])
        return paper
    except Exception as e:
        logger.warning(f'Paper not found on arxiv - {paper_id}')
        return None

def fetch_entries(query):
    with urllib.request.urlopen(BASE_URL + query) as url:
        response = url.read()

    parse = feedparser.parse(response)
    num_added = 0
    num_skipped = 0

    for e in parse.entries:
        _, added, skipped = handle_entry(e)
        num_added += added
        num_skipped += skipped

    return num_added, num_skipped

@catch_exceptions(logger=logger)
def fetch_papers(start_index=0, max_index=3000, results_per_iteration=200, wait_time=5, query=DEF_QUERY, break_on_no_added=1):
    # Main loop to fetch new results
    logger.info('Updating paper DB')

    for i in range(start_index, max_index, results_per_iteration):
        num_failures = 0

        logger.info(f'Results {i} - {i + results_per_iteration}')
        query_string = f'search_query={query}&sortBy=lastUpdatedDate&start={i}&max_results={results_per_iteration}'

        while num_failures < 10:
            num_added, num_skipped = fetch_entries(query_string)

            if num_added == 0 and num_skipped > 0 and break_on_no_added == 1:
                logger.info('No new papers were added. Assuming no new papers exist. Exiting.')
                return
            elif num_added + num_skipped > 0:
                logger.info(f'Added {num_added} papers, already had {num_skipped}.')
                break
            else:
                logger.info('Received no results from arxiv. Retrying after sleep')
                num_failures += 1
                time.sleep(5)

        logger.info(f'Sleeping for {wait_time} seconds')
        time.sleep(wait_time + random.uniform(0, 3))

def parse_arguments():
    # parse input arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('--search-query', type=str,
                        default=DEF_QUERY,
                        help='query used for arxiv API. See http://arxiv.org/help/api/user-manual#detailed_examples')
    parser.add_argument('--start-index', type=int, default=0, help='0 = most recent API result')
    parser.add_argument('--max-index', type=int, default=3000, help='upper bound on the paper index we will fetch')
    parser.add_argument('--results-per-iteration', type=int, default=200, help='passed to arxiv API')
    parser.add_argument('--wait-time', type=float, default=5.0, help='wait time allows being gentle on the arxiv API (in seconds)')
    parser.add_argument('--break-on-no-added', type=int, default=1, help='break out early if all returned query papers are already in db? 1=yes, 0=no')
    args, unknown = parser.parse_known_args()

    return args


def run():
    logger_config(info_filename='arxiv.log')

    # Parse input arguments
    args = parse_arguments()
    print(f'Searching arXiv for {args.search_query}')

    # Fetching papers
    fetch_papers(args.start_index, args.max_index, args.results_per_iteration, args.wait_time, args.search_query, args.break_on_no_added)


if __name__ == "__main__":
    run()
