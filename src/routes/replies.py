import logging
from datetime import datetime

from flask import Blueprint
from flask_jwt_extended import get_jwt_identity, jwt_optional, jwt_required
from flask_restful import (Api, Resource, abort, fields, inputs, marshal_with,
                           reqparse)
from sqlalchemy import or_
from typing import Optional
from src.new_backend.models import Collection, Comment, Paper, Reply, db, User

app = Blueprint('replies', __name__)
api = Api(app)
logger = logging.getLogger(__name__)

replies_fields = {
    'id': fields.String,
    'user': fields.String(attribute='user.username'),
    'text': fields.String,
    'createdAt': fields.DateTime(dt_format='rfc822', attribute='creation_date'),
}

EMPTY_FIELD_MSG = 'This field cannot be blank'

class ReplyResource(Resource):

    def _get_reply(self, reply_id):

        reply = Reply.query.get_or_404(reply_id)

        return reply


    @marshal_with(replies_fields, envelope='reply')
    def post(self, reply_id):
        reply = self._get_reply(reply_id)

        edit_reply_parser = reqparse.RequestParser()
        print(edit_reply_parser)
        edit_reply_parser.add_argument('text', help=EMPTY_FIELD_MSG, type=str, location='json', required=False)
        #edit_comment_parser.add_argument('visibility', help=EMPTY_FIELD_MSG, type=visibilityObj, location='json',
        #                                 required=True)
        data = edit_reply_parser.parse_args()
        print(data)
        reply.text = data['text']
        db.session.commit()


        return reply


api.add_resource(ReplyResource, "/<reply_id>")
