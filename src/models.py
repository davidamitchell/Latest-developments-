"""Shared data models.

Two schema contracts define the pipeline boundaries:

  Schema Contract A — FetchedItem (src/fetchers/__init__.py)
    Output of every fetcher; input to the processing pipeline.
    Represents raw, deduplicated content from a single source item.

  Schema Contract B — ProcessedItem (this module)
    Output of the full processing pipeline; input to both consumers.
    Carries FetchedItem fields plus all pipeline-stage enrichments.
    Both the email digest and the site build read only ProcessedItem.
    Neither consumer may call a fetcher or a pipeline stage directly.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

_log = logging.getLogger(__name__)

SourceClass = Literal["primary", "operator", "practitioner", "media", "market"]

TrendState = Literal["emerging", "scaling", "mature", "declining", "unknown"]

EvidenceType = Literal["experiment", "benchmark", "anecdote", "announcement", "analysis", "unknown"]

Domain = Literal[
    "multimodal",
    "agents",
    "infra",
    "reasoning",
    "safety",
    "evals",
    "data",
    "hardware",
    "general",
    "unknown",
]

ImpactVector = Literal["cost", "latency", "capability", "safety", "adoption", "unknown"]


@dataclass
class ProcessedItem:
    """Schema Contract B: output of the processing pipeline.

    Consumed by the email digest and site build. Neither consumer may access
    fetchers or pipeline internals — they depend only on this type.

    Populated in stages by the pipeline (src/pipeline/). Fields that are not
    yet computed by a stage keep their default values; pipeline stages must not
    leave required fields as defaults without explicit reason.
    """

    # ── Carried from FetchedItem (source metadata — immutable after fetch) ──
    id: str
    title: str
    url: str
    source_name: str
    source_type: str
    source_class: SourceClass
    author: str
    published: datetime | None
    has_code: bool
    evidence_type: EvidenceType

    # ── Stage 1: Ingest / Validate ──
    fetch_date: str = ""        # ISO date of fetch run, e.g. "2026-05-02"

    # ── Stage 2: Clean ──
    cleaned_content: str = ""  # Normalised text, HTML stripped, whitespace collapsed

    # ── Stage 3: Concept Extraction ──
    concepts: list[str] = field(default_factory=list)   # Key entities and techniques
    actors: list[str] = field(default_factory=list)     # Organisations and people named
    impact_vector: ImpactVector = "unknown"             # Primary impact area

    # ── Stage 4: Theme Classification ──
    theme: str = ""             # 1–3 word label, e.g. "agentic RAG"
    domain: Domain = "unknown"  # Canonical domain from taxonomy

    # ── Stage 5: Summary Extraction ──
    summary: str = ""           # 2–3 sentence item summary

    # ── Stage 6: Media / Marketing Identification ──
    is_marketing: bool = False
    marketing_confidence: float = 0.0   # 0–1; 1 = near-certain marketing

    # ── Stage 7: Hype Scoring ──
    hype_risk: float = 0.0      # 0–1; derived from marketing flag + source incentive

    # ── Stage 8: Credibility Scoring ──
    credibility_score: float = 0.5  # 0–1; 5-axis composite

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-serialisable dict for processed data persistence."""
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "source_name": self.source_name,
            "source_type": self.source_type,
            "source_class": self.source_class,
            "author": self.author,
            "published": self.published.isoformat() if self.published else None,
            "has_code": self.has_code,
            "evidence_type": self.evidence_type,
            "fetch_date": self.fetch_date,
            "cleaned_content": self.cleaned_content,
            "concepts": self.concepts,
            "actors": self.actors,
            "impact_vector": self.impact_vector,
            "theme": self.theme,
            "domain": self.domain,
            "summary": self.summary,
            "is_marketing": self.is_marketing,
            "marketing_confidence": self.marketing_confidence,
            "hype_risk": self.hype_risk,
            "credibility_score": self.credibility_score,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ProcessedItem:
        """Deserialise from a dict produced by to_dict()."""
        published = None
        if d.get("published"):
            try:
                published = datetime.fromisoformat(d["published"])
            except ValueError:
                pass
        return cls(
            id=d["id"],
            title=d["title"],
            url=d["url"],
            source_name=d["source_name"],
            source_type=d.get("source_type", ""),
            source_class=d.get("source_class", "practitioner"),
            author=d.get("author", ""),
            published=published,
            has_code=d.get("has_code", False),
            evidence_type=d.get("evidence_type", "unknown"),
            fetch_date=d.get("fetch_date", ""),
            cleaned_content=d.get("cleaned_content", ""),
            concepts=d.get("concepts", []),
            actors=d.get("actors", []),
            impact_vector=d.get("impact_vector", "unknown"),
            theme=d.get("theme", ""),
            domain=d.get("domain", "unknown"),
            summary=d.get("summary", ""),
            is_marketing=d.get("is_marketing", False),
            marketing_confidence=d.get("marketing_confidence", 0.0),
            hype_risk=d.get("hype_risk", 0.0),
            credibility_score=d.get("credibility_score", 0.5),
        )


@dataclass
class CanonicalRecord:
    """Structured representation of a single fetched item's core claim."""

    url: str
    title: str
    source_class: SourceClass = "practitioner"
    claim: str = ""
    evidence_type: EvidenceType = "unknown"
    has_code: bool = False
    domain: Domain = "unknown"
    technique: str = ""
    impact_vector: ImpactVector = "unknown"
    actors: list[str] = field(default_factory=list)
    credibility_score: float = 0.5
    hype_risk: float = 0.0
    date: str = ""  # ISO date string YYYY-MM-DD


@dataclass
class TrendMetrics:
    """Per-theme metrics used to classify trend state."""

    theme: str
    domain: str = "unknown"
    definition: str = ""
    state: TrendState = "unknown"
    confidence: float = 0.5
    volume: float = 0.0  # credibility-weighted item count
    velocity: float = 0.0  # week-over-week volume delta
    diversity: int = 0  # number of distinct source classes
    adoption_proxy: float = 0.0  # 0–1: jobs, repo activity, pricing mentions
    stability: float = 1.0  # inverse of rolling variance
    hype_risk: float = 0.0  # 0–1
    item_count: int = 0
    last_seen: str = ""  # ISO date of most recent item
    source_classes: list[str] = field(default_factory=list)
    source_class_counts: dict[str, int] = field(default_factory=dict)
    history: list[dict] = field(default_factory=list)  # [{date, volume, state}, …]


@dataclass
class ThemeNode:
    """A theme cluster in the relationship graph."""

    name: str
    domain: str = "unknown"
    definition: str = ""
    state: TrendState = "unknown"
    item_count: int = 0
    last_seen: str = ""
    source_classes: list[str] = field(default_factory=list)
    source_class_counts: dict[str, int] = field(default_factory=dict)
    hype_risk: float = 0.0


@dataclass
class GraphEdge:
    """A directed relationship between two theme nodes."""

    source: str
    target: str
    # Relationship type from the plan spec
    rel_type: Literal["causal", "competitive", "compositional", "contradictory"] = "causal"
    weight: float = 1.0  # number of independent supporting paths
    source_diversity: int = 1  # distinct source classes supporting this edge


# ── ProcessedItem JSONL I/O ──────────────────────────────────────────────────
# Kept here (with the model) so consumers can read ProcessedItem records
# without importing src.pipeline.run and its transitive stage dependencies.

def write_processed_jsonl(items: list[ProcessedItem], path: Path) -> None:
    """Write ProcessedItem list to path as JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")
    _log.info("Wrote %d processed item(s) to %s", len(items), path)


def read_processed_jsonl(path: Path) -> list[ProcessedItem]:
    """Read ProcessedItem JSONL file; return [] if file is missing."""
    if not path.exists():
        _log.debug("Processed file not found: %s", path)
        return []
    items: list[ProcessedItem] = []
    with path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                items.append(ProcessedItem.from_dict(json.loads(line)))
            except Exception as exc:
                _log.warning("Skipping malformed line %d in %s: %s", lineno, path, exc)
    return items
