import logging
import os
import sys
from src import app

env = os.environ.get('ENV', 'development')

# -----------------------------------------------------------------------------
# int main
# -----------------------------------------------------------------------------

port = int(os.environ.get('PORT', 5000))
logger = logging.getLogger(__name__)

# Don't run server if there are command arguments
if len(sys.argv) == 1:
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
else:
    logger.info('Running cli function')
