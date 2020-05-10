import logging
import threading

import schedule
import time
from src.new_backend.scrapers.arxiv import run as run_arxiv
from src.new_backend.scrapers.twitter import main_twitter_fetcher
from src.new_backend.scrapers.paperswithcode import run as run_paperswithcode


def run_threaded(job_func):
    job_thread = threading.Thread(target=job_func)
    job_thread.start()


def run_scheduled_tasks():
    logger = logging.getLogger(__name__)

    logger.info('Start background tasks')
    schedule.every(30).minutes.do(run_threaded, main_twitter_fetcher)
    schedule.every(6).hours.do(run_threaded, run_paperswithcode)
    schedule.every(3).hours.do(run_threaded, run_arxiv)

    while True:
        schedule.run_pending()
        time.sleep(10)
