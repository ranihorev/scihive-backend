import json
import logging
import os
from typing import Dict, List, Tuple
from urllib.parse import urljoin
import requests
from typing import Optional
from itsdangerous import URLSafeTimedSerializer
from ...models import Comment, Reply, unsubscribe_table, db, User, Paper

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


def new_invite_notification(user_id: int, paper_id: int, invited_by_name: str, message: str):
    paper: Paper = Paper.query.get(paper_id)
    user: User = User.query.get(user_id)

    variables = {
        "first_name": user.first_name or user.username,
        "text": message,
        "link": urljoin(FRONTEND_BASE_URL, f'/paper/{paper_id}'),
    }
    subject = f"{invited_by_name} invited you to collaborate on {paper.title}"
    send_email(address=user.email, name=user.first_name or user.username,
               variables=variables, template="paper_invite", subject=subject)


def get_unsubscribed_users(user_id: Optional[int], paper_id: int) -> List[int]:
    # Users to ignore
    unsubscribed_users = db.session.query(unsubscribe_table.c.user_id).filter(
        unsubscribe_table.c.paper_id == paper_id).all()

    ignore_users = [u.user_id for u in unsubscribed_users]
    # Ignore the current commenting user
    if user_id is not None:
        ignore_users.append(user_id)
    return ignore_users


def send_mail_for_paper_comment_or_reply(send_to_users: List[User], text: str, subject: str, paper_id: int, comment_id: int):
    for user in send_to_users:
        variables = {
            "first_name": user.username,
            "text": text,
            "link": urljoin(FRONTEND_BASE_URL, f'/paper/{paper_id}#highlight-{comment_id}'),
            "mute_link": urljoin(BASE_UNSUBSCRIBE_LINK, create_unsubscribe_token(user.email, paper_id))
        }
        send_email(address=user.email, name=user.username, variables=variables, template="new_reply", subject=subject)


def get_shortened_text(paper_title: str, max_length: int = 40):
    shortened_title = paper_title
    if len(shortened_title) > max_length:
        shortened_title = shortened_title[:max_length] + '...'
    return shortened_title


def new_reply_notification(user_id: Optional[int], paper_id: int, reply_id: int):
    paper = Paper.query.get(paper_id)
    paper_title = paper.title
    reply: Reply = Reply.query.get(reply_id)
    parent_comment: Comment = reply.parent
    parent_comment_id = parent_comment.id

    # Users to ignore
    ignore_users = get_unsubscribed_users(user_id, paper_id)

    # Get all the users that replied to this comment
    base_q = db.session.query(Reply.user_id, User).join(Reply.user).distinct(Reply.user_id)
    send_to_users = base_q.filter(Reply.parent_id == parent_comment_id,
                                  Reply.user_id.notin_(ignore_users), Reply.user_id != None).all()
    send_to_users = [user for _, user in send_to_users]

    if parent_comment.user and parent_comment.user_id != user_id and parent_comment.user not in ignore_users:
        send_to_users.append(parent_comment.user)

    logger.info(f'Sending notification on reply {reply_id} to {len(send_to_users)} users')
    text = f"You have got a new reply to your comment on '{paper_title}'"
    subject = f"New reply on '{get_shortened_text(paper_title)}'"
    send_mail_for_paper_comment_or_reply(send_to_users=send_to_users, comment_id=parent_comment_id,
                                         paper_id=paper_id, text=text, subject=subject)


def new_comment_notification(user_id: Optional[int], paper_id: int, comment_id: int):
    paper = Paper.query.get(paper_id)
    paper_title = paper.title

    # Users to ignore
    ignore_users = get_unsubscribed_users(user_id, paper_id)

    # Get all the users that replied to this paper
    base_q = db.session.query(Comment.user_id, User).join(Comment.user).distinct(Comment.user_id)
    send_to_users = base_q.filter(Comment.paper_id == paper_id, Comment.user_id.notin_(
        ignore_users), Comment.user_id != None).all()
    send_to_users = [user for _, user in send_to_users]

    # Add the paper creator - if hasn't unsubscribed and not already on the list
    if paper.uploaded_by and (paper.uploaded_by.id not in ignore_users) and (paper.uploaded_by not in send_to_users):
        send_to_users.append(paper.uploaded_by)

    # Send emails
    logger.info(f'Sending notification on comment {comment_id} to {len(send_to_users)} users')
    if not send_to_users:
        return

    text = f"A new comment was posted on a paper you are following - {paper_title}"
    subject = f"New comment on '{get_shortened_text(paper_title)}'"
    send_mail_for_paper_comment_or_reply(send_to_users=send_to_users, comment_id=comment_id,
                                         paper_id=paper_id, text=text, subject=subject)


def send_email(address: str, name: str, variables: Dict[str, str], subject: str, template: str):
    if not MAILGUN_KEY:
        logger.warning('Maingun key is missing. Skipping sending')
        return
    try:
        response = requests.post(
            "https://api.mailgun.net/v3/email.scihive.org/messages",
            auth=("api", MAILGUN_KEY),
            data={"from": "Scihive <noreply@scihive.org>",
                  "to": f"{name} <{address}>",
                  "subject": subject,
                  "template": template,
                  "h:X-Mailgun-Variables": f'{json.dumps(variables)}'})
        logger.info(f'Email was sent successfully to {address}')
        return response
    except Exception as e:
        logger.error(f'Failed to send email - {e}')
        return
