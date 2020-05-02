import logging
import uuid
from datetime import datetime
from flask_jwt_extended import get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash

from src.new_backend.models import User, db
from flask_restful import abort

logger = logging.getLogger(__name__)


def get_user_by_email(email: str = None):
    if not email:
        email = get_jwt_identity()
    user = User.query.filter_by(email=email).first()
    if not user:
        abort(404, message='User not found')
    return user


def generate_hash(password):
    return generate_password_hash(password)


def verify_hash(password, hash):
    return check_password_hash(hash, password)


def get_user():
    current_user = get_jwt_identity()

    if current_user:
        return User.query.filter(User.email == current_user).first()

    return None
