import os
import eventlet

eventlet.monkey_patch()
import logging
import os
from typing import Tuple

from dotenv import load_dotenv
from easy_profile import EasyProfileMiddleware
from flask import Flask, jsonify
from flask_caching import Cache
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_socketio import SocketIO
# This is required to patch marshal
# noinspection PyUnresolvedReferences
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from werkzeug.exceptions import HTTPException

load_dotenv(dotenv_path=os.environ.get('ENV_FILE'))

from .error_logger import init_sentry
from .logger import logger_config
from .patch_marshal import *

from .models import Paper, db, init_db, paper_collection_table

logger_config()
env = os.environ.get('FLASK_ENV', 'development')
logger = logging.getLogger(__name__)


def create_app(env: str) -> Tuple[Flask, SocketIO]:
    flask_app = Flask(__name__)
    flask_app.config['ENV'] = env
    init_db(flask_app=flask_app)
    cors_allowed_origins = os.environ.get('FRONTEND_URL')
    if not cors_allowed_origins:
        logger.warning('Falling back to allow all origins. Not recommended in production!')
        cors_allowed_origins = '*'

    flask_app.url_map.strict_slashes = False
    if env == 'development':
        flask_app.wsgi_app = EasyProfileMiddleware(flask_app.wsgi_app)

    redis_url = os.environ.get('REDIS_URL')
    socketio_app = SocketIO(flask_app, cors_allowed_origins=[
                            cors_allowed_origins], engineio_logger=False, message_queue=redis_url)

    CORS(flask_app, supports_credentials=True, origins=[cors_allowed_origins])

    secret_key = os.environ.get('SECRET_KEY')
    if not secret_key:
        logger.warning('SECRET_KEY is missing')
    flask_app.config['SECRET_KEY'] = secret_key or 'devkey, should be in a file'

    flask_app.config['JWT_TOKEN_LOCATION'] = ['cookies']
    flask_app.config['JWT_COOKIE_CSRF_PROTECT'] = False
    flask_app.config['JWT_ACCESS_TOKEN_EXPIRES'] = False

    JWTManager(flask_app)

    Limiter(flask_app, key_func=get_remote_address, default_limits=[
        "10000 per hour", "500 per minute"])
    Cache(flask_app, config={'CACHE_TYPE': 'simple'})

    @flask_app.errorhandler(HTTPException)
    def main_error_handler(error):
        message = ''
        try:
            message = error.data.get('message')
        except Exception:
            pass
        response = jsonify(message)
        response.status_code = getattr(error, 'code', 500)
        return response

    with flask_app.app_context():
        flask_app.socketio_app = socketio_app

        from .routes.admin import app as admin_routes
        from .routes.comments import app as comments_routes
        from .routes.groups import app as groups_routes
        from .routes.new_paper import app as new_paper_routes
        from .routes.paper import app as paper_routes
        from .routes.paper_list import app as paper_list_routes
        from .routes.user import app as user_routes
        from .scrapers import arxiv, paperswithcode, twitter
        from .websocket import setup_websocket

        flask_app.register_blueprint(paper_list_routes, url_prefix='/papers')
        flask_app.register_blueprint(paper_routes, url_prefix='/paper')
        flask_app.register_blueprint(comments_routes, url_prefix='/paper')
        flask_app.register_blueprint(user_routes, url_prefix='/user')
        flask_app.register_blueprint(groups_routes, url_prefix='/groups')
        flask_app.register_blueprint(admin_routes, url_prefix='/admin')
        flask_app.register_blueprint(new_paper_routes, url_prefix='/new_paper')
        setup_websocket(socketio_app=socketio_app)

    @flask_app.cli.command("fetch-arxiv")
    def fetch_arxiv():
        arxiv.run()

    @flask_app.cli.command("fetch-paperswithcode")
    def fetch_papers_with_code():
        paperswithcode.run()

    @flask_app.cli.command("fetch-twitter")
    def fetch_twitter():
        twitter.main_twitter_fetcher()

    @flask_app.route('/health')
    def hello_world():
        return 'Running!'

    @flask_app.cli.command("fix-stars-count")
    def fix_stars_count():
        total_per_paper = db.session.query(paper_collection_table.c.paper_id, func.count(
            paper_collection_table.c.collection_id)).group_by(paper_collection_table.c.paper_id).all()
        with_stars = [p for p in total_per_paper if p[1] > 0]
        id_to_stars = {p[0]: p[1] for p in with_stars}
        papers = Paper.query.filter(Paper.id.in_(list(id_to_stars.keys()))).all()
        for p in papers:
            p.num_stars = id_to_stars[p.id]
        db.session.commit()

    return flask_app, socketio_app


init_sentry(env)
flask_app, socketio_app = create_app(env)
