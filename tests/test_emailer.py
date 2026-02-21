"""Tests for src/emailer.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.emailer import send_digest


def _env(provider: str = "gmail") -> dict[str, str]:
    return {
        "EMAIL_PROVIDER": provider,
        "EMAIL_SENDER": "sender@example.com",
        "EMAIL_PASSWORD": "password123",
        "EMAIL_RECIPIENT": "recipient@example.com",
    }


class TestSendDigest:
    def test_raises_when_sender_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("EMAIL_SENDER", raising=False)
        with pytest.raises(RuntimeError, match="EMAIL_SENDER"):
            send_digest("Subject", "Body")

    def test_raises_when_recipient_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EMAIL_SENDER", "s@x.com")
        monkeypatch.setenv("EMAIL_PASSWORD", "pw")
        monkeypatch.delenv("EMAIL_RECIPIENT", raising=False)
        with pytest.raises(RuntimeError, match="EMAIL_RECIPIENT"):
            send_digest("Subject", "Body")

    def test_gmail_smtp_called(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for k, v in _env("gmail").items():
            monkeypatch.setenv(k, v)

        mock_server = MagicMock()
        mock_server.__enter__ = lambda s: s
        mock_server.__exit__ = MagicMock(return_value=False)

        with patch("src.emailer.smtplib.SMTP_SSL", return_value=mock_server):
            send_digest("Test Subject", "Test body")

        mock_server.login.assert_called_once_with("sender@example.com", "password123")
        mock_server.sendmail.assert_called_once()
        args = mock_server.sendmail.call_args.args
        assert args[0] == "sender@example.com"
        assert "recipient@example.com" in args[1]

    def test_sendgrid_called(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for k, v in _env("sendgrid").items():
            monkeypatch.setenv(k, v)

        mock_sg = MagicMock()
        mock_sg.send.return_value.status_code = 202

        mock_mail_cls = MagicMock()

        with (
            patch.dict(
                "sys.modules",
                {
                    "sendgrid": MagicMock(SendGridAPIClient=MagicMock(return_value=mock_sg)),
                    "sendgrid.helpers.mail": MagicMock(Mail=mock_mail_cls),
                },
            ),
        ):
            send_digest("Subject", "Body")

        mock_sg.send.assert_called_once()

    def test_email_subject_in_message(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for k, v in _env("gmail").items():
            monkeypatch.setenv(k, v)

        mock_server = MagicMock()
        mock_server.__enter__ = lambda s: s
        mock_server.__exit__ = MagicMock(return_value=False)

        with patch("src.emailer.smtplib.SMTP_SSL", return_value=mock_server):
            send_digest("My Digest Subject", "Body content")

        raw_message = mock_server.sendmail.call_args.args[2]
        assert "My Digest Subject" in raw_message

    def test_resend_called(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EMAIL_PROVIDER", "resend")
        monkeypatch.setenv("EMAIL_SENDER", "sender@example.com")
        monkeypatch.setenv("EMAIL_RECIPIENT", "recipient@example.com")
        monkeypatch.setenv("RESEND_API_KEY", "re_test_key")

        with patch("src.emailer.httpx.post") as mock_post:
            mock_post.return_value.status_code = 200
            send_digest("Subject", "Body")

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert "resend.com" in call_kwargs.args[0]
        payload = call_kwargs.kwargs["json"]
        assert payload["to"] == ["recipient@example.com"]
        assert payload["subject"] == "Subject"

    def test_resend_raises_when_api_key_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EMAIL_PROVIDER", "resend")
        monkeypatch.setenv("EMAIL_SENDER", "s@x.com")
        monkeypatch.setenv("EMAIL_RECIPIENT", "r@x.com")
        monkeypatch.delenv("RESEND_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="RESEND_API_KEY"):
            send_digest("Subject", "Body")
