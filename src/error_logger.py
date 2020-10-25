import os
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
from flask_jwt_extended.exceptions import NoAuthorizationError


def before_send(event, hint):
    if 'exc_info' in hint:
        exc_type, exc_value, tb = hint['exc_info']
        if isinstance(exc_value, NoAuthorizationError):
            req = event.get('request', '')
            return None
    return event


def init_sentry(env: str):
    SENTRY_DSN = os.environ.get('SENTRY_DSN', '')
    if SENTRY_DSN:
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            integrations=[FlaskIntegration()],
            environment=env,
            before_send=before_send,
            ignore_errors=['TooManyRequests']
        )
