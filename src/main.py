import logging
import os
import copy

from flask_jwt_extended.view_decorators import jwt_optional
from werkzeug.exceptions import HTTPException

from . import app
# create the DB:
from .models import db, Paper, paper_collection_table
from sqlalchemy import func
from flask_cors import CORS
from flask_jwt_extended import JWTManager, verify_jwt_in_request
from flask_jwt_extended.exceptions import InvalidHeaderError, NoAuthorizationError
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
from .scrapers import arxiv
from .scrapers import paperswithcode
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
from .scrapers import twitter
from .run_background_tasks import run_scheduled_tasks
from flask import Blueprint, jsonify


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

# TODO: fix this:
cors = CORS(app, supports_credentials=True, origins=['*'])

secret_key = os.environ.get('SECRET_KEY')
print(secret_key)
if not secret_key:
    logger.warning('SECRET_KEY is missing')
app.config['SECRET_KEY'] = secret_key or 'devkey, should be in a file'

app.config['JWT_TOKEN_LOCATION'] = ['cookies']
app.config['JWT_COOKIE_CSRF_PROTECT'] = False
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = False

jwt = JWTManager(app)

limiter = Limiter(app, key_func=get_remote_address, default_limits=[
    "10000 per hour", "500 per minute"])
cache = Cache(app, config={'CACHE_TYPE': 'simple'})


@app.errorhandler(HTTPException)
def main_error_handler(error):
    message = ''
    try:
        message = error.data.get('message')
    except Exception:
        pass
    response = jsonify(message)
    response.status_code = getattr(error, 'code', 500)
    return response


def register_collab_blueprint(bp: Blueprint, url_prefix: str):
    new_bp = copy.copy(bp)
    new_bp.name = 'collab_' + new_bp.name

    @new_bp.before_request
    def enforce_login():
        try:
            verify_jwt_in_request()
        except (NoAuthorizationError, InvalidHeaderError):
            return jsonify({'msg': 'Unauthorized access'}), 403

    app.register_blueprint(new_bp, url_prefix=url_prefix)


app.register_blueprint(paper_list_routes, url_prefix='/papers')
app.register_blueprint(paper_routes, url_prefix='/paper')
app.register_blueprint(comments_routes, url_prefix='/paper')
app.register_blueprint(user_routes, url_prefix='/user')
app.register_blueprint(groups_routes, url_prefix='/groups')
app.register_blueprint(admin_routes, url_prefix='/admin')
app.register_blueprint(new_paper_routes, url_prefix='/new_paper')


@app.cli.command("fetch-arxiv")
def fetch_arxiv():
    arxiv.run()


@app.cli.command("fetch-paperswithcode")
def fetch_papers_with_code():
    paperswithcode.run()


@app.cli.command("fetch-twitter")
def fetch_twitter():
    twitter.main_twitter_fetcher()


@app.cli.command("run-background-tasks")
def background_tasks():
    run_scheduled_tasks()


@app.route('/test')
def hello_world():
    return 'Hello, World!'


@app.cli.command("fix-stars-count")
def fix_stars_count():
    total_per_paper = db.session.query(paper_collection_table.c.paper_id, func.count(
        paper_collection_table.c.collection_id)).group_by(paper_collection_table.c.paper_id).all()
    with_stars = [p for p in total_per_paper if p[1] > 0]
    id_to_stars = {p[0]: p[1] for p in with_stars}
    papers = Paper.query.filter(Paper.id.in_(list(id_to_stars.keys()))).all()
    for p in papers:
        p.num_stars = id_to_stars[p.id]
    db.session.commit()
