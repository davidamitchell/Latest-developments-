# Latest Developments

Watches YouTube channels, blogs, and Hacker News for new AI/ML content, summarises it with Claude, and sends one email per day.

Runs on GitHub Actions. The workflow, config, and deduplication state all live in this repository — no external infrastructure required.

---

## Setup

### 1. Configure sources

Edit `config/sources.yaml` to choose which YouTube channels, RSS feeds, and HN filters to watch.

### 2. Add GitHub Secrets

Settings → Secrets and variables → Actions:

| Secret | Value |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic console API key |
| `EMAIL_SENDER` | Sending address |
| `EMAIL_PASSWORD` | Gmail App Password or SendGrid key |
| `EMAIL_RECIPIENT` | Destination address |
| `EMAIL_PROVIDER` | `gmail` or `sendgrid` |

Gmail requires an [App Password](https://support.google.com/accounts/answer/185833), not your account password. Enable 2FA first.

### 3. Enable the workflow

GitHub Actions → `Daily Digest` → Enable. Runs at 07:00 UTC by default; adjust the cron in `.github/workflows/daily-digest.yml`.

---

## Local development

```bash
make dev-install   # install with dev dependencies
make dry-run       # run pipeline without sending email
make test          # run test suite
make lint          # ruff check
```

Copy `.env.example` to `.env` and fill in credentials before running locally.

---

## Deduplication

After each run, processed item IDs are written to `state/processed.json` and committed back to the repo by the workflow. The next run loads this file and skips anything already seen.

To reset: delete `state/processed.json`.

---

## Customising the summary

`summary.prompt` in `config/sources.yaml` tells Claude what to focus on. The default targets model releases, research papers, and developer tooling. Edit freely — it's passed verbatim as the system prompt.

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
