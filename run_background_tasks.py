import logging
import threading

import schedule
import time
from tasks.fetch_papers import fetch_papers_main
from tasks.twitter_daemon import main_twitter_fetcher
from tasks.paperswithcode import fetch_code_data

from logger import logger_config

from dotenv import load_dotenv
load_dotenv()

def run_threaded(job_func):
    job_thread = threading.Thread(target=job_func)
    job_thread.start()


if __name__ == '__main__':
    logger_config(info_filename='background_tasks.log')
    logger = logging.getLogger(__name__)

    logger.info('Start background tasks')
    schedule.every(30).minutes.do(run_threaded, main_twitter_fetcher)
    schedule.every(3).hours.do(run_threaded, fetch_papers_main)
    schedule.every(3).hours.do(run_threaded, fetch_code_data)

    while True:
        schedule.run_pending()
        time.sleep(10)
