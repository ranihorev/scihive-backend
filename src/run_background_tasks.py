import logging
import threading
import os
import schedule
import time
from .scrapers.arxiv import run as run_arxiv
from .scrapers.twitter import main_twitter_fetcher
from .scrapers.paperswithcode import run as run_paperswithcode


def run_threaded(job_func):
    job_thread = threading.Thread(target=job_func)
    job_thread.start()


def run_scheduled_tasks():
    logger = logging.getLogger(__name__)

    logger.info('Start background tasks')
    schedule.every(int(os.environ.get('TWITTER_FREQ_HOURS', 3.15))).hours.do(run_threaded, main_twitter_fetcher)
    # schedule.every(int(os.environ.get('PAPERS_WITH_CODE_FREQ_HOURS', 6.2))).hours.do(run_threaded, run_paperswithcode)
    schedule.every(int(os.environ.get('ARXIV_FREQ_HOURS', 4.2))).hours.do(run_threaded, run_arxiv)

    while True:
        schedule.run_pending()
        time.sleep(10)
