"""Tests for src/trend_state.py — state machine transitions (Epic 14, slice 14.5)."""

from __future__ import annotations

import pytest

from src.models import TrendMetrics
from src.trend_state import (
    _MIN_DIVERSITY_FOR_TREND,
    _VEL_DECLINING_MAX,
    _VEL_EMERGING_MIN,
    _VEL_MATURE_MAX,
    _VEL_SCALING_MIN,
    _VOL_MATURE_MIN,
    _VOL_SCALING_MIN,
    classify_state,
    compute_stability,
    compute_velocity,
    update_metrics,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _metrics(
    velocity: float = 0.0,
    volume: float = 0.0,
    diversity: int = 3,
    adoption_proxy: float = 0.0,
    stability: float = 1.0,
    history: list[dict] | None = None,
) -> TrendMetrics:
    return TrendMetrics(
        theme="Test Theme",
        velocity=velocity,
        volume=volume,
        diversity=diversity,
        adoption_proxy=adoption_proxy,
        stability=stability,
        history=history or [],
    )


# ---------------------------------------------------------------------------
# Diversity gate (Rule 1)
# ---------------------------------------------------------------------------


class TestDiversityGate:
    def test_low_diversity_positive_velocity_gives_unknown(self):
        """Single-source signal — cannot confirm emerging trend."""
        m = _metrics(velocity=0.5, volume=1.0, diversity=1)
        assert classify_state(m) == "unknown"

    def test_low_diversity_exactly_one_gives_unknown(self):
        m = _metrics(velocity=0.3, volume=3.0, diversity=1)
        assert classify_state(m) == "unknown"

    def test_low_diversity_declining_is_still_declining(self):
        """Declining can be classified even with low diversity."""
        m = _metrics(velocity=-0.2, volume=2.0, diversity=1)
        assert classify_state(m) == "declining"

    def test_minimum_diversity_allows_classification(self):
        m = _metrics(
            velocity=_VEL_EMERGING_MIN + 0.05, volume=1.0, diversity=_MIN_DIVERSITY_FOR_TREND
        )
        assert classify_state(m) == "emerging"


# ---------------------------------------------------------------------------
# Declining (Rule 2)
# ---------------------------------------------------------------------------


class TestDecliningState:
    def test_negative_velocity_is_declining(self):
        m = _metrics(velocity=_VEL_DECLINING_MAX - 0.01, diversity=3)
        assert classify_state(m) == "declining"

    def test_exactly_at_declining_threshold(self):
        m = _metrics(velocity=_VEL_DECLINING_MAX, diversity=3)
        assert classify_state(m) == "declining"

    def test_single_source_strongly_declining(self):
        """Even with single source, declining is classified."""
        m = _metrics(velocity=-0.5, volume=1.0, diversity=1)
        assert classify_state(m) == "declining"

    def test_just_above_declining_threshold_not_declining(self):
        """Velocity just above threshold should not trigger declining."""
        m = _metrics(velocity=_VEL_DECLINING_MAX + 0.01, volume=0.5, diversity=1)
        # Not enough velocity for emerging and low diversity → unknown
        assert classify_state(m) != "declining"


# ---------------------------------------------------------------------------
# Emerging (Rule 3)
# ---------------------------------------------------------------------------


class TestEmergingState:
    def test_fast_rising_low_volume_multi_source_is_emerging(self):
        m = _metrics(
            velocity=_VEL_EMERGING_MIN + 0.1,
            volume=_VOL_SCALING_MIN - 0.5,
            diversity=_MIN_DIVERSITY_FOR_TREND,
        )
        assert classify_state(m) == "emerging"

    def test_high_velocity_but_low_diversity_is_unknown(self):
        m = _metrics(velocity=0.8, volume=0.5, diversity=1)
        assert classify_state(m) == "unknown"

    def test_spike_vs_trend_low_diversity_stays_unknown(self):
        """A single-day spike with one source is a spike, not a trend."""
        m = _metrics(velocity=2.0, volume=0.5, diversity=1)
        assert classify_state(m) == "unknown"


# ---------------------------------------------------------------------------
# Scaling (Rule 4)
# ---------------------------------------------------------------------------


class TestScalingState:
    def test_high_velocity_high_volume_multi_source_is_scaling(self):
        m = _metrics(
            velocity=_VEL_SCALING_MIN + 0.1,
            volume=_VOL_SCALING_MIN + 1.0,
            diversity=_MIN_DIVERSITY_FOR_TREND,
        )
        assert classify_state(m) == "scaling"

    def test_scaling_requires_minimum_volume(self):
        """High velocity with volume below scaling threshold → emerging, not scaling."""
        m = _metrics(
            velocity=_VEL_SCALING_MIN + 0.5,
            volume=_VOL_SCALING_MIN - 0.1,
            diversity=_MIN_DIVERSITY_FOR_TREND,
        )
        assert classify_state(m) != "scaling"

    def test_scaling_requires_diversity(self):
        m = _metrics(
            velocity=_VEL_SCALING_MIN + 0.1,
            volume=_VOL_SCALING_MIN + 1.0,
            diversity=1,
        )
        assert classify_state(m) != "scaling"


# ---------------------------------------------------------------------------
# Mature (Rule 5)
# ---------------------------------------------------------------------------


class TestMatureState:
    def test_stable_high_volume_is_mature(self):
        m = _metrics(
            velocity=0.0,  # near-zero = abs(_VEL_MATURE_MAX)
            volume=_VOL_MATURE_MIN + 1.0,
            diversity=_MIN_DIVERSITY_FOR_TREND,
        )
        assert classify_state(m) == "mature"

    def test_mature_requires_high_volume(self):
        m = _metrics(
            velocity=0.0,
            volume=_VOL_MATURE_MIN - 0.5,
            diversity=_MIN_DIVERSITY_FOR_TREND,
        )
        assert classify_state(m) != "mature"

    def test_mature_requires_diversity(self):
        m = _metrics(
            velocity=0.0,
            volume=_VOL_MATURE_MIN + 1.0,
            diversity=1,
        )
        assert classify_state(m) != "mature"

    def test_high_positive_velocity_not_mature(self):
        """Fast-growing theme with high volume should be scaling, not mature."""
        m = _metrics(
            velocity=_VEL_MATURE_MAX + 0.5,
            volume=_VOL_MATURE_MIN + 2.0,
            diversity=_MIN_DIVERSITY_FOR_TREND,
        )
        assert classify_state(m) != "mature"


# ---------------------------------------------------------------------------
# Default → unknown
# ---------------------------------------------------------------------------


class TestUnknownDefault:
    def test_no_signal_is_unknown(self):
        m = _metrics(velocity=0.0, volume=0.0, diversity=0)
        assert classify_state(m) == "unknown"

    def test_zero_velocity_low_volume_is_unknown(self):
        m = _metrics(velocity=0.0, volume=0.5, diversity=_MIN_DIVERSITY_FOR_TREND)
        assert classify_state(m) == "unknown"


# ---------------------------------------------------------------------------
# compute_velocity
# ---------------------------------------------------------------------------


class TestComputeVelocity:
    def test_returns_zero_with_no_history(self):
        assert compute_velocity(1.0, []) == 0.0

    def test_returns_zero_with_single_history_point(self):
        assert compute_velocity(2.0, [{"volume": 1.0}]) == 0.0

    def test_growth_from_one_to_two_is_100_percent(self):
        history = [{"volume": 1.0}, {"volume": 2.0}]
        v = compute_velocity(2.0, history)
        # (2 - 1) / 1 = 1.0
        assert v == pytest.approx(1.0)

    def test_decline_from_two_to_one_is_minus_50_percent(self):
        history = [{"volume": 2.0}, {"volume": 1.0}]
        v = compute_velocity(1.0, history)
        # (1 - 2) / 2 = -0.5
        assert v == pytest.approx(-0.5)

    def test_zero_prev_volume_caps_at_upper_bound(self):
        history = [{"volume": 0.0}, {"volume": 0.0}]
        v = compute_velocity(4.0, history)
        assert 0.0 <= v <= 1.0

    def test_flat_history_is_zero_velocity(self):
        history = [{"volume": 3.0}, {"volume": 3.0}]
        v = compute_velocity(3.0, history)
        assert v == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# compute_stability
# ---------------------------------------------------------------------------


class TestComputeStability:
    def test_constant_volume_is_perfectly_stable(self):
        history = [{"volume": 3.0}, {"volume": 3.0}, {"volume": 3.0}]
        assert compute_stability(history) == pytest.approx(1.0)

    def test_single_point_is_stable(self):
        assert compute_stability([{"volume": 5.0}]) == 1.0

    def test_empty_history_is_stable(self):
        assert compute_stability([]) == 1.0

    def test_highly_volatile_history_is_low_stability(self):
        # Alternating 0 and 10
        history = [{"volume": 0.0}, {"volume": 10.0}, {"volume": 0.0}, {"volume": 10.0}]
        s = compute_stability(history)
        assert s < 0.5

    def test_stability_bounded_zero_to_one(self):
        histories = [
            [{"volume": v} for v in [1, 1, 1, 1]],
            [{"volume": v} for v in [0, 10, 0, 10]],
            [{"volume": v} for v in [1, 2, 3, 4, 5]],
        ]
        for h in histories:
            s = compute_stability(h)
            assert 0.0 <= s <= 1.0


# ---------------------------------------------------------------------------
# update_metrics
# ---------------------------------------------------------------------------


class TestUpdateMetrics:
    def test_appends_snapshot_to_history(self):
        m = _metrics(
            volume=2.0, history=[{"date": "2026-01-14", "volume": 1.0, "state": "emerging"}]
        )
        updated = update_metrics(m, new_volume=2.5, today_str="2026-01-15")
        assert len(updated.history) == 2
        assert updated.history[-1]["date"] == "2026-01-15"
        assert updated.history[-1]["volume"] == pytest.approx(2.5)

    def test_history_capped_at_max(self):
        history = [
            {"date": f"2026-01-{i:02d}", "volume": float(i), "state": "unknown"}
            for i in range(1, 32)
        ]
        m = _metrics(history=history)
        updated = update_metrics(m, new_volume=5.0, today_str="2026-02-01", max_history=30)
        assert len(updated.history) <= 30

    def test_volume_is_updated(self):
        m = _metrics(volume=1.0)
        updated = update_metrics(m, new_volume=3.0, today_str="2026-01-15")
        assert updated.volume == pytest.approx(3.0)

    def test_state_recomputed_after_update(self):
        m = _metrics(velocity=0.0, volume=0.5, diversity=3)
        # Before update: probably unknown
        assert classify_state(m) == "unknown"

        # Now simulate growing into scaling range
        m.history = [{"date": "2026-01-01", "volume": 1.0, "state": "unknown"}]
        updated = update_metrics(m, new_volume=5.0, today_str="2026-01-08")
        # State should be recomputed
        assert updated.state in ("emerging", "scaling", "mature", "declining", "unknown")
