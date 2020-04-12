import argparse
import logging
import threading

from src.tasks.fetch_papers import fetch_papers_main
from src.tasks.twitter_daemon import main_twitter_fetcher, recalculate
from src.tasks.paperswithcode import fetch_code_data

from src.logger import logger_config

from dotenv import load_dotenv
load_dotenv()


def run_threaded(job_func):
    job_thread = threading.Thread(target=job_func)
    job_thread.start()


if __name__ == '__main__':
    logger_config(info_filename='background_tasks.log')
    logger = logging.getLogger(__name__)

    parser = argparse.ArgumentParser(description='Run tasks')
    parser.add_argument('-ct', '--calc_twitter',  action="store_true", help='Recalculate twitter')
    parser.add_argument('-t', '--twitter',  action="store_true", help='Fetch twitter')
    parser.add_argument('-p', '--papers',  action="store_true", help='Fetch papers')
    parser.add_argument('-c', '--code',  action="store_true", help='Fetch code data')
    args = parser.parse_args()

    if args.calc_twitter:
        logger.info('Recalculating Twitter')
        recalculate()

    if args.twitter:
        logger.info('Fetching tweets')
        main_twitter_fetcher()

    if args.papers:
        logger.info('Fetching papers')
        fetch_papers_main()

    if args.code:
        logger.info('Fetching code data')
        fetch_code_data()

