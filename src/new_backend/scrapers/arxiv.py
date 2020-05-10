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
from ..models import Paper, Author, ArxivPaper, Tag, db
from .utils import catch_exceptions
from src.logger import logger_config
from src.routes.s3_utils import arxiv_to_s3
import os
import pytz
from sqlalchemy.orm.exc import NoResultFound

logger = logging.getLogger(__name__)
BASE_URL = 'http://export.arxiv.org/api/query?'  # base api query url
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


def get_pdf_link(paper_data):
    for link in paper_data.get('links', []):
        if link.get('type', '') == 'application/pdf':
            return link.get('href', '')

    return None


# Returns the tags in a given paper_data (the tags are CS, CS.ML, gr, etc), always in lower-case
def get_tags(paper_data):
    tags = []

    for tag_dict in paper_data.get('tags', []):
        tag = tag_dict.get('term', '')

        if tag != '':
            tags.append(tag)

    return tags


def add_tags(tags, paper, source='arXiv'):
    for tag_name in tags:
        # For the time being we ignore non-arxiv tags.
        # ArXiv tags are always of the form archive.subject (https://arxiv.org/help/arxiv_identifier)
        if not re.match('[A-Za-z\\-]+\\.[A-Za-z\\-]+', tag_name):
            continue

        tag = db.session.query(Tag).filter(Tag.name == tag_name).first()

        if not tag:
            tag = Tag(name=tag_name, source=source)
            db.session.add(tag)

        tag.papers.append(paper)


def handle_entry(e, download_to_s3=False):
    paper_data = encode_feedparser_dict(e)

    # Count of added and skipper papers
    added = 0
    skipped = 0

    # Extract just the raw arxiv id and version for this paper
    rawid, version = parse_arxiv_url(paper_data['id'])
    paper_data['_rawid'] = rawid
    paper_data['_version'] = version

    # If the paper didn't exist in our database (or it's a new version), we add it
    paper = db.session.query(Paper).filter(Paper.original_id == rawid).first()
    paper_data['time_updated'] = dateutil.parser.parse(paper_data['updated'])
    paper_data['time_published'] = dateutil.parser.parse(paper_data['published'])

    # Get the PDF
    pdf_link = get_pdf_link(paper_data)

    # We ignore papers without a PDF
    if not pdf_link:
        return paper_data, 0, 1

    if not paper:
        # Getting the PDF from the dictionary
        local_pdf = None
        if download_to_s3:
            if os.environ.get('S3_BUCKET_NAME'):
                local_pdf = arxiv_to_s3(paper.original_pdf)
            else:
                logger.error('S3 bucket name is missing')

        paper = Paper(title=paper_data['title'], link=paper_data['link'], original_pdf=pdf_link, local_pdf=local_pdf, publication_date=paper_data['time_published'],
                      abstract=paper_data['summary'], original_id=paper_data['_rawid'], last_update_date=paper_data['time_updated'])

        # Adding new authors to the paper
        for author in paper_data['authors']:
            author_name = author['name']
            existing_author = Author.query.filter(Author.name == author_name).first()
            if not existing_author:
                existing_author = Author(name=author_name)
                db.session.add(existing_author)

            existing_author.papers.append(paper)

        # We create a new paper in database (and an arXiv paper object)
        added = 1
        db.session.add(paper)
        db.session.flush()
        arxiv_paper = ArxivPaper(paper_id=paper.id, json_data=e)
        db.session.add(arxiv_paper)

    elif paper.last_update_date < paper_data['time_published']:
        # Updating the existing paper in the database
        paper.title = paper_data['title']
        paper.abstract = paper_data['summary']
        paper.link = paper_data['link']
        paper.original_pdf = pdf_link
        paper.original_id = paper_data['_rawid']
        paper.last_update_date = paper_data['time_updated']
        paper.publication_date = paper_data['time_published']

        # Updating the arXiv object as well
        existing_arxiv_paper = db.session.query(ArxivPaper).filter(ArxivPaper.paper == paper.id).first()
        existing_arxiv_paper.json_data = e

        added = 1
    else:
        skipped = 1

    # Getting the tags for the papers
    tags = get_tags(paper_data)
    add_tags(tags, paper)

    db.session.commit()

    return paper_data, added, skipped

# Is this method redundant?


def fetch_entry(paper_id, download_to_s3=False):
    paper_id = paper_id.replace('_', '/')
    try:
        with urllib.request.urlopen(f'{BASE_URL}id_list={paper_id}') as url:
            response = url.read()
        parse = feedparser.parse(response)
        paper, added, skipped = handle_entry(parse.entries[0], download_to_s3)
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
    parser.add_argument('--wait-time', type=float, default=5.0,
                        help='wait time allows being gentle on the arxiv API (in seconds)')
    parser.add_argument('--break-on-no-added', type=int, default=1,
                        help='break out early if all returned query papers are already in db? 1=yes, 0=no')
    args, unknown = parser.parse_known_args()

    return args


def run():
    # Parse input arguments
    args = parse_arguments()
    logger.info(f'Searching arXiv for {args.search_query}')

    # Fetching papers
    fetch_papers(args.start_index, args.max_index, args.results_per_iteration,
                 args.wait_time, args.search_query, args.break_on_no_added)


if __name__ == "__main__":
    run()
