import logging
import os

from src import app
from flask_cors import CORS
from flask_graphql import GraphQLView
from flask_jwt_extended import JWTManager
from flask_jwt_extended.exceptions import NoAuthorizationError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from sassutils.wsgi import SassMiddleware
from flask_caching import Cache
from .routes.paper import app as paper_routes
from .routes.paper_list import app as paper_list_routes
from .routes.user import app as user_routes
from .routes.library import app as library_routes
from .routes.groups import app as groups_routes
from .routes.admin import app as admin_routes
from .routes.new_paper import app as new_paper_routes
from dotenv import load_dotenv
from .logger import logger_config
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
from .new_backend.models import db_session
from .new_backend.schema import schema

load_dotenv()
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

app.add_url_rule('/graphql', view_func=GraphQLView.as_view('graphql', schema=schema, graphiql=True,
                                                           context={'session': db_session}))


@app.route('/test')
def hello_world():
    return 'Hello, World!'

@app.teardown_appcontext
def shutdown_session(exception=None):
    db_session.remove()

