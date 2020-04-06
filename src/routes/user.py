import random
import string

from flask import Blueprint, jsonify
import logging

from flask_restful import Resource, reqparse, Api
from flask_jwt_extended import (create_access_token, jwt_required, jwt_refresh_token_required,
                                get_jwt_identity, get_raw_jwt, set_access_cookies, unset_access_cookies)

from ..new_backend.models import User, db
from .user_utils import find_by_email, generate_hash, verify_hash, save_revoked_token

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
        current_user = find_by_email(data['email'])

        if not current_user:
            return {'message': 'User {} doesn\'t exist'.format(data['email'])}, 401

        if verify_hash(data['password'], current_user['password']):
            access_token = create_access_token(identity=data['email'])
            # refresh_token = create_refresh_token(identity=data['email'])

            resp = jsonify({'message': 'You are now logged in!',
                            'username': current_user['username'],
                            'email': current_user['email']}
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
            save_revoked_token(jti)
            resp = jsonify({'message': 'Access token has been revoked'})
            unset_access_cookies(resp)
            return resp
        except:
            return {'message': 'Something went wrong'}, 500


class UserLogoutRefresh(Resource):
    @jwt_refresh_token_required
    def post(self):
        jti = get_raw_jwt()['jti']
        try:
            save_revoked_token(jti)
            return {'message': 'Refresh token has been revoked'}
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


api.add_resource(UserRegistration, '/register')
api.add_resource(UserLogin, '/login')
api.add_resource(UserLogoutAccess, '/logout/access')
api.add_resource(UserLogoutRefresh, '/logout/refresh')
api.add_resource(TokenRefresh, '/token/refresh')
api.add_resource(ValidateUser, '/validate')