import os

from flask import Blueprint, jsonify
import logging
from flask_jwt_extended.view_decorators import jwt_optional

from flask_restful import Api, Resource, abort, reqparse, marshal_with, fields
from flask_jwt_extended import (create_access_token, jwt_required, jwt_refresh_token_required,
                                get_jwt_identity, get_raw_jwt, set_access_cookies, unset_access_cookies)

from google.oauth2 import id_token
from google.auth.transport import requests

from ..models import User, db, RevokedToken, Paper
from .user_utils import generate_hash, get_jwt_email, get_user_optional, verify_hash, get_user_by_email
from .notifications.index import deserialize_token

app = Blueprint('user', __name__)
api = Api(app)
logger = logging.getLogger(__name__)

parser = reqparse.RequestParser()
parser.add_argument('email', help='This field cannot be blank', required=True)
parser.add_argument('password', help='This field cannot be blank', required=True)
parser.add_argument('username', required=False)

# Based on https://github.com/oleg-agapov/flask-jwt-auth/


def make_error(status_code, message):
    response = jsonify()
    response.status_code = status_code
    return response


class UserRegistration(Resource):
    def post(self):
        abort(404, message='Password registration has been removed')


def get_user_profile(user: User):
    return {'username': user.username, 'firstName': user.first_name,
            'lastName': user.last_name, 'email': user.email, 'provider': user.provider}


class UserLogin(Resource):
    def post(self):
        data = parser.parse_args()
        current_user = get_user_by_email(data['email'])

        if not current_user:
            abort(401, message='User {} doesn\'t exist'.format(data['email']))
        elif current_user.pending:
            abort(403, message='User is pending. Please log in via Google')
        elif current_user.provider:
            abort(403, message='Please log in via Google')

        if verify_hash(data['password'], current_user.password):
            access_token = create_access_token(identity=data['email'])
            # refresh_token = create_refresh_token(identity=data['email'])

            resp = jsonify({'message': 'You are now logged in!',
                            'username': current_user.username,
                            'email': current_user.email}
                           )
            set_access_cookies(resp, access_token)
            return get_user_profile(current_user)
        else:
            return abort(401, message="Wrong credentials")


class UserLogoutAccess(Resource):
    @jwt_required
    def post(self):
        jti = get_raw_jwt()['jti']
        try:
            db.session.add(RevokedToken(token=jti))
            db.session.commit()
            resp = jsonify({'message': 'Access token has been revoked'})
            unset_access_cookies(resp)
            return resp
        except:
            return {'message': 'Something went wrong'}, 500


class TokenRefresh(Resource):
    @jwt_refresh_token_required
    def post(self):
        current_user = get_jwt_identity()
        access_token = create_access_token(identity=current_user)
        return {'access_token': access_token}


class ValidateUser(Resource):

    @jwt_optional
    def get(self):
        user = get_user_optional()
        if user:
            return get_user_profile(user)
        return None


class Unsubscribe(Resource):

    @marshal_with({'title': fields.String})
    def post(self, token):
        try:
            email, paper_id = deserialize_token(token)
            user = get_user_by_email(email)
            # Verify paper exists
            paper = Paper.query.get_or_404(paper_id)
        except Exception as e:
            abort(404, message='invalid token')
            return

        user.unsubscribed_papers.append(paper)
        db.session.commit()
        return paper


class GoogleLogin(Resource):
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('token', help='This field cannot be blank', required=True, location='json')
        data = parser.parse_args()
        try:
            info = id_token.verify_oauth2_token(data['token'], requests.Request(), os.environ.get('GOOGLE_CLIENT_ID'))
        except ValueError as e:
            print(e)
            abort(403, message='invalid token')

        email = info['email']

        current_user_email = get_jwt_email()
        if current_user_email and current_user_email != email:
            # TODO: Allow linking non-matching email addresses
            abort(403, message='Your Google email address does not match your existing user')

        # create user if not missing
        user = User.query.filter_by(email=email).first()
        first_name: str = info.get('given_name')
        last_name: str = info.get('family_name')
        if not user:
            username = first_name + ' ' + last_name
            username.replace(' ', '_')
            new_user = User(username=username,
                            email=email, password='', first_name=first_name, last_name=last_name, provider='Google')
            db.session.add(new_user)
            db.session.commit()
        elif not user.provider:
            user.first_name = first_name
            user.last_name = last_name
            user.provider = 'Google'
            user.pending = False
            db.session.commit()

        access_token = create_access_token(
            identity={'email': email, 'provider': 'Google', 'first_name': first_name, 'last_name': last_name})
        resp = jsonify({'message': 'User was created/merged'})
        set_access_cookies(resp, access_token)
        return resp


api.add_resource(GoogleLogin, '/google_login')
api.add_resource(UserRegistration, '/register')
api.add_resource(UserLogin, '/login')
api.add_resource(UserLogoutAccess, '/logout')
api.add_resource(TokenRefresh, '/token/refresh')
api.add_resource(ValidateUser, '/validate')
api.add_resource(Unsubscribe, '/unsubscribe/<token>')


# # new reply

#  try:
#             comment_user_email = comment.get('user').get('email')
#             current_user_email = get_jwt_identity()
#             if comment_user_email and comment_user_email != current_user_email:
#                 paper = get_paper_by_id(paper_id, {"title": 1})
#                 threading.Thread(target=new_reply_notification, args=(
#                     comment_user_email, comment['user']['username'], paper_id, paper['title'])).start()
#         except Exception as e:
#             logger.error(f'Failed to notify on a new reply - {e}')
