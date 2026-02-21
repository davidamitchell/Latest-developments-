# Latest Developments

Watches YouTube channels, blogs, and Hacker News for new AI/ML content, summarises it with Claude, and sends one email per day.

Runs on GitHub Actions. The workflow, config, and deduplication state all live in this repository — no external infrastructure required.

---

## What costs money

| Component | Cost |
|---|---|
| GitHub Actions | Free (public repo or within free-tier minutes) |
| YouTube RSS + transcripts | Free (no API key) |
| Hacker News API | Free |
| Resend email | Free up to 3 000 emails/month |
| **Claude summarisation** | **Paid** — ~$0.01–0.05 per run with Haiku |

Claude is optional. Set `summary.enabled: false` in `config/sources.yaml` and the pipeline sends a plain link list instead. Useful for testing delivery before signing up for an Anthropic account.

---

## Setup

### 1. Configure sources

Edit `config/sources.yaml` to choose which YouTube channels, RSS feeds, and HN filters to watch. Everything is commented.

### 2. Choose an email provider

**Resend** is the easiest starting point — free tier, no App Password or domain required for initial testing.

1. Sign up at [resend.com](https://resend.com) and create an API key.
2. For testing you can send from `onboarding@resend.dev` to your own address.
3. Set `EMAIL_PROVIDER=resend` and `RESEND_API_KEY=re_...` in your secrets.

Gmail also works but requires [App Password setup](https://support.google.com/accounts/answer/185833) (2FA must be enabled first).

### 3. Add GitHub Secrets

Settings → Secrets and variables → Actions. Minimum set for a Resend + link-digest run:

| Secret | Value |
|---|---|
| `EMAIL_PROVIDER` | `resend` |
| `RESEND_API_KEY` | Resend API key |
| `EMAIL_SENDER` | `onboarding@resend.dev` (testing) or your verified address |
| `EMAIL_RECIPIENT` | Where to send the digest |

Add `ANTHROPIC_API_KEY` when you want AI summaries instead of a link list.

### 4. Enable the workflow

GitHub Actions → `Daily Digest` → Enable. Runs at 07:00 UTC by default; adjust the cron in `.github/workflows/daily-digest.yml`.

---

## Local development

```bash
make dev-install   # install with dev dependencies
cp .env.example .env && $EDITOR .env
make dry-run       # run pipeline, print digest to stdout (no email sent)
make test          # run test suite
make lint          # ruff check
```

---

## Deduplication

After each run, processed item IDs are written to `state/processed.json` and committed back to the repo by the workflow. The next run loads this file and skips anything already seen.

To reset: delete `state/processed.json`.

---

## Customising the summary

`summary.prompt` in `config/sources.yaml` is passed verbatim as the Claude system prompt. The default targets model releases, research papers, and developer tooling.

---

## Project layout

```
config/sources.yaml         source list and summary settings
state/processed.json        deduplication store (committed by CI)
src/                        pipeline code
docs/adr/                   architecture decisions
.github/workflows/          scheduled job
```

Conventions and agent instructions: `AGENTS.md`
Planned work: `BACKLOG.md`
Design decisions: `docs/adr/README.md`
