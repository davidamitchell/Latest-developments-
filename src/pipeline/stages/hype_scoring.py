"""Stage 7 — Hype Scoring.

Derives hype_risk from the item's source class and evidence type using the
existing detect_hype() function from src.credibility.
No external calls — purely deterministic.
"""

from __future__ import annotations

import dataclasses

from src.credibility import detect_hype
from src.models import CanonicalRecord, ProcessedItem


def score_hype(item: ProcessedItem) -> ProcessedItem:
    """Return item with hype_risk set."""
    record = CanonicalRecord(
        url=item.url,
        title=item.title,
        source_class=item.source_class,
        evidence_type=item.evidence_type,
        has_code=item.has_code,
        domain=item.domain,
        impact_vector=item.impact_vector,
        actors=list(item.actors),
    )
    hype_risk = detect_hype(record)
    return dataclasses.replace(item, hype_risk=hype_risk)
