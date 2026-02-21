"""Email delivery via Gmail SMTP or SendGrid."""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def _require(key: str) -> str:
    value = os.environ.get(key, "").strip()
    if not value:
        raise RuntimeError(f"Environment variable {key!r} is not set")
    return value


def send_digest(subject: str, body: str) -> None:
    """
    Send the digest email.

    Reads EMAIL_PROVIDER, EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENT
    from environment variables (set as GitHub Secrets in CI).
    """
    provider = os.environ.get("EMAIL_PROVIDER", "gmail").lower()
    sender = _require("EMAIL_SENDER")
    password = _require("EMAIL_PASSWORD")
    recipient = _require("EMAIL_RECIPIENT")

    if provider == "sendgrid":
        _send_sendgrid(sender, password, recipient, subject, body)
    else:
        _send_gmail(sender, password, recipient, subject, body)


def _send_gmail(sender: str, password: str, recipient: str, subject: str, body: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.attach(MIMEText(body, "plain", "utf-8"))

    logger.info("Sending digest to %s via Gmail SMTP", recipient)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.sendmail(sender, [recipient], msg.as_string())
    logger.info("Email sent")


def _send_sendgrid(sender: str, api_key: str, recipient: str, subject: str, body: str) -> None:
    try:
        import sendgrid  # type: ignore[import-untyped]
        from sendgrid.helpers.mail import Mail  # type: ignore[import-untyped]
    except ImportError as e:
        raise RuntimeError("sendgrid package not installed") from e

    sg = sendgrid.SendGridAPIClient(api_key=api_key)
    message = Mail(
        from_email=sender,
        to_emails=recipient,
        subject=subject,
        plain_text_content=body,
    )
    response = sg.send(message)
    logger.info("Email sent via SendGrid (status %s)", response.status_code)
