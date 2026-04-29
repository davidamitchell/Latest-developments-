"""Credibility scoring and hype detection for canonical records."""

from __future__ import annotations

import math
from datetime import date, datetime, timezone

from src.models import CanonicalRecord, SourceClass

# ── Proximity weights by source class ────────────────────────────────
_PROXIMITY: dict[str, float] = {
    "primary":      1.0,
    "operator":     0.7,
    "practitioner": 0.5,
    "media":        0.3,
    "market":       0.4,
}

# ── Incentive alignment by source class ──────────────────────────────
# Operators/vendors have conflicts of interest; community is more independent.
_INCENTIVE: dict[str, float] = {
    "primary":      0.8,  # academic incentive to publish positive results
    "operator":     0.4,  # commercial incentive
    "practitioner": 0.7,  # mostly independent
    "media":        0.5,  # traffic/narrative incentives
    "market":       0.6,  # financial incentives
}

# ── Reproducibility by evidence type ─────────────────────────────────
_REPRODUCIBILITY: dict[str, float] = {
    "experiment":    0.9,
    "benchmark":     0.8,
    "analysis":      0.6,
    "anecdote":      0.3,
    "announcement":  0.2,
    "unknown":       0.3,
}

# ── Adoption signal by evidence type ─────────────────────────────────
_ADOPTION: dict[str, float] = {
    "experiment":    0.5,
    "benchmark":     0.5,
    "analysis":      0.4,
    "anecdote":      0.6,   # anecdotes often reflect real usage
    "announcement":  0.2,
    "unknown":       0.3,
}

# Time-decay half-life in days: credibility halves every 14 days
_HALF_LIFE_DAYS = 14.0


def time_decay(date_str: str, reference: date | None = None) -> float:
    """Return a 0–1 decay multiplier based on item age."""
    if not date_str:
        return 0.8  # assume recent if unknown
    try:
        item_date = datetime.fromisoformat(date_str).date()
    except ValueError:
        return 0.8
    ref = reference or datetime.now(timezone.utc).date()
    age_days = max(0, (ref - item_date).days)
    return math.exp(-math.log(2) * age_days / _HALF_LIFE_DAYS)


def score_credibility(record: CanonicalRecord, reference_date: date | None = None) -> float:
    """Return a 0–1 composite credibility score for a canonical record.

    Axes: proximity, incentive_alignment, reproducibility, adoption_signal, time_decay.
    """
    cls = record.source_class or "practitioner"
    etype = record.evidence_type or "unknown"

    proximity      = _PROXIMITY.get(cls, 0.5)
    incentive      = _INCENTIVE.get(cls, 0.5)
    reproducibility = _REPRODUCIBILITY.get(etype, 0.3)
    adoption       = _ADOPTION.get(etype, 0.3)
    decay          = time_decay(record.date, reference_date)

    # Weighted average: proximity and reproducibility matter most
    raw = (
        proximity      * 0.30
        + incentive    * 0.15
        + reproducibility * 0.25
        + adoption     * 0.15
        + decay        * 0.15
    )
    return round(min(1.0, max(0.0, raw)), 3)


def detect_hype(record: CanonicalRecord) -> float:
    """Return a 0–1 hype risk score.

    High hype: high language intensity from low-evidence, media-class sources.
    Uses evidence type as a proxy for evidence density and source class as an
    incentive proxy. The caller (Gemini extraction) may also provide a direct
    hype_language_intensity field; if not, we derive a proxy.
    """
    # Evidence density: higher = more substantiated
    evidence_density = _REPRODUCIBILITY.get(record.evidence_type or "unknown", 0.3)

    # Source incentive risk (inverted incentive score)
    incentive_risk = 1.0 - _INCENTIVE.get(record.source_class or "practitioner", 0.5)

    # Operator announcements about their own capabilities are high-hype
    vendor_boost = 0.2 if (
        record.source_class == "operator"
        and record.evidence_type == "announcement"
    ) else 0.0

    # Media class with no primary evidence
    media_boost = 0.15 if (
        record.source_class == "media"
        and record.evidence_type in ("anecdote", "announcement", "unknown")
    ) else 0.0

    raw = (
        (1.0 - evidence_density) * 0.5
        + incentive_risk * 0.3
        + vendor_boost
        + media_boost
    )
    return round(min(1.0, max(0.0, raw)), 3)
