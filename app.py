import logging
import os

from src import app
from dotenv import load_dotenv
import pymongo
from src.logger import logger_config

load_dotenv()
env = os.environ.get('ENV', 'development')

logger_config()
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# int main
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    logger.info('connecting to mongodb...')
    client = pymongo.MongoClient()
    mdb = client.arxiv
    db_papers = mdb.papers
    db_authors = mdb.authors
    sem_sch_papers = mdb.sem_sch_papers
    sem_sch_authors = mdb.sem_sch_authors
    network_requests = mdb.network_requests

    # start
    if env == 'production':
        # run on Tornado instead, since running raw Flask in prod is not recommended
        logger.info(f'starting tornado on port {port}')
        from tornado.wsgi import WSGIContainer
        from tornado.httpserver import HTTPServer
        from tornado.ioloop import IOLoop
        from tornado.log import enable_pretty_logging

        enable_pretty_logging()
        http_server = HTTPServer(WSGIContainer(app))
        http_server.listen(port)
        IOLoop.instance().start()
    elif env == 'development':
        logger.info(f'starting flask on port {port}')
        app.debug = False
        app.run(port=port, host='0.0.0.0')
    else:
        logger.error(f'ENV is missing or incorrect {env}')
