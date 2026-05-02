# ADR-0017: Canonical Pipeline Architecture

Date: 2026-05-02
Status: accepted

## Context

The pipeline evolved organically from a simple fetch → summarise → email system into one with trend analysis, credibility scoring, theme clustering, and a GitHub Pages site. As capability grew, three distinct concerns became tangled in a single `daily-digest.yml` workflow:

1. **Email digest** — fetch, summarise, email, archive to `history/`
2. **Trend analysis** — read history, compute themes and trend state, write `docs/data/`
3. **Site build** — publish `docs/` to GitHub Pages

The daily-digest workflow ran all three sequentially and committed state, history, and site data in a single bot commit. This created several problems:

- A trend-analysis failure blocked the email send (and vice versa), coupling independent concerns.
- `docs/data/*.json` was committed as part of the digest run, making it look like persisted application state when it is a build artefact derived from `history/`.
- The site "rebuilt itself" as a side effect of every digest run, with no clear trigger or ownership.
- The architecture was not legible: a reader of the workflow could not tell which steps were essential to the email and which were for the site.

Additionally, source configuration in `sources.yaml` had grown into two parallel sections — email sources (`youtube`, `blogs`, `hacker_news`, `substack`) and trend sources (`trends.*`) — with some sources duplicated in both, making it unclear which sources fed which pipeline.

## Decision

### 1. Separate into three independent workflows

| Workflow | Trigger | Commits | Responsibility |
|---|---|---|---|
| `daily-digest.yml` | Schedule + `workflow_dispatch` | `state/processed.json`, `history/` | Email pipeline only |
| `rebuild-site.yml` | `workflow_run` (after digest success on `main`) + `workflow_dispatch` | `docs/data/` | Site build only |
| `ci.yml` | Every push + PR | — | Lint and test |

`daily-digest.yml` does not run trend analysis and does not touch `docs/data/`.

`rebuild-site.yml` is the only workflow that writes `docs/data/`. It triggers automatically after `daily-digest` succeeds on `main`, or can be manually dispatched.

### 2. Establish the fetcher boundary as the core design principle

All source types (YouTube, RSS, Substack, HN, arXiv, HuggingFace, etc.) are normalised to a `FetchedItem` at the fetcher. Post-processing is source-type-agnostic. The fetcher's only job is that normalisation. This boundary must be preserved: adding a new source type means adding a fetcher, not changing downstream processing.

`FetchedItem` fields carry all metadata needed for post-processing: `source_class`, `source_type`, `source_name`, `author`, `published`, `has_code`, `evidence_type`. Downstream stages must not infer these from content.

### 3. Declare docs/data/ as a build artefact

`docs/data/*.json` is generated output, not persisted state. Its source of truth is `history/`. It may be committed to git for GH Pages compatibility (which requires files in the repo), but:

- It is only ever written by `rebuild-site.yml`, never by `daily-digest.yml`.
- If the GH Pages deployment mechanism is changed to use Actions artefacts in future, `docs/data/` can be removed from git tracking without losing any data.

### 4. Target processing pipeline stages (to be implemented — see W-0024)

After fetching, items should pass through discrete, composable processing stages before the digest or trend analysis consumes them:

1. **Ingest** — validate `FetchedItem` fields; reject malformed items; assign defaults
2. **Clean** — strip markup, normalise whitespace, truncate to token budget
3. **Enrich** — AI extraction of concepts, themes, and summaries per item
4. **Score** — hype risk and credibility computation

Currently these stages are partially interleaved across `summariser.py`, `credibility.py`, `themes.py`, and `trends.py`. W-0024 will extract them into an explicit pipeline.

## Consequences

### Positive

- Each workflow has one responsibility. A digest failure does not prevent site rebuild.
- `docs/data/` provenance is clear: it is always generated from `history/`, never from runtime state.
- The fetcher boundary is explicit and documented. Post-processing cannot accidentally depend on source type.
- The site rebuild can be triggered independently for debugging, without re-running the email pipeline.

### Negative / Trade-offs

- Two GitHub Actions runs per digest day instead of one. Each run costs Actions minutes.
- Site data may lag the digest by a few minutes while `rebuild-site` completes.
- Source configuration duplication (email sources vs trend sources in `sources.yaml`) is left for W-0025; it is a known imperfection, not a blocker.

### Neutral

- `history/*.txt` remains the canonical source of truth for trend analysis.
- `state/processed.json` remains the canonical deduplication state.
- The email and trend pipelines remain separate entry points (`src/main.py` vs `src/trends.py`). Merging them is explicitly out of scope — their concerns differ.

## Related

- ADR-0014: Digest history archiving and trend analysis
- ADR-0016: GitHub Pages trend intelligence site
- W-0023: Implement workflow separation (this ADR)
- W-0024: Implement discrete pipeline processing stages
- W-0025: Unify source configuration schema
