import logging
import os
import sys

from . import flask_app, socketio_app
env = os.environ.get('ENV', 'development')
is_dev = env == 'development'

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    logger = logging.getLogger(__name__)

    if sys.argv[0].endswith('flask'):
        if sys.argv[1] != 'run':
            logger.info('Running cli function')
        else:
            logger.info('Running flask in debug mode (without socket-io)')
    else:
        logger.info(f'starting flask on port {port}')
        socketio_app.run(app=flask_app, debug=is_dev, port=port, host='0.0.0.0' if not is_dev else None)
