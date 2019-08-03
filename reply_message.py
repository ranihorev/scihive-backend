import os
import requests


def send_message(to, subject, text, html):
    requests.post(
        "https://api.mailgun.net/v3/email.scihive.org/messages",
        auth=("api", os.environ["MAILGUN_API"]),
        data={"from": "SciHive <mailgun@email.scihive.org>",
              "to":[to],
              "subject": subject,
              "text":text,
              "html":html
             }
    )

def send_reply_message(to, user_1, user_2, paper_id, comment, reply):
    requests.post(
        "https://api.mailgun.net/v3/email.scihive.org/messages",
        auth=("api", os.environ["MAILGUN_API"]),
        data={"from": "SciHive <mailgun@email.scihive.org>",
              "to":[to],
              "subject": "Reply to your comment on SciHive",
              "text":"""Hello, {0}!\n{1} has replied to your comment on SciHive:
                     \n{2}\n~{0}\n{3}\n~{1}\nClick here to view site.""".format(user_1, user_2, comment, reply),
              "html":"""<p><b>Hello, {0}!</b><br>{1} has replied to your comment on SciHive:</p>
                     <p>{2}<br>~{0}</p><p>{3}<br>~{1}</p><br>
                     <a href='https://www.scihive.org/paper/{4}'>Click here to view site.</a>""".format(user_1, user_2, comment,
                                                                                                        reply, paper_id)
             }
    )

