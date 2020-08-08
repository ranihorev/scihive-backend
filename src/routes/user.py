import os
import random
import string

from flask import Blueprint, jsonify
import logging

from flask_restful import Api, Resource, abort, reqparse, marshal_with, fields
from flask_jwt_extended import (create_access_token, jwt_required, jwt_refresh_token_required,
                                get_jwt_identity, get_raw_jwt, set_access_cookies, unset_access_cookies)

from google.oauth2 import id_token
from google.auth.transport import requests

from ..new_backend.models import User, db, RevokedToken
from .user_utils import generate_hash, verify_hash, get_user_by_email
from .notifications.index import deserialize_token
from src.new_backend.models import Paper

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
        data = parser.parse_args()

        if db.session.query(User.email).filter_by(email=data['email']).scalar() is not None:
            return {'message': 'User {} already exists'.format(data['email'])}

        email = data['email']
        password = generate_hash(data['password'])
        username = data['username']
        if not username:
            username = 'Anon_' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))

        try:
            new_user = User(username=username, email=email, password=password)
            db.session.add(new_user)
            db.session.commit()

            access_token = create_access_token(identity=data['email'])
            # refresh_token = create_refresh_token(identity=data['email'])
            resp = jsonify({'message': 'User was created', 'username': username, 'email': email})
            set_access_cookies(resp, access_token)
            return resp

        except Exception as e:
            return {'message': 'Something went wrong'}, 500


class UserLogin(Resource):
    def post(self):
        data = parser.parse_args()
        current_user = get_user_by_email(data['email'])

        if not current_user:
            return {'message': 'User {} doesn\'t exist'.format(data['email'])}, 401

        if verify_hash(data['password'], current_user.password):
            access_token = create_access_token(identity=data['email'])
            # refresh_token = create_refresh_token(identity=data['email'])

            resp = jsonify({'message': 'You are now logged in!',
                            'username': current_user.username,
                            'email': current_user.email}
                           )
            set_access_cookies(resp, access_token)
            return resp
        else:
            return {'message': 'Wrong credentials'}, 401


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
    @jwt_required
    def get(self):
        return {'message': 'success'}


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


class NewLogin(Resource):
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('token', help='This field cannot be blank', required=True, location='json')
        data = parser.parse_args()
        try:
            info = id_token.verify_oauth2_token(data['token'], requests.Request(), os.environ.get('GOOGLE_CLIENT_ID'))
            access_token = create_access_token(
                identity={'email': info['email'], 'source': 'google', 'first_name': info['given_name'], 'last_name': info['family_name']})
            resp = jsonify({'message': 'User was created/merged'})
            set_access_cookies(resp, access_token)
            return resp
        except ValueError as e:
            print(e)


api.add_resource(NewLogin, '/login2')
api.add_resource(UserRegistration, '/register')
api.add_resource(UserLogin, '/login')
api.add_resource(UserLogoutAccess, '/logout/access')
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
