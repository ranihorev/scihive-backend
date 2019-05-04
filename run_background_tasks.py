import logging
import threading

import schedule
import time
from papers_utils.fetch_papers import fetch_papers_main
from papers_utils.twitter_daemon import main_twitter_fetcher

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

    while True:
        schedule.run_pending()
        time.sleep(10)