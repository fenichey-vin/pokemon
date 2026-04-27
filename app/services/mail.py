import smtplib
from email.message import EmailMessage
from flask import current_app

_SUBJECT = "Your Pokemon Catalog login code"
_BODY = (
    "Your login code is: {code}\n"
    "This code expires in 15 minutes.\n"
    "If you didn't request this, ignore this email."
)


def send_login_code(to_email: str, code: str) -> bool:
    host = current_app.config["MAIL_SMTP_HOST"]
    port = int(current_app.config["MAIL_SMTP_PORT"])
    user = current_app.config["MAIL_SMTP_USER"]
    password = current_app.config["MAIL_SMTP_PASSWORD"]
    from_addr = current_app.config["MAIL_FROM"]

    msg = EmailMessage()
    msg["Subject"] = _SUBJECT
    msg["From"] = from_addr
    msg["To"] = to_email
    msg.set_content(_BODY.format(code=code))

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port) as smtp:
                smtp.login(user, password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(user, password)
                smtp.send_message(msg)
        return True
    except Exception as e:
        current_app.logger.error("SMTP error sending to %s: %s", to_email, e)
        return False
