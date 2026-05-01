"""Tests for adoption_proxy computation in build_trend_metrics (W-0012)."""

from __future__ import annotations

from src.trends import build_trend_metrics


def _make_history(
    entries: list[tuple[str, str, str]],
    today: str = "2026-05-01",
) -> list[tuple[str, str, str, str]]:
    """Build history tuples from (source_class, source_name, date) triples."""
    return [(date, "test theme", cls, name) for date, cls, name in entries]


def _repeated(
    source_class: str,
    source_name: str,
    count: int,
    date: str = "2026-05-01",
) -> list[tuple[str, str, str]]:
    return [(date, source_class, source_name)] * count


class TestAdoptionProxyComputation:
    TODAY = "2026-05-01"

    def _get_proxy(self, raw_entries: list[tuple[str, str, str, str]]) -> float:
        metrics = build_trend_metrics(raw_entries, {}, self.TODAY)
        assert metrics, "Expected at least one metric"
        return metrics[0].adoption_proxy

    def test_zero_for_primary_only_sources(self):
        """Research-only theme: no market, no practitioner → proxy near zero."""
        entries = _make_history(
            _repeated("primary", "arXiv", 5) + _repeated("primary", "HuggingFace", 5)
        )
        proxy = self._get_proxy(entries)
        # Only breadth signal (primary class present but no market/practitioner)
        # breadth_classes = {"primary"} → len-1 = 0 → 0.0 breadth
        assert proxy == 0.0

    def test_nonzero_for_market_class_entries(self):
        """Market items (pricing data) should produce nonzero adoption_proxy."""
        entries = _make_history(
            _repeated("primary", "arXiv", 5) + _repeated("market", "OpenRouter", 3)
        )
        proxy = self._get_proxy(entries)
        assert proxy > 0.0

    def test_nonzero_for_practitioner_class_entries(self):
        """Practitioner items should produce nonzero adoption_proxy."""
        entries = _make_history(
            _repeated("primary", "arXiv", 5) + _repeated("practitioner", "YouTube", 5)
        )
        proxy = self._get_proxy(entries)
        assert proxy > 0.0

    def test_adoption_proxy_bounded_zero_to_one(self):
        """Proxy must always be in [0, 1]."""
        entries = _make_history(
            _repeated("primary", "arXiv", 10)
            + _repeated("market", "OpenRouter", 10)
            + _repeated("practitioner", "YouTube", 10)
            + _repeated("operator", "Anthropic", 10)
        )
        proxy = self._get_proxy(entries)
        assert 0.0 <= proxy <= 1.0

    def test_more_market_entries_increases_proxy(self):
        """Adding more market-class entries should increase or maintain proxy."""
        base = _make_history(
            _repeated("primary", "arXiv", 5) + _repeated("market", "OpenRouter", 2)
        )
        more_market = _make_history(
            _repeated("primary", "arXiv", 5) + _repeated("market", "OpenRouter", 8)
        )
        proxy_base = self._get_proxy(base)
        proxy_more = self._get_proxy(more_market)
        assert proxy_more >= proxy_base

    def test_cross_class_breadth_adds_signal(self):
        """A theme with 4 distinct classes should have higher proxy than 2 classes."""
        two_classes = _make_history(
            _repeated("primary", "arXiv", 5) + _repeated("market", "OpenRouter", 5)
        )
        four_classes = _make_history(
            _repeated("primary", "arXiv", 5)
            + _repeated("market", "OpenRouter", 5)
            + _repeated("practitioner", "YouTube", 5)
            + _repeated("operator", "Anthropic", 5)
        )
        proxy_two = self._get_proxy(two_classes)
        proxy_four = self._get_proxy(four_classes)
        assert proxy_four > proxy_two

    def test_adoption_proxy_returned_in_metrics(self):
        """adoption_proxy must be stored on TrendMetrics (not always 0.0)."""
        entries = _make_history(
            _repeated("primary", "arXiv", 5)
            + _repeated("market", "OpenRouter", 5)
            + _repeated("practitioner", "Ollama", 5)
        )
        metrics = build_trend_metrics(entries, {}, self.TODAY)
        assert metrics[0].adoption_proxy != 0.0, (
            "adoption_proxy should be non-zero when market/practitioner items are present"
        )
