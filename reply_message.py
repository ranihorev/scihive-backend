import requests

def send_reply_message():
    requests.post(
        "https://api.mailgun.net/v3/SchiHive/messages",
        auth=("api", "API KEY"),
        data={"from": "SciHive <ADDR@DOMAIN.com>",
              "to":["user@example.com"],
              "subject": "Reply to your comment on SciHive",
              "text":"""Hello, User!\nJohn Doe has replied to your comment on Paper X:
                     \n{COMMENT}\n~User\n{REPLY}\n~John Doe\n\nClick here to view site.""",
              "html":"""<p><b>Hello, User!</b><br>John Doe has replied to your comment on Paper X:</p>
                     <p>{COMMENT}<br>~User</p><p>{REPLY}<br>~John Doe</p><br><br>
                     <a href='www.scihive.org/paperx'>Click here to view site.</a>"""
        }
    )

