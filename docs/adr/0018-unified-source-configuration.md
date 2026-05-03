# ADR-0018: Unified Source Configuration Schema

Date: 2026-05-02
Status: accepted

## Context

`config/sources.yaml` grew two parallel source lists as the pipeline grew:

- `youtube`, `blogs`, `substack`, `hacker_news` — sources for the email digest
- `trends.arxiv`, `trends.huggingface`, `trends.operator_sources`, … — sources for the trend pipeline

This duplicates source definitions (the same operator blogs appear in both sections), forces edits in two places when adding a new source, and reflects the old two-pipeline architecture that ADR-0017 retired. The canonical pipeline (ADR-0017) has a single fetch step that feeds a single `data/processed/` data store — both consumers read from there. The configuration must reflect this.

A secondary problem: the `summary` config section (Gemini model, prompt, token budget) was coupled to the email digest via `src/config.py`'s `SummaryConfig` but was also part of the shared `Config` object. The digest consumer must not depend on source configuration at all — it depends only on Schema Contract B (`ProcessedItem`).

## Decision

### Two independent top-level sections: `sources` and `digest`

`sources` and `digest` have zero coupling. Neither references the other. They are loaded independently by different consumers:

- `src/pipeline/fetch.py` reads `sources` to know what to fetch
- `src/digest/send.py` reads `digest` to know how to format and filter the email

```
config/sources.yaml
├── sources:   (list)          ← fetch pipeline reads this
└── digest:    (mapping)       ← email digest reads this; references only ProcessedItem fields
```

The site build (`src/site/build.py`) reads neither — it operates entirely on `data/processed/` records.

### `sources` — flat list, one entry per source

Every source is a flat list entry with a `type` discriminator. Fetchers with no
per-source granularity (Hacker News, HuggingFace, Replicate, OpenRouter) appear
as a single singleton entry whose type-specific options live inline.

```yaml
sources:
  # RSS / Atom feeds
  - type: rss
    name: "Anthropic Blog"
    url: "https://www.anthropic.com/rss.xml"
    source_class: operator
    enabled: true

  - type: rss
    name: "Ethan Mollick"
    url: "https://www.oneusefulthing.org/feed"
    source_class: practitioner
    enabled: true

  # YouTube channels
  - type: youtube
    name: "Nate Jones"
    channel_id: "UC0C-17n9iuUQPylguM1d-lQ"
    source_class: practitioner
    enabled: true
    max_videos: 5

  # Substack newsletters
  - type: substack
    name: "Nate's Newsletter"
    slug: "natesnewsletter"
    source_class: media
    enabled: true

  # Singleton fetchers — one entry, options inline
  - type: hackernews
    name: "Hacker News"
    source_class: practitioner
    enabled: true
    min_score: 100
    keywords: [llm, agents, reasoning, inference, "foundation model"]
    max_stories: 10

  - type: arxiv
    name: "arXiv"
    source_class: primary
    enabled: true
    categories: [cs.AI, cs.LG, cs.CL, cs.CV, cs.RO]
    max_papers: 30

  - type: huggingface
    name: "HuggingFace Models"
    source_class: primary
    enabled: false
    max_models: 50
    min_downloads: 100

  - type: openrouter
    name: "OpenRouter Pricing"
    source_class: market
    enabled: false
    limit: 100
```

All valid `type` values: `rss` | `youtube` | `substack` | `hackernews` | `arxiv` |
`huggingface` | `paperswithcode` | `operator_changelog` | `replicate` | `openreview` | `openrouter`.

`source_class` is a property of the source entry, not derived from type. It is
carried onto every `FetchedItem` and `ProcessedItem` produced by that source.

### `digest` — independent, references only `ProcessedItem` fields

The digest section has no knowledge of which sources are configured or enabled.
Its filter predicates reference only fields present on `ProcessedItem`
(Schema Contract B). The email consumer reads this section and applies the
predicates to already-processed records — it never looks at the `sources` list.

```yaml
digest:
  subject: "Daily AI Digest — {date}"
  send_if_empty: false

  # Filters applied to ProcessedItem records before selecting items for the digest.
  # These reference only ProcessedItem field names — not source names or source types.
  min_credibility: 0.3      # exclude items with credibility_score below this
  max_hype_risk: 0.8        # exclude items with hype_risk above this
  exclude_marketing: true   # exclude items where is_marketing is true

  # Gemini digest generation
  model: "gemini-2.5-flash"
  max_tokens: 2000
  max_items_per_source: 5
  prompt: |
    Analyse the following AI developments...
```

The `source_class` field on `ProcessedItem` is data, not configuration — the
digest may use it as a filter value (e.g. `exclude_classes: [market]`) if
needed, but this is a predicate on the data schema, not a reference to the
sources configuration.

### `history` and `logging` remain as shared global sections

```yaml
history:
  enabled: true
  history_days: 7
  history_dir: history

logging:
  level: INFO
  log_file: null
```

These are not consumer-specific and are used by the pipeline runner and digest
consumer independently.

## Configuration loader changes (`src/config.py`)

The existing per-section dataclasses (`YouTubeConfig`, `BlogsConfig`,
`HackerNewsConfig`, `TrendsConfig`, `SummaryConfig`, …) are replaced by:

```python
@dataclass
class SourceEntry:
    type: str          # discriminator
    name: str
    source_class: str  # "primary" | "operator" | "practitioner" | "media" | "market"
    enabled: bool = True
    # Type-specific options carried as a dict; accessed by fetcher factory
    options: dict[str, Any] = field(default_factory=dict)

@dataclass
class DigestConfig:
    subject: str = "Daily AI Digest — {date}"
    send_if_empty: bool = False
    min_credibility: float = 0.0
    max_hype_risk: float = 1.0
    exclude_marketing: bool = False
    model: str = "gemini-2.5-flash"
    max_tokens: int = 2000
    max_items_per_source: int = 5
    prompt: str = ""

@dataclass
class Config:
    sources: list[SourceEntry] = field(default_factory=list)
    digest: DigestConfig = field(default_factory=DigestConfig)
    history: HistoryConfig = field(default_factory=HistoryConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
```

`src/pipeline/fetch.py` instantiates the correct fetcher class from
`entry.type`, passing `entry` as its configuration. The fetcher factory
(`_build_fetchers`) iterates `cfg.sources` and filters on `entry.enabled`.

`src/digest/send.py` reads only `cfg.digest`; never accesses `cfg.sources`.

## Consequences

### Positive

- **Single source of truth**: every source is defined once. Adding a new source
  is one list entry.
- **Clean boundary**: digest config depends only on `ProcessedItem` field names,
  not on source topology. Renaming or removing a source does not touch digest config.
- **Simpler fetch loop**: `fetch_all()` iterates one list; no conditional
  `if cfg.youtube.enabled / if cfg.blogs.enabled` blocks.
- **Open/Closed**: adding a new fetcher type requires only a new case in the
  fetcher factory and a new type value — nothing else changes.

### Negative / Trade-offs

- **Breaking change**: `config/sources.yaml` must be fully rewritten. No
  backward compatibility shim is provided.
- **`src/config.py` rewrite**: all existing per-section dataclasses are removed.
  Any code that reads `cfg.youtube`, `cfg.blogs`, `cfg.hacker_news`, or
  `cfg.trends` must be updated.
- **Type-specific validation moves to fetcher layer**: the config loader
  validates only the common fields; type-specific options are validated by each
  fetcher when instantiated.

## Migration

1. Write ADR-0018 (this document) — done
2. Rewrite `config/sources.yaml` with the new schema
3. Rewrite `src/config.py` — new `SourceEntry` + `DigestConfig`; delete old section classes
4. Update `src/pipeline/fetch.py` — `_build_fetchers()` iterates `cfg.sources`
5. Update `src/digest/send.py` — reads `cfg.digest` only; remove any `cfg.summary` references
6. Delete `src/main.py` (old entrypoint that mixed concerns and read old config)
7. Update `tests/test_config.py` — test new loader and `DigestConfig` independence
8. Update `.github/copilot-instructions.md` — replace config section examples

## Related

- ADR-0007: YAML for source configuration (original decision)
- ADR-0017: Canonical pipeline architecture (motivated this change)
- W-0025: Implementation backlog item
