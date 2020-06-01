import json
import logging
import os
from typing import Dict, List
from urllib.parse import urljoin
import requests
from typing import Optional
from itsdangerous import URLSafeTimedSerializer
from src.routes.user_utils import get_user_by_email
from src.new_backend.models import Comment, unsubscribe_table, db, User, Paper

logger = logging.getLogger(__name__)

MAILGUN_KEY = os.environ.get('MAILGUN_KEY')
SERIALIZER_KEY = os.environ.get('SERIALIZER_KEY')
serializer = URLSafeTimedSerializer(SERIALIZER_KEY)

FRONTEND_BASE_URL = os.environ.get('FRONTEND_URL')
BASE_UNSUBSCRIBE_LINK = urljoin(FRONTEND_BASE_URL, '/user/unsubscribe/')


def create_unsubscribe_token(email, paper_id):
    return serializer.dumps([email, paper_id])


def deserialize_token(token):
    return serializer.loads(token)


def new_reply_notification(email: str, name: str, paper_id: str, paper_title: str):
    # TODO: update this function
    return
    # if has_user_unsubscribed(email, paper_id):
    #     return
    variables = {
        "first_name": name,
        "text": f"You have got a new reply to your comment on '{paper_title}'",
        "link": urljoin(FRONTEND_BASE_URL, '/paper', f'/{paper_id}'),
        "mute_link": urljoin(BASE_UNSUBSCRIBE_LINK, create_unsubscribe_token(email, paper_id))
    }

    send_email(address=email, name=name, variables=variables, template="new_reply",
               subject="You have got a new reply to your comment")


# users is a list of {email, name} dicts
def new_comment_notification(user_id: Optional[int], paper_id: int, comment_id: int):
    paper = Paper.query.get(paper_id)
    paper_id = paper.id
    paper_title = paper.title
    unsubscribed_users = db.session.query(unsubscribe_table.c.user_id).filter(
        unsubscribe_table.c.paper_id == paper_id).all()

    ignore_users = [u.user_id for u in unsubscribed_users]
    if user_id is not None:
        ignore_users.append(user_id)

    base_q = db.session.query(Comment.user_id.label('id'), User.email,
                              User.username).join(Comment.user).distinct(Comment.user_id)
    send_to_users = base_q.filter(Comment.paper_id == paper_id, Comment.user_id.notin_(
        ignore_users), Comment.user_id != None).all()

    # notify the user who uploaded if that user hasn't unsubscribed and not already on the list
    if paper.uploaded_by and (paper.uploaded_by.id not in ignore_users) and (paper.uploaded_by not in send_to_users):
        send_to_users.append(paper.uploaded_by)

    logger.info(f'Sending notification on comment {comment_id} to {len(send_to_users)} users')
    for u in send_to_users:
        variables = {
            "first_name": u.username,
            "text": f"A new comment was posted on a paper you are following - {paper_title}",
            "link": urljoin(FRONTEND_BASE_URL, f'/paper/{paper_id}#highlight-{comment_id}'),
            "mute_link": urljoin(BASE_UNSUBSCRIBE_LINK, create_unsubscribe_token(u.email, paper_id))
        }
        shortened_title = paper_title
        max_length = 40
        if len(shortened_title) > max_length:
            shortened_title = shortened_title[:max_length] + '...'
        send_email(address=u.email, name=u.username, variables=variables, template="new_reply",
                   subject=f"New comment on {shortened_title}")


def send_email(address: str, name: str, variables: Dict[str, str], subject: str, template: str):
    try:
        return requests.post(
            "https://api.mailgun.net/v3/email.scihive.org/messages",
            auth=("api", MAILGUN_KEY),
            data={"from": "Scihive <noreply@scihive.org>",
                  "to": f"{name} <{address}>",
                  "subject": subject,
                  "template": template,
                  "h:X-Mailgun-Variables": f'{json.dumps(variables)}'})
    except Exception as e:
        logger.error(f'Failed to send email - {e}')
        return
