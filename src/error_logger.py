import os
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
from flask_jwt_extended.exceptions import NoAuthorizationError
from werkzeug.exceptions import Forbidden, NotFound


def init_sentry(env: str):
    SENTRY_DSN = os.environ.get('SENTRY_DSN', '')
    if SENTRY_DSN:
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            integrations=[FlaskIntegration()],
            environment=env,
            ignore_errors=['TooManyRequests', NotFound, NoAuthorizationError, Forbidden]
        )
