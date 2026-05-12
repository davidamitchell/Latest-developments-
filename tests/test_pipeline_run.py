"""TDD tests for src/pipeline/run.py — the processing entrypoint."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from src.fetchers import FetchedItem
from src.models import ProcessedItem

_QUOTA_METRIC = "generativelanguage.googleapis.com/generate_content_free_tier_requests"


def _make_fetched(id_: str = "item-1") -> FetchedItem:
    return FetchedItem(
        id=id_,
        title="Test Title",
        url=f"https://example.com/{id_}",
        content="<p>LLM inference research findings.</p>",
        source_name="Test Source",
        source_type="rss",
        source_class="practitioner",
        author="Alice",
        published=datetime(2026, 5, 2, tzinfo=UTC),
        has_code=False,
        evidence_type="analysis",
    )


# ── process ─────────────────────────────────────────────────────────────────


class TestProcess:
    """process(items, gemini_api_key, fetch_date) → (list[ProcessedItem], int failures)"""

    def _null_client(self):
        """A Gemini client mock that returns minimal valid combined-enrichment responses."""
        from google.genai.types import FinishReason

        client = MagicMock()
        resp = MagicMock()
        resp.text = (
            "CONCEPTS: LLM\n"
            "ACTORS: none\n"
            "IMPACT: capability\n"
            "THEME: inference\n"
            "DOMAIN: infra\n"
            "SUMMARY: Sentence one. Sentence two.\n"
            "MARKETING: false\n"
            "CONFIDENCE: 0.1"
        )
        candidate = MagicMock()
        candidate.finish_reason = FinishReason.STOP
        resp.candidates = [candidate]
        client.models.generate_content.return_value = resp
        return client

    def _mock_http_client(self):
        m = MagicMock()
        m.ratelimit_headers = {}
        return m

    @contextmanager
    def _patch_gemini(self, client=None):
        """Patch _make_gemini_client (tuple) and _resolve_cascade for tests."""
        if client is None:
            client = self._null_client()
        with (
            patch("src.pipeline.run._make_gemini_client", return_value=(client, self._mock_http_client())),
            patch("src.pipeline.run._resolve_cascade", return_value=["gemini-2.5-flash"]),
        ):
            yield

    def test_returns_list(self):
        from src.pipeline.run import process

        items = [_make_fetched("a"), _make_fetched("b")]
        with self._patch_gemini():
            result, _ = process(items, gemini_api_key="fake-key", fetch_date="2026-05-02")
        assert isinstance(result, list)

    def test_returns_one_item_per_input(self):
        from src.pipeline.run import process

        items = [_make_fetched("a"), _make_fetched("b")]
        with self._patch_gemini():
            result, _ = process(items, gemini_api_key="fake-key", fetch_date="2026-05-02")
        assert len(result) == 2

    def test_all_results_are_processed_items(self):
        from src.pipeline.run import process

        items = [_make_fetched("x")]
        with self._patch_gemini():
            result, _ = process(items, gemini_api_key="fake-key", fetch_date="2026-05-02")
        assert all(isinstance(r, ProcessedItem) for r in result)

    def test_ids_match_input(self):
        from src.pipeline.run import process

        items = [_make_fetched("id-1"), _make_fetched("id-2")]
        with self._patch_gemini():
            result, _ = process(items, gemini_api_key="fake-key", fetch_date="2026-05-02")
        result_ids = {r.id for r in result}
        assert result_ids == {"id-1", "id-2"}

    def test_fetch_date_propagated(self):
        from src.pipeline.run import process

        items = [_make_fetched("d1")]
        with self._patch_gemini():
            result, _ = process(items, gemini_api_key="fake-key", fetch_date="2026-05-02")
        assert all(r.fetch_date == "2026-05-02" for r in result)

    def test_cleaned_content_set(self):
        from src.pipeline.run import process

        items = [_make_fetched("c1")]
        with self._patch_gemini():
            result, _ = process(items, gemini_api_key="fake-key", fetch_date="2026-05-02")
        assert all(len(r.cleaned_content) > 0 for r in result)

    def test_credibility_score_set(self):
        from src.pipeline.run import process

        items = [_make_fetched("cs1")]
        with self._patch_gemini():
            result, _ = process(items, gemini_api_key="fake-key", fetch_date="2026-05-02")
        assert all(0.0 <= r.credibility_score <= 1.0 for r in result)

    def test_hype_risk_set(self):
        from src.pipeline.run import process

        items = [_make_fetched("h1")]
        with self._patch_gemini():
            result, _ = process(items, gemini_api_key="fake-key", fetch_date="2026-05-02")
        assert all(0.0 <= r.hype_risk <= 1.0 for r in result)

    def test_empty_input_returns_empty_list(self):
        from src.pipeline.run import process

        with self._patch_gemini():
            result, failures = process([], gemini_api_key="fake-key", fetch_date="2026-05-02")
        assert result == []
        assert failures == 0

    def test_works_without_gemini_key(self):
        """When no Gemini key is provided, AI stages are skipped gracefully."""
        from src.pipeline.run import process

        items = [_make_fetched("no-key")]
        result, failures = process(items, gemini_api_key=None, fetch_date="2026-05-02")
        assert len(result) == 1
        assert result[0].id == "no-key"
        assert result[0].fetch_date == "2026-05-02"
        assert result[0].credibility_score > 0.0
        assert failures == 0

    def test_ai_failure_counted(self):
        """Non-quota Gemini transport errors are counted per item."""
        from google.genai.errors import ClientError

        from src.pipeline.run import process

        client = MagicMock()
        client.models.generate_content.side_effect = ClientError(
            429, {"error": "temporary upstream error"}
        )
        items = [_make_fetched("fail-1"), _make_fetched("fail-2")]
        with (
            self._patch_gemini(client=client),
            patch("src.pipeline._gemini.time.sleep"),
            patch("src.retry.time.sleep"),
        ):
            result, failures = process(items, gemini_api_key="fake-key", fetch_date="2026-05-02")
        assert failures == 2
        assert len(result) == 2

    def test_quota_exhaustion_stops_ai_for_remaining_items(self):
        """When free-tier quota is exhausted, process() stops further AI calls in this run."""
        from google.genai.errors import ClientError

        from src.pipeline.run import process

        quota_exc = ClientError(
            429,
            {
                "error": {
                    "code": 429,
                    "message": f"Quota exceeded for metric: {_QUOTA_METRIC}",
                    "status": "RESOURCE_EXHAUSTED",
                }
            },
        )
        quota_exc.details = [
            {
                "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                "violations": [{"quotaMetric": _QUOTA_METRIC}],
            }
        ]

        client = MagicMock()
        client.models.generate_content.side_effect = quota_exc
        items = [_make_fetched("quota-1"), _make_fetched("quota-2"), _make_fetched("quota-3")]

        with (
            self._patch_gemini(client=client),
            patch("src.pipeline._gemini.time.sleep"),
            patch("src.retry.time.sleep") as retry_sleep,
        ):
            result, failures = process(items, gemini_api_key="fake-key", fetch_date="2026-05-02")

        assert len(result) == 3
        assert failures == 1
        # First item hits quota and is not retried; remaining items skip AI.
        assert client.models.generate_content.call_count == 1
        assert all(item.summary == "" for item in result[1:])
        assert all(item.concepts == [] for item in result[1:])
        assert all(item.credibility_score > 0.0 for item in result)
        retry_sleep.assert_not_called()

    def test_process_retries_client_error_using_server_retry_delay(self):
        from google.genai.errors import ClientError

        from src.pipeline.run import process

        client = MagicMock()
        items = [_make_fetched("retry-429")]

        transient = ClientError(429, {"error": "quota exceeded"})
        transient.details = [
            {
                "@type": "type.googleapis.com/google.rpc.RetryInfo",
                "retryDelay": "47s",
            }
        ]
        calls = 0

        def enrich_side_effect(item: ProcessedItem, *_args, **_kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise transient
            return item, True

        with (
            self._patch_gemini(client=client),
            patch("src.pipeline.run.enrich", side_effect=enrich_side_effect),
            patch("src.pipeline._gemini.time.sleep"),
            patch("src.retry.time.sleep") as retry_sleep,
        ):
            result, failures = process(items, gemini_api_key="fake-key", fetch_date="2026-05-02")

        assert len(result) == 1
        assert failures == 0
        assert calls == 2
        retry_sleep.assert_called_once_with(47.0)

    def test_process_propagates_non_retryable_enrich_errors(self):
        from src.pipeline.run import process

        client = MagicMock()
        items = [_make_fetched("non-retryable")]

        with (
            self._patch_gemini(client=client),
            patch("src.pipeline.run.enrich", side_effect=ValueError("bad payload")),
            patch("src.pipeline._gemini.time.sleep"),
            patch("src.retry.time.sleep") as retry_sleep,
            pytest.raises(ValueError, match="bad payload"),
        ):
            process(items, gemini_api_key="fake-key", fetch_date="2026-05-02")

        retry_sleep.assert_not_called()

    @patch("src.pipeline._gemini.time.sleep")
    def test_rate_limiter_paces_gemini_calls(self, mock_sleep):
        """The rate limiter sleeps between consecutive Gemini calls."""
        from src.pipeline.run import process

        items = [_make_fetched("rl-1"), _make_fetched("rl-2"), _make_fetched("rl-3")]
        with self._patch_gemini():
            process(items, gemini_api_key="fake-key", fetch_date="2026-05-02")
        assert mock_sleep.call_count >= 2


# ── _RateLimiter ─────────────────────────────────────────────────────────────


class TestRateLimiter:
    def test_first_call_does_not_sleep(self):
        from src.pipeline._gemini import _RateLimiter

        with (
            patch("src.pipeline._gemini.time.sleep") as mock_sleep,
            patch("src.pipeline._gemini.time.monotonic", side_effect=[1000.0, 1000.0]),
        ):
            rl = _RateLimiter(rpm=5)
            rl.wait()
        mock_sleep.assert_not_called()

    def test_rapid_second_call_sleeps(self):
        from src.pipeline._gemini import _RateLimiter

        # Simulate: first call at t=1000, second call immediately at t=1000.1
        # With 5 RPM the interval is 12s, so we expect ~11.9s sleep.
        monotonic_values = [1000.0, 1000.0, 1000.1, 1000.1]
        with (
            patch("src.pipeline._gemini.time.sleep") as mock_sleep,
            patch("src.pipeline._gemini.time.monotonic", side_effect=monotonic_values),
        ):
            rl = _RateLimiter(rpm=5)
            rl.wait()  # first call — no sleep
            rl.wait()  # second call — should sleep
        assert mock_sleep.call_count == 1
        slept = mock_sleep.call_args.args[0]
        assert 11.0 < slept < 12.5

    def test_call_after_full_interval_does_not_sleep(self):
        from src.pipeline._gemini import _RateLimiter

        # Second call arrives 15s after first — no sleep needed.
        monotonic_values = [1000.0, 1000.0, 1015.0, 1015.0]
        with (
            patch("src.pipeline._gemini.time.sleep") as mock_sleep,
            patch("src.pipeline._gemini.time.monotonic", side_effect=monotonic_values),
        ):
            rl = _RateLimiter(rpm=5)
            rl.wait()
            rl.wait()
        mock_sleep.assert_not_called()


# ── quota detection ───────────────────────────────────────────────────────────


class TestQuotaDetection:
    def test_detects_quota_exhaustion_from_message_text(self):
        from google.genai.errors import ClientError

        from src.pipeline.run import _is_quota_exhausted_error

        exc = ClientError(
            429,
            {"error": {"message": f"Quota exceeded for metric: {_QUOTA_METRIC}"}},
        )
        assert _is_quota_exhausted_error(exc) is True

    def test_detects_quota_exhaustion_from_quota_id(self):
        from google.genai.errors import ClientError

        from src.pipeline.run import _is_quota_exhausted_error

        exc = ClientError(429, {"error": "quota"})
        exc.details = [
            {
                "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}],
            }
        ]
        assert _is_quota_exhausted_error(exc) is True

    def test_ignores_non_dict_details_and_non_quota_payloads(self):
        from google.genai.errors import ClientError

        from src.pipeline.run import _is_quota_exhausted_error

        exc = ClientError(429, {"error": "temporary issue"})
        exc.details = [
            "not-a-dict",
            {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": ["not-a-dict"]},
        ]
        assert _is_quota_exhausted_error(exc) is False

    def test_non_429_errors_are_not_treated_as_quota_exhaustion(self):
        from google.genai.errors import ClientError

        from src.pipeline.run import _is_quota_exhausted_error

        exc = ClientError(500, {"error": f"Quota exceeded for metric: {_QUOTA_METRIC}"})
        assert _is_quota_exhausted_error(exc) is False

    def test_remaining_item_count_helper(self):
        from src.pipeline.run import _remaining_item_count

        assert _remaining_item_count(5, 0) == 4
        assert _remaining_item_count(5, 4) == 0


class TestMergeAndWriteProcessed:
    def _make_processed(self, id_: str) -> ProcessedItem:
        return ProcessedItem(
            id=id_,
            title="T",
            url="https://example.com",
            source_name="S",
            source_type="rss",
            source_class="practitioner",
            author="",
            published=None,
            has_code=False,
            evidence_type="unknown",
            fetch_date="2026-05-02",
            cleaned_content="cleaned text",
        )

    def test_preserves_existing_items_when_no_new_items(self, tmp_path):
        from src.models import read_processed_jsonl, write_processed_jsonl
        from src.pipeline.run import _merge_and_write

        path = tmp_path / "processed.jsonl"
        existing = [self._make_processed("existing-1"), self._make_processed("existing-2")]
        write_processed_jsonl(existing, path)

        merged = _merge_and_write(path, [])
        reloaded = read_processed_jsonl(path)

        assert [item.id for item in merged] == ["existing-1", "existing-2"]
        assert [item.id for item in reloaded] == ["existing-1", "existing-2"]


# ── write_processed_jsonl ────────────────────────────────────────────────────


class TestWriteProcessedJsonl:
    def _make_processed(self, id_: str) -> ProcessedItem:
        return ProcessedItem(
            id=id_,
            title="T",
            url="https://example.com",
            source_name="S",
            source_type="rss",
            source_class="practitioner",
            author="",
            published=None,
            has_code=False,
            evidence_type="unknown",
            fetch_date="2026-05-02",
            cleaned_content="cleaned text",
            summary="Summary here.",
        )

    def test_writes_one_line_per_item(self, tmp_path):
        from src.models import write_processed_jsonl

        items = [self._make_processed("p1"), self._make_processed("p2")]
        path = tmp_path / "processed.jsonl"
        write_processed_jsonl(items, path)
        lines = path.read_text().splitlines()
        assert len(lines) == 2

    def test_each_line_is_valid_json(self, tmp_path):
        from src.models import write_processed_jsonl

        items = [self._make_processed("p3")]
        path = tmp_path / "processed.jsonl"
        write_processed_jsonl(items, path)
        for line in path.read_text().splitlines():
            d = json.loads(line)
            assert "id" in d
            assert "credibility_score" in d

    def test_roundtrip_via_from_dict(self, tmp_path):
        from src.models import write_processed_jsonl

        original = self._make_processed("rt-2")
        path = tmp_path / "processed.jsonl"
        write_processed_jsonl([original], path)
        line = path.read_text().splitlines()[0]
        restored = ProcessedItem.from_dict(json.loads(line))
        assert restored.id == original.id
        assert restored.fetch_date == original.fetch_date

    def test_creates_parent_directories(self, tmp_path):
        from src.models import write_processed_jsonl

        path = tmp_path / "data" / "processed" / "2026-05-02.jsonl"
        write_processed_jsonl([self._make_processed("d1")], path)
        assert path.exists()

    def test_empty_list_writes_empty_file(self, tmp_path):
        from src.models import write_processed_jsonl

        path = tmp_path / "empty.jsonl"
        write_processed_jsonl([], path)
        assert path.exists()
        assert path.read_text().strip() == ""


# ── read_processed_jsonl ─────────────────────────────────────────────────────


class TestReadProcessedJsonl:
    def _make_processed(self, id_: str) -> ProcessedItem:
        return ProcessedItem(
            id=id_,
            title="T",
            url="https://example.com",
            source_name="S",
            source_type="rss",
            source_class="practitioner",
            author="",
            published=None,
            has_code=False,
            evidence_type="unknown",
            fetch_date="2026-05-02",
            cleaned_content="cleaned",
        )

    def test_reads_items_written_by_write(self, tmp_path):
        from src.models import read_processed_jsonl, write_processed_jsonl

        items = [self._make_processed("r1"), self._make_processed("r2")]
        path = tmp_path / "p.jsonl"
        write_processed_jsonl(items, path)
        result = read_processed_jsonl(path)
        assert len(result) == 2
        assert {r.id for r in result} == {"r1", "r2"}

    def test_returns_empty_list_for_missing_file(self, tmp_path):
        from src.models import read_processed_jsonl

        assert read_processed_jsonl(tmp_path / "nope.jsonl") == []

    def test_skips_malformed_lines(self, tmp_path):
        from src.models import read_processed_jsonl

        good = json.dumps(self._make_processed("g2").to_dict())
        path = tmp_path / "mixed.jsonl"
        path.write_text(f"{good}\nnot-json\n")
        result = read_processed_jsonl(path)
        assert len(result) == 1
        assert result[0].id == "g2"
