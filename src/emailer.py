"""Email delivery via Gmail SMTP, SendGrid, or Resend."""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

logger = logging.getLogger(__name__)


def _require(key: str) -> str:
    value = os.environ.get(key, "").strip()
    if not value:
        raise RuntimeError(f"Environment variable {key!r} is not set")
    return value


def send_digest(subject: str, body: str, html_body: str | None = None) -> None:
    """
    Send the digest email.

    Reads EMAIL_PROVIDER, EMAIL_SENDER, EMAIL_RECIPIENT, and credentials
    from environment variables (set as GitHub Secrets in CI).

    When *html_body* is provided the email is sent as multipart/alternative
    with both a plain-text part and an HTML part, so clients that support
    HTML show the richer layout while others fall back to plain text.

    Providers:
      gmail    — EMAIL_PASSWORD = Gmail App Password (requires 2FA + App Password)
      sendgrid — EMAIL_PASSWORD = SendGrid API key
      resend   — RESEND_API_KEY = Resend API key (free tier: 3 000 emails/month,
                 EMAIL_SENDER must use a verified domain or onboarding@resend.dev
                 for initial testing)
    """
    provider = os.environ.get("EMAIL_PROVIDER", "gmail").lower()
    sender = _require("EMAIL_SENDER")
    recipient = _require("EMAIL_RECIPIENT")

    if provider == "resend":
        api_key = _require("RESEND_API_KEY")
        _send_resend(sender, api_key, recipient, subject, body, html_body)
    elif provider == "sendgrid":
        password = _require("EMAIL_PASSWORD")
        _send_sendgrid(sender, password, recipient, subject, body, html_body)
    else:
        password = _require("EMAIL_PASSWORD")
        _send_gmail(sender, password, recipient, subject, body, html_body)


def _send_gmail(
    sender: str,
    password: str,
    recipient: str,
    subject: str,
    body: str,
    html_body: str | None = None,
) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.attach(MIMEText(body, "plain", "utf-8"))
    if html_body:
        msg.attach(MIMEText(html_body, "html", "utf-8"))

    logger.info("Sending digest to %s via Gmail SMTP", recipient)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.sendmail(sender, [recipient], msg.as_string())
    logger.info("Email sent")


def _send_sendgrid(
    sender: str,
    api_key: str,
    recipient: str,
    subject: str,
    body: str,
    html_body: str | None = None,
) -> None:
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
        html_content=html_body,
    )
    response = sg.send(message)
    logger.info("Email sent via SendGrid (status %s)", response.status_code)


def _send_resend(
    sender: str,
    api_key: str,
    recipient: str,
    subject: str,
    body: str,
    html_body: str | None = None,
) -> None:
    logger.info("Sending digest to %s via Resend", recipient)
    payload: dict = {"from": sender, "to": [recipient], "subject": subject, "text": body}
    if html_body:
        payload["html"] = html_body
    response = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=15,
    )
    response.raise_for_status()
    logger.info("Email sent via Resend (status %s)", response.status_code)
