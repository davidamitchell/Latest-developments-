"""Stage 8 — Credibility Scoring.

Derives credibility_score from the item's source class and evidence type using
the existing score_credibility() function from src.credibility.
No external calls — purely deterministic.
"""

from __future__ import annotations

import dataclasses

import src.credibility as _cred
from src.models import CanonicalRecord, ProcessedItem


def score_credibility(item: ProcessedItem) -> ProcessedItem:
    """Return item with credibility_score set."""
    date_str = item.fetch_date or (item.published.date().isoformat() if item.published else "")
    record = CanonicalRecord(
        url=item.url,
        title=item.title,
        source_class=item.source_class,
        evidence_type=item.evidence_type,
        has_code=item.has_code,
        domain=item.domain,
        impact_vector=item.impact_vector,
        actors=list(item.actors),
        date=date_str,
    )
    credibility = _cred.score_credibility(record)
    return dataclasses.replace(item, credibility_score=credibility)
