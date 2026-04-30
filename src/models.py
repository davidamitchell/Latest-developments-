"""Shared data models for the trend analysis pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

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
class CanonicalRecord:
    """Structured representation of a single fetched item's core claim."""

    url: str
    title: str
    source_class: SourceClass = "practitioner"
    claim: str = ""
    evidence_type: EvidenceType = "unknown"
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
