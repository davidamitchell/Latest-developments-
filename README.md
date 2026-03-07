# Latest Developments

Watches YouTube channels, blogs, and Hacker News for new AI/ML content, summarises it with Gemini, and sends one email per day.

Runs on GitHub Actions. The workflow, config, and deduplication state all live in this repository — no external infrastructure required.

---

## Cost

Everything here has a free tier sufficient for a daily digest.

| Component | Cost |
|---|---|
| GitHub Actions | Free (public repo or within free-tier minutes) |
| YouTube RSS + transcripts | Free — no API key |
| Hacker News API | Free |
| Resend email | Free up to 3 000 emails/month |
| Gemini summarisation | Free — Google AI Studio gives 1 500 req/day |

To skip AI summarisation entirely, set `summary.enabled: false` in `config/sources.yaml`. The pipeline will send a plain link list. Useful for verifying email delivery before setting up a Gemini key.

---

## Setup

### 1. Configure sources

Edit `config/sources.yaml`. It is fully commented. At minimum, choose which YouTube channels and/or RSS feeds to watch.

### 2. Get a Gemini API key (free)

1. Go to [aistudio.google.com](https://aistudio.google.com) and sign in with your Google account.
2. Click **Get API key** → **Create API key**.
3. Copy the key — it starts with `AIza`.

No billing setup required. The free tier (1 500 requests/day, 1M tokens/day) covers daily digest runs comfortably.

### 3. Set up email

**Resend** is the simplest starting point — free tier, no domain or App Password required for initial testing.

1. Sign up at [resend.com](https://resend.com) and create an API key.
2. For testing, send from `onboarding@resend.dev` to your own address. To send from your own domain, add and verify it in the Resend dashboard.

Gmail also works but requires an [App Password](https://support.google.com/accounts/answer/185833) (Google account 2FA must be enabled first).

### 4. Add GitHub Secrets

Settings → Secrets and variables → Actions → New repository secret.

**Minimum set (Resend + AI summary):**

| Secret | Value |
|---|---|
| `GEMINI_API_KEY` | Your Google AI Studio key |
| `EMAIL_PROVIDER` | `resend` |
| `RESEND_API_KEY` | Your Resend API key |
| `EMAIL_SENDER` | `onboarding@resend.dev` (testing) or your verified address |
| `EMAIL_RECIPIENT` | Where to send the digest |

**To skip AI summary (email-only smoke test):**

Omit `GEMINI_API_KEY` and set `summary.enabled: false` in `sources.yaml`. The pipeline will send a link list without calling Gemini.

**Gmail instead of Resend:**

| Secret | Value |
|---|---|
| `EMAIL_PROVIDER` | `gmail` |
| `EMAIL_SENDER` | `you@gmail.com` |
| `EMAIL_PASSWORD` | Your Gmail App Password |
| `EMAIL_RECIPIENT` | Destination address |

### 5. Enable the workflow

GitHub Actions tab → `Daily Digest` → Enable workflow.

Runs at 07:00 UTC by default. To change the time, edit the cron in `.github/workflows/daily-digest.yml` and update `schedule.time_utc` in `sources.yaml` to match (the YAML field is informational only).

---

## Local development

```bash
make dev-install        # install with dev dependencies
cp .env.example .env
$EDITOR .env            # fill in GEMINI_API_KEY and email credentials
make dry-run            # run pipeline, print digest to stdout — no email sent
make test               # run test suite
make lint               # ruff check
```

`make dry-run` fetches real content and calls the real Gemini API if `GEMINI_API_KEY` is set. To run fully offline (just email smoke test), set `summary.enabled: false` in `sources.yaml` first.

---

## Deduplication

After each successful run, processed item IDs are written to `state/processed.json` and committed back to the repo by the workflow. The next run skips anything already in that file.

To reset: delete `state/processed.json` and commit the deletion.

---

## Customising the summary

`summary.prompt` in `config/sources.yaml` is passed verbatim as the Gemini system instruction. The default targets model releases, research papers, and developer tooling. Swap in any focus area you like.

---

## Project layout

```
config/sources.yaml         source list and summary settings
state/processed.json        deduplication store (committed by CI)
src/                        pipeline code
docs/adr/                   architecture decisions
.github/workflows/          scheduled job
.github/copilot-instructions.md  agent instructions
BACKLOG.md                  planned and completed work items
PROGRESS.md                 append-only session history
CHANGELOG.md                user-facing change log
```

AI agents should read `.github/copilot-instructions.md` for full project conventions, coding standards, and working methodology.
