import logging

from flask_jwt_extended.view_decorators import jwt_optional
from flask_socketio import join_room, leave_room

from . import socketio_app
from .routes.paper_query_utils import get_paper_or_none
from .routes.permissions_utils import enforce_permissions_to_paper
from .routes.user_utils import get_user_optional

logger = logging.getLogger(__name__)


@socketio_app.on('message')
def handle_message(message):
    print('received message: ' + message)


@socketio_app.on('join')
@jwt_optional
def on_join(data):
    paper_id = data.get('paperId')
    token = data.get('token')
    if not paper_id:
        logger.warning('paperId is missing')
        return
    current_user = get_user_optional()
    paper = get_paper_or_none(paper_id)
    if not paper:
        logger.warning(f'paper not found - {paper_id}')
        return
    enforce_permissions_to_paper(paper, current_user, token=token)
    join_room(paper_id)


@socketio_app.on('leave')
def on_leave(data):
    paper_id = data['paperId']
    if not paper_id:
        logger.warning('paperId is missing')
        return
    leave_room(paper_id)
