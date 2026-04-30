"""Unit tests for src/credibility.py — 5-axis credibility scoring (Epic 12, slice 12.4)."""

from __future__ import annotations

from datetime import date

import pytest

from src.credibility import (
    _PROXIMITY,
    _REPRODUCIBILITY,
    detect_hype,
    score_credibility,
    time_decay,
)
from src.models import CanonicalRecord

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _record(
    source_class: str = "practitioner",
    evidence_type: str = "unknown",
    date_str: str = "2026-01-15",
    url: str = "https://example.com/item",
) -> CanonicalRecord:
    return CanonicalRecord(
        url=url,
        title="Test item",
        source_class=source_class,  # type: ignore[arg-type]
        evidence_type=evidence_type,  # type: ignore[arg-type]
        date=date_str,
    )


# ---------------------------------------------------------------------------
# time_decay
# ---------------------------------------------------------------------------


class TestTimeDecay:
    def test_today_item_is_close_to_one(self):
        today = date(2026, 1, 15)
        result = time_decay("2026-01-15", reference=today)
        assert result == pytest.approx(1.0, abs=0.001)

    def test_one_half_life_ago(self):
        """After HALF_LIFE_DAYS, decay should be ~0.5."""
        reference = date(2026, 1, 29)  # 14 days after item
        result = time_decay("2026-01-15", reference=reference)
        assert result == pytest.approx(0.5, abs=0.01)

    def test_two_half_lives_ago(self):
        """After 2×HALF_LIFE_DAYS, decay should be ~0.25."""
        reference = date(2026, 2, 12)  # 28 days after item
        result = time_decay("2026-01-15", reference=reference)
        assert result == pytest.approx(0.25, abs=0.01)

    def test_old_item_asymptotically_approaches_zero(self):
        reference = date(2026, 6, 1)  # ~135 days after item
        result = time_decay("2026-01-15", reference=reference)
        assert result < 0.01

    def test_empty_date_returns_default(self):
        result = time_decay("")
        assert result == pytest.approx(0.8)

    def test_invalid_date_returns_default(self):
        result = time_decay("not-a-date")
        assert result == pytest.approx(0.8)

    def test_future_item_date_returns_one(self):
        """Items in the future (after reference) should not decay below 1.0."""
        reference = date(2026, 1, 1)
        result = time_decay("2026-01-15", reference=reference)
        # age_days is capped at 0 via max(0, …)
        assert result == pytest.approx(1.0, abs=0.001)


# ---------------------------------------------------------------------------
# score_credibility — axis checks
# ---------------------------------------------------------------------------


class TestScoreCredibility:
    def test_primary_experiment_is_high(self):
        rec = _record(source_class="primary", evidence_type="experiment")
        score = score_credibility(rec, reference_date=date(2026, 1, 15))
        # proximity=1.0, incentive=0.8, reproducibility=0.9, adoption=0.5, decay≈1
        # Weighted: 1.0×0.30 + 0.8×0.15 + 0.9×0.25 + 0.5×0.15 + 1.0×0.15 = 0.82
        assert score > 0.70

    def test_operator_announcement_is_lower(self):
        rec = _record(source_class="operator", evidence_type="announcement")
        score = score_credibility(rec, reference_date=date(2026, 1, 15))
        assert score < 0.55

    def test_media_anecdote_is_low(self):
        rec = _record(source_class="media", evidence_type="anecdote")
        score = score_credibility(rec, reference_date=date(2026, 1, 15))
        assert score < 0.50

    def test_old_item_penalised(self):
        recent = _record(source_class="primary", evidence_type="experiment", date_str="2026-01-15")
        old = _record(source_class="primary", evidence_type="experiment", date_str="2025-01-15")
        ref = date(2026, 1, 15)
        assert score_credibility(recent, ref) > score_credibility(old, ref)

    def test_score_bounded_zero_to_one(self):
        for sc in ("primary", "operator", "practitioner", "media", "market"):
            for et in ("experiment", "benchmark", "anecdote", "announcement", "unknown"):
                rec = _record(source_class=sc, evidence_type=et)
                s = score_credibility(rec)
                assert 0.0 <= s <= 1.0, f"Score out of bounds for {sc}/{et}: {s}"

    def test_unknown_source_class_uses_default(self):
        rec = _record(source_class="unknown_class")  # type: ignore[arg-type]
        score = score_credibility(rec)
        assert 0.0 <= score <= 1.0

    def test_missing_source_class_uses_practitioner_default(self):
        rec = CanonicalRecord(url="https://x.com", title="T", source_class=None)  # type: ignore[arg-type]
        score = score_credibility(rec)
        assert 0.0 <= score <= 1.0

    def test_primary_benchmark_beats_practitioner_anecdote(self):
        primary = _record(source_class="primary", evidence_type="benchmark")
        pract = _record(source_class="practitioner", evidence_type="anecdote")
        ref = date(2026, 1, 15)
        assert score_credibility(primary, ref) > score_credibility(pract, ref)


# ---------------------------------------------------------------------------
# detect_hype
# ---------------------------------------------------------------------------


class TestDetectHype:
    def test_operator_announcement_is_high_hype(self):
        rec = _record(source_class="operator", evidence_type="announcement")
        hype = detect_hype(rec)
        assert hype > 0.55, f"Operator announcement hype should be high, got {hype}"

    def test_media_anecdote_is_high_hype(self):
        rec = _record(source_class="media", evidence_type="anecdote")
        hype = detect_hype(rec)
        assert hype > 0.50

    def test_primary_experiment_is_low_hype(self):
        rec = _record(source_class="primary", evidence_type="experiment")
        hype = detect_hype(rec)
        assert hype < 0.30

    def test_hype_bounded_zero_to_one(self):
        for sc in ("primary", "operator", "practitioner", "media", "market"):
            for et in ("experiment", "benchmark", "anecdote", "announcement", "unknown"):
                rec = _record(source_class=sc, evidence_type=et)
                h = detect_hype(rec)
                assert 0.0 <= h <= 1.0, f"Hype out of bounds for {sc}/{et}: {h}"

    def test_operator_with_experiment_is_lower_than_operator_with_announcement(self):
        announce = _record(source_class="operator", evidence_type="announcement")
        experiment = _record(source_class="operator", evidence_type="experiment")
        assert detect_hype(announce) > detect_hype(experiment)

    def test_hype_inversely_related_to_credibility(self):
        """High hype sources should have lower credibility scores."""
        high_hype_rec = _record(source_class="media", evidence_type="announcement")
        low_hype_rec = _record(source_class="primary", evidence_type="experiment")
        ref = date(2026, 1, 15)
        assert detect_hype(high_hype_rec) > detect_hype(low_hype_rec)
        assert score_credibility(high_hype_rec, ref) < score_credibility(low_hype_rec, ref)


# ---------------------------------------------------------------------------
# Proximity axis completeness
# ---------------------------------------------------------------------------


class TestProximityAxis:
    @pytest.mark.parametrize(
        "source_class", ["primary", "operator", "practitioner", "media", "market"]
    )
    def test_all_source_classes_have_proximity(self, source_class: str):
        assert source_class in _PROXIMITY

    def test_primary_has_highest_proximity(self):
        assert _PROXIMITY["primary"] == max(_PROXIMITY.values())

    def test_media_has_lower_proximity_than_primary(self):
        assert _PROXIMITY["media"] < _PROXIMITY["primary"]


# ---------------------------------------------------------------------------
# Reproducibility axis completeness
# ---------------------------------------------------------------------------


class TestReproducibilityAxis:
    @pytest.mark.parametrize(
        "evidence_type",
        ["experiment", "benchmark", "analysis", "anecdote", "announcement", "unknown"],
    )
    def test_all_evidence_types_have_reproducibility(self, evidence_type: str):
        assert evidence_type in _REPRODUCIBILITY

    def test_experiment_beats_announcement(self):
        assert _REPRODUCIBILITY["experiment"] > _REPRODUCIBILITY["announcement"]
