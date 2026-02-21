# ADR-0006: Email Delivery via SMTP with SendGrid Option

Date: 2026-02-21
Status: Accepted

## Context

The pipeline must send a daily digest email. Requirements:
- Works from GitHub Actions (no interactive auth)
- Supports HTML and plain-text content
- Reliable enough for personal use (not bulk marketing)
- Minimal setup cost

Options considered:
1. **Gmail SMTP with App Password** — use Python `smtplib` with Gmail's SMTP server
2. **SendGrid API** — transactional email service with a free tier
3. **Amazon SES** — requires AWS account; overkill for one email/day
4. **Mailgun** — similar to SendGrid
5. **GitHub Actions email action** — limited and not configurable enough

## Decision

Implement email delivery in `src/emailer.py` with **Gmail SMTP as the default**, and **SendGrid as a configurable alternative**.

The provider is selected by the `EMAIL_PROVIDER` environment variable (`gmail` or `sendgrid`). Both paths share the same interface, so adding providers later is straightforward.

### Gmail configuration
- Uses `smtplib.SMTP_SSL` on port 465
- Requires `EMAIL_SENDER` (Gmail address) and `EMAIL_PASSWORD` (App Password, not account password)
- Google account must have 2FA enabled to generate an App Password

### SendGrid configuration
- Uses the `sendgrid` Python SDK
- Requires `SENDGRID_API_KEY`

## Consequences

### Positive
- Gmail SMTP requires no paid account — a personal Gmail with an App Password is sufficient
- `smtplib` is in the Python standard library; no extra dependency for the Gmail path
- SendGrid's free tier (100 emails/day) is more than enough; useful if the user doesn't want to use their Gmail SMTP

### Negative / Trade-offs
- Gmail App Passwords are less secure than OAuth2; App Password should be treated as a secret
- Gmail may rate-limit or block SMTP from unusual IPs (GitHub Actions' IPs are well-known; occasionally flagged)
- SendGrid adds a dependency and API key to manage

### Neutral
- The email is sent as both HTML and plain-text (multipart) for maximum compatibility
- A future slice will add HTML formatting to the digest body (Epic 6.3)
