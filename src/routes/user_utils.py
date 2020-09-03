import logging
from typing import Optional
import uuid
from datetime import datetime
from flask_jwt_extended import get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash

from src.new_backend.models import User, db
from flask_restful import abort

logger = logging.getLogger(__name__)


def get_user_by_email(email: str = None) -> User:
    if not email:
        email = get_jwt_email()
    user = User.query.filter_by(email=email).first()
    if not user:
        abort(404, message='User not found')
    return user


def generate_hash(password):
    return generate_password_hash(password)


def verify_hash(password, hash):
    return check_password_hash(hash, password)


def get_user_optional() -> Optional[User]:
    current_user = get_jwt_email()

    if current_user:
        return User.query.filter(User.email == current_user).first()

    return None


def get_jwt_email() -> Optional[str]:
    current_user = get_jwt_identity()
    if not current_user:
        return None

    if isinstance(current_user, dict):
        return current_user['email']
    return current_user
