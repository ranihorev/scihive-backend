import json
import logging
import os
from typing import Dict, List

import requests
from itsdangerous import URLSafeTimedSerializer
from src.routes.user_utils import get_user_by_email

logger = logging.getLogger(__name__)

MAILGUN_KEY = os.environ.get('MAILGUN_KEY')
SERIALIZER_KEY = os.environ.get('SERIALIZER_KEY')
serializer = URLSafeTimedSerializer(SERIALIZER_KEY)

BASE_UNSUBSCRIBE_LINK = 'https://www.scihive.org/user/unsubscribe/'


def create_unsubscribe_token(email, paper_id):
    return serializer.dumps([email, paper_id])


def deserialize_token(token):
    return serializer.loads(token)


def has_user_unsubscribed(user_email, paper_id):
    user = get_user_by_email(user_email)
    return paper_id in user.get('mutedPapers', [])


def new_reply_notification(email: str, name: str, paper_id: str, paper_title: str):
    if has_user_unsubscribed(email, paper_id):
        return
    variables = {
        "first_name": name,
        "text": f"You have got a new reply to your comment on '{paper_title}'",
        "link": f"https://www.scihive.org/paper/{paper_id}",
        "mute_link": f"{BASE_UNSUBSCRIBE_LINK}{create_unsubscribe_token(email, paper_id)}"
    }

    send_email(address=email, name=name, variables=variables, template="new_reply",
               subject="You have got a new reply to your comment")


# users is a list of {email, name} dicts
def new_comment_notification(users: List[Dict[str, str]], paper_id: str, paper_title: str):
    for u in users:
        # Skip if user unsubscribed from that paper
        if has_user_unsubscribed(u.get('email'), paper_id):
            continue

        variables = {
            "first_name": u.get('name'),
            "text": f"A new comment was posted on a paper you are following - {paper_title}. Click below to view:",
            "link": f"https://www.scihive.org/paper/{paper_id}",
            "mute_link": f"{BASE_UNSUBSCRIBE_LINK}{create_unsubscribe_token(u.get('email'), paper_id)}"
        }
        shortened_title = paper_title
        max_length = 40
        if len(shortened_title) > max_length:
            shortened_title = shortened_title[:max_length] + '...'
        send_email(address=u.get('email'), name=u.get('name'), variables=variables, template="new_reply",
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
