# Latest Developments

A daily digest pipeline that monitors YouTube channels, blogs, and Hacker News in the LLM/AI space — then emails you a concise, configurable summary every morning.

Runs entirely on **GitHub Codespaces** via a scheduled GitHub Actions workflow. No server required.

---

## What It Does

1. Fetches new content from configured sources (YouTube channels, RSS blogs, Hacker News)
2. Transcribes YouTube videos (using available transcripts; falls back to audio)
3. Summarises content using Anthropic Claude
4. Emails you one digest per day
5. Tracks what it has already processed so nothing is repeated across runs

---

## Quick Start

### Prerequisites

- A GitHub account with Codespaces enabled
- An [Anthropic API key](https://console.anthropic.com/)
- An email account for sending (Gmail App Password or SendGrid API key)

### Setup

1. **Fork or clone this repository**

2. **Add GitHub Secrets** (Settings → Secrets and variables → Actions):

   | Secret | Description |
   |---|---|
   | `ANTHROPIC_API_KEY` | Your Anthropic Claude API key |
   | `EMAIL_SENDER` | Address to send from |
   | `EMAIL_PASSWORD` | Gmail App Password or SendGrid key |
   | `EMAIL_RECIPIENT` | Address to send the digest to |
   | `EMAIL_PROVIDER` | `gmail` or `sendgrid` |

3. **Configure your sources** — edit `config/sources.yaml`:

   ```yaml
   youtube:
     channels:
       - name: "Andrej Karpathy"
         channel_id: "UCbXgNpp0jedKWcQiULLbDTA"
   blogs:
     rss:
       - name: "Simon Willison's Weblog"
         url: "https://simonwillison.net/atom/everything/"
   hacker_news:
     enabled: true
     min_score: 100
     keywords: ["LLM", "AI", "Claude", "GPT"]
   ```

4. **Enable the workflow** — GitHub Actions → `Daily Digest` → Enable

The workflow runs daily at 07:00 UTC by default. You can also trigger it manually.

---

## Configuration

### Sources (`config/sources.yaml`)

- **YouTube channels** — fetches recent videos and their transcripts
- **RSS blogs** — fetches new entries since last run
- **Hacker News** — filters stories by keyword and minimum score

### Summary Prompt (`config/sources.yaml` → `summary.prompt`)

Customise what Claude looks for in the digest. Example:

```yaml
summary:
  prompt: |
    Focus on: new model releases, benchmark results, research papers,
    and practical developer tools. Ignore marketing announcements.
  max_items_per_source: 5
  max_tokens: 2000
```

---

## Running Locally / in Codespaces

```bash
# Install dependencies
pip install -r requirements.txt

# Run in debug mode (verbose logging, no email sent)
python -m src.main --debug --dry-run

# Run normally
python -m src.main
```

---

## Project Structure

```
├── README.md                   # This file
├── AGENTS.md                   # Instructions for AI coding agents
├── BACKLOG.md                  # Prioritised feature backlog
├── PROGRESS.md                 # Current progress and status
├── config/
│   └── sources.yaml            # Sources and prompt configuration
├── docs/
│   └── adr/                    # Architecture Decision Records
├── src/
│   ├── main.py                 # Entry point
│   ├── fetchers/               # Source-specific fetchers
│   ├── summariser.py           # Claude summarisation
│   ├── emailer.py              # Email delivery
│   ├── state.py                # Deduplication state management
│   └── logger.py               # Logging setup
├── tests/
├── .github/
│   └── workflows/
│       └── daily-digest.yml    # Scheduled GitHub Actions workflow
└── requirements.txt
```

---

## Deduplication

The pipeline stores a `state/processed.json` file tracking every item it has summarised (by URL or video ID). Items are never processed twice, even if they remain the most recent entry on a source.

---

## Debug Mode

Run with `--debug` for structured, verbose logging to stdout. Combine with `--dry-run` to skip the email step entirely — useful for testing new sources or prompt changes.

---

## Contributing / Architecture

See `AGENTS.md` for coding conventions and agent instructions.
See `docs/adr/` for Architecture Decision Records explaining key design choices.
See `BACKLOG.md` for planned work.
