import logging
import os

from src import app
# create the DB:
from .new_backend.models import db

from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_jwt_extended.exceptions import NoAuthorizationError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_caching import Cache
from .routes.paper import app as paper_routes
from .routes.comments import app as comments_routes
from .routes.paper_list import app as paper_list_routes
from .routes.user import app as user_routes
from .routes.groups import app as groups_routes
from .routes.admin import app as admin_routes
from .routes.new_paper import app as new_paper_routes
from .new_backend.scrapers import arxiv
from .new_backend.scrapers import paperswithcode
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
from src.new_backend.scrapers import twitter
import threading
from .run_background_tasks import run_scheduled_tasks


env = os.environ.get('ENV', 'development')

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

limiter = Limiter(app, key_func=get_remote_address, default_limits=[
    "5000 per hour", "200 per minute"])
cache = Cache(app, config={'CACHE_TYPE': 'simple'})

app.register_blueprint(paper_list_routes, url_prefix='/papers')
app.register_blueprint(paper_routes, url_prefix='/paper')
app.register_blueprint(comments_routes, url_prefix='/paper')
app.register_blueprint(user_routes, url_prefix='/user')
app.register_blueprint(groups_routes, url_prefix='/groups')
app.register_blueprint(admin_routes, url_prefix='/admin')
app.register_blueprint(new_paper_routes, url_prefix='/new_paper')


is_main_process = not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true"
if os.environ.get('RUN_BACKGROUND_TASKS') and is_main_process:
    tasks = threading.Thread(target=run_scheduled_tasks, daemon=True)
    tasks.start()


@app.cli.command("fetch-arxiv")
def fetch_arxiv():
    arxiv.run()


@app.cli.command("fetch-paperswithcode")
def fetch_papers_with_code():
    paperswithcode.run()


@app.cli.command("fetch-twitter")
def fetch_twitter():
    twitter.main_twitter_fetcher()


@app.route('/test')
def hello_world():
    return 'Hello, World!'
