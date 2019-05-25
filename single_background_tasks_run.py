import argparse
import logging
import threading

from tasks.fetch_papers import fetch_papers_main
from tasks.twitter_daemon import main_twitter_fetcher, recalculate

from logger import logger_config

from dotenv import load_dotenv
load_dotenv()

def run_threaded(job_func):
    job_thread = threading.Thread(target=job_func)
    job_thread.start()


if __name__ == '__main__':
    logger_config(info_filename='background_tasks.log')
    logger = logging.getLogger(__name__)

    parser = argparse.ArgumentParser(description='Run tasks')
    parser.add_argument('-t', '--twitter',  action="store_true", help='Recalculate twitter')
    args = parser.parse_args()

    if args.twitter:
        logger.info('Recalculating Twitter')
        recalculate()
    else:
        logger.info('Run background tasks once')
        fetch_papers_main()
        main_twitter_fetcher()
