"""Trend state machine: classify themes as emerging / scaling / mature / declining."""

from __future__ import annotations

from src.models import TrendMetrics, TrendState

# Minimum distinct source classes required for any non-declining state.
_MIN_DIVERSITY_FOR_TREND = 2

# Velocity thresholds (week-over-week credibility-weighted volume change)
_VEL_EMERGING_MIN  =  0.1
_VEL_SCALING_MIN   =  0.15
_VEL_MATURE_MAX    =  0.15  # near-zero velocity
_VEL_DECLINING_MAX = -0.05

# Volume thresholds (weekly credibility-weighted item count)
_VOL_SCALING_MIN = 2.0
_VOL_MATURE_MIN  = 4.0


def classify_state(metrics: TrendMetrics) -> TrendState:
    """Classify a theme's trend state from its metrics.

    Rules (applied in order; first match wins):
    1. Insufficient diversity → unknown (insufficient cross-source support)
    2. Declining velocity with falling volume → declining
    3. High velocity, moderate volume, low adoption → emerging
    4. High velocity, meaningful volume → scaling
    5. Low velocity, high volume, stable → mature
    6. Default → unknown
    """
    v = metrics.velocity
    vol = metrics.volume
    div = metrics.diversity

    # Rule 1: need cross-class confirmation to be anything but declining/unknown
    if div < _MIN_DIVERSITY_FOR_TREND and v >= 0:
        return "unknown"

    # Rule 2: declining
    if v <= _VEL_DECLINING_MAX:
        return "declining"

    # Rule 3: emerging — fast-rising but still small and unproven
    if v >= _VEL_EMERGING_MIN and vol < _VOL_SCALING_MIN and div >= _MIN_DIVERSITY_FOR_TREND:
        return "emerging"

    # Rule 4: scaling — growing meaningfully across sources
    if v >= _VEL_SCALING_MIN and vol >= _VOL_SCALING_MIN and div >= _MIN_DIVERSITY_FOR_TREND:
        return "scaling"

    # Rule 5: mature — stable high-volume theme
    if abs(v) < _VEL_MATURE_MAX and vol >= _VOL_MATURE_MIN and div >= _MIN_DIVERSITY_FOR_TREND:
        return "mature"

    return "unknown"


def compute_velocity(current_volume: float, history: list[dict]) -> float:
    """Compute week-over-week velocity from history snapshots.

    *history* is a list of dicts [{date, volume, state}, ...] sorted oldest-first.
    Returns the change between the most recent two data points, normalised by
    the older value to make it a relative rate.
    """
    if len(history) < 2:
        return 0.0

    prev_vol = history[-2].get("volume", 0.0)
    if prev_vol == 0:
        # Previous was zero: treat growth as a large positive signal, capped
        return min(1.0, current_volume * 0.5)

    return round((current_volume - prev_vol) / prev_vol, 4)


def compute_stability(history: list[dict]) -> float:
    """Return stability (inverse normalised variance) from volume history.

    1.0 = perfectly stable; 0.0 = highly volatile.
    """
    volumes = [h.get("volume", 0.0) for h in history if "volume" in h]
    if len(volumes) < 2:
        return 1.0

    mean = sum(volumes) / len(volumes)
    if mean == 0:
        return 1.0

    variance = sum((v - mean) ** 2 for v in volumes) / len(volumes)
    # Normalise coefficient of variation (std/mean); cap at 1
    cv = (variance ** 0.5) / mean
    return round(max(0.0, 1.0 - min(cv, 1.0)), 3)


def update_metrics(
    metrics: TrendMetrics,
    new_volume: float,
    today_str: str,
    max_history: int = 30,
) -> TrendMetrics:
    """Append today's snapshot, recompute derived fields, return updated metrics."""
    # Append snapshot
    metrics.history.append({"date": today_str, "volume": new_volume, "state": metrics.state})
    if len(metrics.history) > max_history:
        metrics.history = metrics.history[-max_history:]

    metrics.volume   = new_volume
    metrics.velocity = compute_velocity(new_volume, metrics.history)
    metrics.stability = compute_stability(metrics.history)
    metrics.state    = classify_state(metrics)
    return metrics
