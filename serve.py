import logging
import os
import json
import patch_marshal
from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_jwt_extended.exceptions import NoAuthorizationError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from sassutils.wsgi import SassMiddleware
from flask_caching import Cache
from routes.paper import app as paper_routes
from routes.paper_list import app as paper_list_routes
from routes.user import app as user_routes
from routes.library import app as library_routes
from routes.groups import app as groups_routes
from routes.admin import app as admin_routes
from routes.new_paper import app as new_paper_routes
from dotenv import load_dotenv
import pymongo
from logger import logger_config
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration


load_dotenv()
env = os.environ.get('ENV', 'development')

logger_config()
logger = logging.getLogger(__name__)

SENTRY_DSN = os.environ.get('SENTRY_DSN', '')


def before_send(event, hint):
    if 'exc_info' in hint:
        exc_type, exc_value, tb = hint['exc_info']
        if isinstance(exc_value, NoAuthorizationError):
            req = event.get('request', '')
            logger.warning(f'Unauthorized access - {req}')
            return None
    return event


if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[FlaskIntegration()],
        environment=env,
        before_send=before_send,
        ignore_errors=['TooManyRequests']
    )

app = Flask(__name__)
app.config.from_object(__name__)

app.config['ENV'] = env
cors = CORS(app, supports_credentials=True, origins=['*'])

if os.path.isfile('secret_key.txt'):
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
else:
    app.config['SECRET_KEY'] = 'devkey, should be in a file'

app.config['JWT_TOKEN_LOCATION'] = ['cookies']
app.config['JWT_COOKIE_CSRF_PROTECT'] = False
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = False

jwt = JWTManager(app)

if app.debug:
    app.wsgi_app = SassMiddleware(app.wsgi_app, {
        __name__: ('static/scss', 'static/css', '/static/css')
    })

limiter = Limiter(app, key_func=get_remote_address, default_limits=[
                  "5000 per hour", "200 per minute"])
cache = Cache(app, config={'CACHE_TYPE': 'simple'})

app.register_blueprint(paper_list_routes, url_prefix='/papers')
app.register_blueprint(paper_routes, url_prefix='/paper')
app.register_blueprint(user_routes, url_prefix='/user')
app.register_blueprint(library_routes, url_prefix='/library')
app.register_blueprint(groups_routes, url_prefix='/groups')
app.register_blueprint(admin_routes, url_prefix='/admin')
app.register_blueprint(new_paper_routes, url_prefix='/new_paper')


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

    ARXIV_CATEGORIES = json.load(open('relevant_arxiv_categories.json', 'r'))

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
