from flask import Blueprint
import logging
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_restful import Api, Resource, reqparse, abort
from . import db_acronyms
from routes.user import find_by_email

app = Blueprint('admin', __name__)
api = Api(app)
logger = logging.getLogger(__name__)


def non_empty_string(s):
    if not s:
        raise ValueError("Must not be empty string")
    return s


class AddAcronym(Resource):
    method_decorators = [jwt_required]

    def post(self):
        current_user = find_by_email(get_jwt_identity())
        if not current_user.get('isAdmin', False):
            abort(401, message='Not an admin')
        parser = reqparse.RequestParser()
        parser.add_argument('longForm', type=non_empty_string, required=True)
        parser.add_argument('shortForm', type=non_empty_string, required=True)
        data = parser.parse_args()
        db_acronyms.update_one({'short_form': data['shortForm']}, {'$set': {'verified': data['longForm']}}, True)
        return {'message': 'success'}


api.add_resource(AddAcronym, "/new_acronym")