# ADR-0017: Canonical Pipeline Architecture

Date: 2026-05-02
Status: accepted

## Context

The pipeline grew organically from a simple fetch → summarise → email system to one with trend analysis, credibility scoring, theme clustering, and a GitHub Pages site. Three architectural problems emerged:

**1. Mixed concerns.** `src/main.py` (email digest) did its own fetching, deduplication, and Gemini summarisation. `src/trends.py` (site data) did its own independent fetching and processing. Both pipelines called Gemini separately. Both maintained their own source lists. Sources like operator blogs appeared in both, duplicating configuration and diverging over time.

**2. Sequential consumers.** The site rebuild was triggered after the email digest, creating a false dependency. Neither consumer depends on the other — they are parallel views over the same data.

**3. No defined schema contracts.** There was no explicit boundary between "fetching content" and "processing content", and no explicit boundary between "processing content" and "using it". Code crossed these boundaries freely, making components hard to test, replace, or extend independently.

## Decision

### SOLID architecture with two schema contracts

Apply Single Responsibility, Open/Closed, Interface Segregation, and Dependency Inversion pragmatically. Three distinct concerns, two explicit schema contracts between them.

```
CONCERN 1: FETCHING
  Configured sources → Fetchers (per source type) → FetchedItem[]
  Deduplication happens here (before any processing)
  Commit: data/raw/YYYY-MM-DD.jsonl
  [Schema Contract A — FetchedItem]

CONCERN 2: PROCESSING PIPELINE
  FetchedItem[] → Pipeline stages → ProcessedItem[]
  Commit: data/processed/YYYY-MM-DD.jsonl
  [Schema Contract B — ProcessedItem]

CONCERN 3A: EMAIL DIGEST (outport adapter)
  ProcessedItem[] → select by config → format → send email
  Write: history/YYYY-MM-DD.txt
  Commit: state/processed.json + history/

CONCERN 3B: SITE BUILD (outport adapter)
  ProcessedItem[] → aggregate trends → write docs/data/ → deploy GH Pages
```

Concerns 3A and 3B are **parallel consumers** triggered by the same event (processed data committed). They have zero dependency on each other.

### Schema Contract A — FetchedItem (`src/fetchers/__init__.py`)

Output of every fetcher; input to the processing pipeline. Mandatory fields:

- `id` — stable dedup key
- `title`, `url`, `content` — source content
- `source_name`, `source_type`, `source_class` — provenance
- `author` — author name where available
- `published` — publication datetime
- `has_code`, `evidence_type` — credibility signals

All fetchers must populate every field. Downstream stages must not infer missing metadata from content.

### Schema Contract B — ProcessedItem (`src/models.py`)

Output of the full processing pipeline; input to both consumers. Carries all FetchedItem fields plus pipeline enrichments:

| Stage | Fields added |
|---|---|
| 1. Ingest / Validate | `fetch_date` |
| 2. Clean | `cleaned_content` |
| 3. Concept Extraction | `concepts`, `actors`, `impact_vector` |
| 4. Theme Classification | `theme`, `domain` |
| 5. Summary Extraction | `summary` |
| 6. Media / Marketing ID | `is_marketing`, `marketing_confidence` |
| 7. Hype Scoring | `hype_risk` |
| 8. Credibility Scoring | `credibility_score` |

Neither consumer (email digest, site build) may call a fetcher or a pipeline stage directly. Both read only `ProcessedItem` records from `data/processed/`.

### Workflow structure

Four workflows, each with one responsibility:

| Workflow | Trigger | Commits | Responsibility |
|---|---|---|---|
| `fetch-and-process.yml` | Schedule + `workflow_dispatch` | `data/raw/`, `data/processed/` | Fetch all sources; run pipeline |
| `email-digest.yml` | `workflow_run` (fetch-and-process success) + `workflow_dispatch` | `state/processed.json`, `history/` | Send digest; archive |
| `rebuild-site.yml` | `workflow_run` (fetch-and-process success) + `workflow_dispatch` | `docs/data/` | Build site |
| `ci.yml` | Every push + PR | — | Lint and test |

`email-digest` and `rebuild-site` both listen to `workflow_run: [Fetch and Process]`. They trigger in parallel and complete independently.

### Raw data persistence

`data/raw/YYYY-MM-DD.jsonl` is committed after fetching. This enables:
- Re-processing without re-fetching (useful when a pipeline stage changes)
- Auditing what was fetched on any given day
- Decoupling the fetch step from the processing step (separate jobs in the workflow)

### Configuration

Sources are defined once in `config/sources.yaml`. Each source will be tagged for which consumers it feeds (`digest`, `trends`, or both) once W-0025 is implemented. Until then, the existing separate sections are a known imperfection.

## Consequences

### Positive

- **Single Responsibility**: each workflow has one job; each Python module has one concern.
- **No consumer coupling**: email and site build trigger in parallel from the same event. Changing or disabling one does not affect the other.
- **Explicit contracts**: `FetchedItem` and `ProcessedItem` are the only coupling points. Any consumer can be replaced by reading those schemas.
- **Re-processing**: committed raw data enables re-running the pipeline on historical fetches without API calls.
- **Testability**: each pipeline stage has a defined input/output type and can be tested in isolation.

### Negative / Trade-offs

- Three workflow runs per day instead of one. Each costs Actions minutes.
- The `daily-digest.yml` and current `rebuild-site.yml` (which triggered after daily-digest) are superseded and should be removed once W-0026/W-0027/W-0028 are implemented.
- `src/main.py` and `src/trends.py` continue to run the old architecture until the migration work is complete.

### Neutral

- `history/*.txt` continues to be written by the email digest for human-readable archiving. It is not consumed by the site build — the site reads `data/processed/` directly.
- `state/processed.json` dedup logic is unchanged. The fetch step reads it; the email digest updates it after send.

## Migration path

| Item | What |
|---|---|
| W-0024 | Implement `FetchedItem.to_dict/from_dict`; `ProcessedItem`; `data/` structure |
| W-0025 | Unify source configuration schema |
| W-0026 | Implement `src/pipeline/fetch.py` and `src/pipeline/run.py`; activate `fetch-and-process.yml` |
| W-0027 | Implement `src/digest/send.py`; activate `email-digest.yml`; retire `daily-digest.yml` |
| W-0028 | Implement `src/site/build.py`; activate `rebuild-site.yml`; retire `src/trends.py` entrypoint |

## Related

- ADR-0014: Digest history archiving and trend analysis
- ADR-0016: GitHub Pages trend intelligence site
- W-0024 through W-0028: migration backlog
