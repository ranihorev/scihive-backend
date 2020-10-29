import logging
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Dict, List, Tuple, NamedTuple
from flask.app import Flask
from flask_restful import marshal

from flask import current_app
import requests
from diskcache import Cache
from flask_socketio import emit
from sqlalchemy.orm.exc import NoResultFound

from ..models import Author, MetadataState, Paper, db
from .file_utils import FileUploader
from .paper_query_utils import metadata_fields

cache = Cache('cache')
logger = logging.getLogger(__name__)


class AuthorObj(NamedTuple):
    first_name: str
    last_name: str
    org: List[str]

    def get_name(self):
        return f'{self.first_name} {self.last_name}'


def get_tag_text(tree, tag, default_value='') -> str:
    element = tree.find(f'.//{tag}')
    return element.text if element is not None else default_value


def get_all_tag_texts(tree, tag):
    element = tree.findall(f'.//{tag}')
    return [e.text for e in element]


def fetch_data_from_grobid(file_content) -> Tuple[bool, Dict[str, Any]]:
    try:
        grobid_url = os.environ.get('GROBID_URL')
        if not grobid_url:
            raise KeyError('Grobid URL is missing')
        grobid_res = requests.post(grobid_url + '/api/processHeaderDocument',
                                   data={'consolidateHeader': 1}, files={'input': file_content})
        if grobid_res.status_code == 503:
            raise Exception('Grobid is unavailable')
        content = re.sub(' xmlns="[^"]+"', '', grobid_res.text)
        tree = ET.fromstring(content)
    except Exception as e:
        logger.error(f'Failed to extract metadata for paper - {e}')
        return False, {'title': 'Untitled', 'authors': [], 'abstract': '', 'date': datetime.now()}

    title = get_tag_text(tree, 'title')

    authors_tree = tree.findall('.//author')
    authors: List[AuthorObj] = []
    for author_tree in authors_tree:
        author = AuthorObj(first_name=get_tag_text(author_tree, 'forename'),
                           last_name=get_tag_text(author_tree, 'surname'),
                           org=get_all_tag_texts(author_tree, 'orgName'))
        authors.append(author)
    abstract: str = tree.find('.//abstract') or ''
    if abstract:
        if abstract.getchildren():
            abstract = abstract.getchildren()[0].text
        else:
            abstract = abstract.text

    doi = get_tag_text(tree, 'idno')
    publish_date = None
    publish_date_raw = tree.find('.//date')
    if publish_date_raw is not None:
        try:
            publish_date = publish_date_raw.get('when')
            publish_date = datetime.strptime(publish_date, "%Y-%m-%d")
        except Exception as e:
            logger.error(f'Failed to extract date for {publish_date_raw.text}')

    return True, {'title': title or None, 'authors': authors, 'abstract': abstract, 'date': publish_date, 'doi': doi}


def extract_paper_metadata(app: Flask, paper_id: str):
    with app.app_context():
        paper: Paper = Paper.query.get_or_404(paper_id)
        paper.metadata_state = MetadataState.fetching  # TODO: move this to redis
        db.session.commit()
        file_content = requests.get(paper.local_pdf).content
        file_hash = FileUploader.calc_hash(file_content)
        # metadata, _ = cache.get(file_hash, expire_time=True)
        metadata = None
        if not metadata:
            logger.info(f'Fetching data from grobid for paper - {paper_id}')
            success, metadata = fetch_data_from_grobid(file_content)
            if success:
                logger.info(f'Fetched data from grobid! - {paper_id}')
                cache.set(file_hash, metadata, expire=24 * 60 * 60)
            else:
                emit('paperInfo', {'success': False}, namespace='/', room=str(paper.id))
                return

        if metadata['title']:
            paper.title = metadata['title']
        if metadata['abstract']:
            paper.abstract = metadata['abstract']
        if metadata['date']:
            paper.date = metadata['date']
        paper.doi = metadata['doi']

        # Create authors
        for current_author in metadata['authors']:
            try:
                author = Author.query.filter(
                    Author.first_name == current_author.first_name, Author.last_name == current_author.last_name).one()
            except NoResultFound:
                author = Author(name=f'{current_author.first_name} {current_author.last_name}',
                                first_name=current_author.first_name, last_name=current_author.last_name, organization=current_author.org)
                db.session.add(author)
            author.papers.append(paper)

        paper.last_update_date = datetime.now()
        paper.metadata_state = MetadataState.ready
        db.session.commit()
        emit('paperInfo', {'success': True, 'data': marshal(paper, metadata_fields)}, namespace='/', room=str(paper.id))
