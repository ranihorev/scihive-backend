import logging
import os
import sys
env = os.environ.get('FLASK_ENV', 'development')

from . import flask_app, socketio_app

is_dev = env == 'development'
logger = logging.getLogger(__name__)

port = int(os.environ.get('PORT', 5000))
host = os.environ.get('HOST', '0.0.0.0' if not is_dev else None)

if __name__ == "__main__":
    if sys.argv[0].endswith('flask'):
        if sys.argv[1] != 'run':
            logger.info('Running cli function')
        else:
            logger.info('Running flask in debug mode (without socket-io)')
