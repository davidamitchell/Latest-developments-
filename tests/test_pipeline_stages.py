"""TDD tests for src/pipeline/stages/ — all 8 pipeline stages.

Each stage function has a defined input/output type:
  ingest(item, fetch_date) -> ProcessedItem
  clean(item, raw_content) -> ProcessedItem
  enrich(item, client) -> (ProcessedItem, bool)
  score_hype(item) -> ProcessedItem
  score_credibility(item) -> ProcessedItem
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from src.fetchers import FetchedItem
from src.models import ProcessedItem


def _make_fetched(
    id_: str = "item-1",
    source_class: str = "practitioner",
    evidence_type: str = "analysis",
    has_code: bool = False,
    published: datetime | None = None,
) -> FetchedItem:
    return FetchedItem(
        id=id_,
        title="Test Title About LLMs",
        url=f"https://example.com/{id_}",
        content="<p>This is a test article about <b>LLM inference</b> performance.</p>",
        source_name="Test Source",
        source_type="rss",
        source_class=source_class,
        author="Alice",
        published=published or datetime(2026, 5, 2, 9, 0, tzinfo=UTC),
        has_code=has_code,
        evidence_type=evidence_type,
    )


def _make_processed(**kwargs) -> ProcessedItem:
    defaults = {
        "id": "item-1",
        "title": "Test Title About LLMs",
        "url": "https://example.com/item-1",
        "source_name": "Test Source",
        "source_type": "rss",
        "source_class": "practitioner",
        "author": "Alice",
        "published": datetime(2026, 5, 2, 9, 0, tzinfo=UTC),
        "has_code": False,
        "evidence_type": "analysis",
        "fetch_date": "2026-05-02",
        "cleaned_content": "This is a test article about LLM inference performance.",
    }
    defaults.update(kwargs)
    return ProcessedItem(**defaults)


# ── Stage 1: Ingest ─────────────────────────────────────────────────────────


class TestIngestStage:
    def test_returns_processed_item(self):
        from src.pipeline.stages.ingest import ingest

        fetched = _make_fetched()
        result = ingest(fetched, fetch_date="2026-05-02")
        assert isinstance(result, ProcessedItem)

    def test_copies_all_fetched_fields(self):
        from src.pipeline.stages.ingest import ingest

        fetched = _make_fetched()
        result = ingest(fetched, fetch_date="2026-05-02")
        assert result.id == fetched.id
        assert result.title == fetched.title
        assert result.url == fetched.url
        assert result.source_name == fetched.source_name
        assert result.source_type == fetched.source_type
        assert result.source_class == fetched.source_class
        assert result.author == fetched.author
        assert result.published == fetched.published
        assert result.has_code == fetched.has_code
        assert result.evidence_type == fetched.evidence_type

    def test_sets_fetch_date(self):
        from src.pipeline.stages.ingest import ingest

        fetched = _make_fetched()
        result = ingest(fetched, fetch_date="2026-05-02")
        assert result.fetch_date == "2026-05-02"

    def test_content_preserved_for_downstream(self):
        """The original content must be accessible; clean stage adds cleaned_content."""
        from src.pipeline.stages.ingest import ingest

        fetched = _make_fetched()
        result = ingest(fetched, fetch_date="2026-05-02")
        # cleaned_content starts empty — clean stage fills it
        assert result.cleaned_content == ""


# ── Stage 2: Clean ──────────────────────────────────────────────────────────


class TestCleanStage:
    def test_strips_html_tags(self):
        from src.pipeline.stages.clean import clean

        item = _make_processed(cleaned_content="")
        item_with_html = ProcessedItem(**{**item.__dict__, "cleaned_content": ""})
        # Simulate raw content with HTML
        item_with_html.__dict__["_raw_content"] = "<p>Hello <b>world</b></p>"

        from src.fetchers import FetchedItem

        fetched = FetchedItem(
            id="c1",
            title="T",
            url="u",
            content="<p>Hello <b>world</b></p>",
            source_name="S",
            source_type="rss",
            source_class="practitioner",
        )
        from src.pipeline.stages.ingest import ingest

        ingested = ingest(fetched, "2026-05-02")
        # Clean stage reads from the original FetchedItem content stored during ingest
        result = clean(ingested, raw_content="<p>Hello <b>world</b></p>")
        assert "<" not in result.cleaned_content
        assert "Hello" in result.cleaned_content
        assert "world" in result.cleaned_content

    def test_collapses_whitespace(self):
        from src.pipeline.stages.clean import clean

        item = _make_processed(cleaned_content="")
        result = clean(item, raw_content="  Hello   \n\n  world  \t\t end  ")
        assert "  " not in result.cleaned_content
        assert result.cleaned_content == result.cleaned_content.strip()

    def test_returns_processed_item(self):
        from src.pipeline.stages.clean import clean

        item = _make_processed(cleaned_content="")
        result = clean(item, raw_content="plain text")
        assert isinstance(result, ProcessedItem)

    def test_empty_content_yields_empty_string(self):
        from src.pipeline.stages.clean import clean

        item = _make_processed(cleaned_content="")
        result = clean(item, raw_content="")
        assert result.cleaned_content == ""


# ── Stage 3-6: _parse() — direct partition tests ─────────────────────────────
# _parse() is the core logic unit of enrich.py. These tests call it with real
# string inputs (no mocks) and cover all specified partitions.


class TestParse:
    """Partition tests for enrich._parse() — the primary logic unit."""

    def _parse(self, text: str) -> dict:
        from src.pipeline.stages.enrich import _parse

        return _parse(text, "test-item")

    _FULL_RESPONSE = (
        "CONCEPTS: LLM inference, attention mechanism\n"
        "ACTORS: Anthropic, Google\n"
        "IMPACT: capability\n"
        "THEME: inference scaling\n"
        "DOMAIN: infra\n"
        "SUMMARY: Researchers found faster inference. Benchmarks show 2x speedup.\n"
        "MARKETING: false\n"
        "CONFIDENCE: 0.1"
    )

    # ── Typical value ─────────────────────────────────────────────────────────

    def test_typical_full_response_parses_all_fields(self):
        result = self._parse(self._FULL_RESPONSE)
        assert result["concepts"] == ["LLM inference", "attention mechanism"]
        assert result["actors"] == ["Anthropic", "Google"]
        assert result["impact_vector"] == "capability"
        assert result["theme"] == "inference scaling"
        assert result["domain"] == "infra"
        assert "Researchers" in result["summary"]
        assert result["is_marketing"] is False
        assert result["marketing_confidence"] == pytest.approx(0.1)

    # ── Empty / missing fields ────────────────────────────────────────────────

    def test_empty_response_returns_all_defaults(self):
        result = self._parse("")
        assert result["concepts"] == []
        assert result["actors"] == []
        assert result["impact_vector"] == "unknown"
        assert result["theme"] == ""
        assert result["domain"] == "unknown"
        assert result["summary"] == ""
        assert result["is_marketing"] is False
        assert result["marketing_confidence"] == 0.0

    def test_missing_individual_fields_fall_back_to_defaults(self):
        result = self._parse("IMPACT: cost")
        assert result["impact_vector"] == "cost"
        assert result["concepts"] == []
        assert result["theme"] == ""

    # ── IMPACT partition ──────────────────────────────────────────────────────

    def test_all_valid_impact_values_accepted(self):
        valid = {"cost", "latency", "capability", "safety", "adoption", "unknown"}
        for v in valid:
            result = self._parse(f"IMPACT: {v}")
            assert result["impact_vector"] == v

    def test_unrecognised_impact_defaults_to_unknown(self):
        result = self._parse("IMPACT: revolutionary")
        assert result["impact_vector"] == "unknown"

    def test_impact_case_insensitive(self):
        result = self._parse("IMPACT: CAPABILITY")
        assert result["impact_vector"] == "capability"

    # ── CONFIDENCE partition ──────────────────────────────────────────────────

    def test_confidence_non_float_string_defaults_to_zero(self):
        result = self._parse("CONFIDENCE: high")
        assert result["marketing_confidence"] == 0.0

    def test_confidence_below_zero_clamped_to_zero(self):
        result = self._parse("CONFIDENCE: -0.5")
        assert result["marketing_confidence"] == 0.0

    def test_confidence_above_one_clamped_to_one(self):
        result = self._parse("CONFIDENCE: 1.5")
        assert result["marketing_confidence"] == 1.0

    def test_confidence_boundary_values_accepted(self):
        assert self._parse("CONFIDENCE: 0.0")["marketing_confidence"] == 0.0
        assert self._parse("CONFIDENCE: 1.0")["marketing_confidence"] == 1.0

    # ── ACTORS: none ─────────────────────────────────────────────────────────

    def test_actors_none_string_produces_empty_list(self):
        result = self._parse("ACTORS: none")
        assert result["actors"] == []

    def test_actors_none_case_insensitive(self):
        result = self._parse("ACTORS: None")
        assert result["actors"] == []

    def test_actors_mixed_with_none_filters_none(self):
        result = self._parse("ACTORS: Anthropic, none, Google")
        assert "none" not in [a.lower() for a in result["actors"]]
        assert "Anthropic" in result["actors"]

    # ── SUMMARY with inner colon ──────────────────────────────────────────────

    def test_summary_with_colon_mid_sentence_not_split(self):
        result = self._parse("SUMMARY: The model achieves 90%: a new record for this benchmark.")
        assert "90%" in result["summary"]
        assert "new record" in result["summary"]

    # ── CONCEPTS boundary ────────────────────────────────────────────────────

    def test_concepts_with_six_items_all_parsed(self):
        """Behaviour for >5 items: all are parsed; the system prompt constrains the model."""
        result = self._parse("CONCEPTS: a, b, c, d, e, f")
        assert len(result["concepts"]) == 6

    def test_concepts_single_item(self):
        result = self._parse("CONCEPTS: transformer")
        assert result["concepts"] == ["transformer"]

    def test_concepts_none_string_produces_empty_list(self):
        result = self._parse("CONCEPTS: none")
        assert result["concepts"] == []


# ── Stage 7: Hype Scoring ────────────────────────────────────────────────────


class TestHypeScoringStage:
    def test_returns_processed_item(self):
        from src.pipeline.stages.hype_scoring import score_hype

        item = _make_processed()
        result = score_hype(item)
        assert isinstance(result, ProcessedItem)

    def test_hype_risk_in_range(self):
        from src.pipeline.stages.hype_scoring import score_hype

        item = _make_processed()
        result = score_hype(item)
        assert 0.0 <= result.hype_risk <= 1.0

    def test_operator_announcement_has_higher_hype(self):
        from src.pipeline.stages.hype_scoring import score_hype

        operator_item = _make_processed(source_class="operator", evidence_type="announcement")
        practitioner_item = _make_processed(source_class="practitioner", evidence_type="experiment")
        op_result = score_hype(operator_item)
        pr_result = score_hype(practitioner_item)
        assert op_result.hype_risk > pr_result.hype_risk

    def test_experiment_evidence_has_low_hype(self):
        from src.pipeline.stages.hype_scoring import score_hype

        item = _make_processed(evidence_type="experiment", source_class="primary")
        result = score_hype(item)
        assert result.hype_risk < 0.4

    def test_does_not_call_external_services(self):
        """Hype scoring delegates to src.credibility.detect_hype — no I/O."""
        import unittest.mock as mock

        import src.credibility as cred_module
        from src.pipeline.stages.hype_scoring import score_hype

        item = _make_processed()
        with mock.patch(
            "src.pipeline.stages.hype_scoring.detect_hype", wraps=cred_module.detect_hype
        ) as spy:
            score_hype(item)
            spy.assert_called_once()


# ── Stage 8: Credibility Scoring ─────────────────────────────────────────────


class TestCredibilityScoringStage:
    def test_returns_processed_item(self):
        from src.pipeline.stages.credibility_scoring import score_credibility

        item = _make_processed()
        result = score_credibility(item)
        assert isinstance(result, ProcessedItem)

    def test_credibility_score_in_range(self):
        from src.pipeline.stages.credibility_scoring import score_credibility

        item = _make_processed()
        result = score_credibility(item)
        assert 0.0 <= result.credibility_score <= 1.0

    def test_primary_with_code_has_high_credibility(self):
        from src.pipeline.stages.credibility_scoring import score_credibility

        item = _make_processed(source_class="primary", evidence_type="experiment", has_code=True)
        result = score_credibility(item)
        assert result.credibility_score >= 0.6

    def test_market_announcement_has_lower_credibility(self):
        from src.pipeline.stages.credibility_scoring import score_credibility

        primary = _make_processed(source_class="primary", evidence_type="experiment", has_code=True)
        market = _make_processed(
            source_class="market", evidence_type="announcement", has_code=False
        )
        p_result = score_credibility(primary)
        m_result = score_credibility(market)
        assert p_result.credibility_score > m_result.credibility_score

    def test_does_not_call_external_services(self):
        """Credibility scoring is purely deterministic — no I/O."""
        import unittest.mock as mock

        import src.credibility as cred_module
        from src.pipeline.stages.credibility_scoring import score_credibility

        item = _make_processed()
        with mock.patch.object(
            cred_module, "score_credibility", wraps=cred_module.score_credibility
        ) as spy:
            score_credibility(item)
            spy.assert_called_once()


# ── Enrich: success and failure behaviour ────────────────────────────────────


class TestEnrich:
    """Retry behaviour is delegated to caller-level with_backoff logic.
    These tests verify the parse/return contract and finish_reason handling."""

    def _make_item(self):
        return _make_processed()

    def _good_client(self):
        from google.genai.types import FinishReason

        client = MagicMock()
        resp = MagicMock()
        resp.text = (
            "CONCEPTS: LLM\nACTORS: none\nIMPACT: capability\n"
            "THEME: inference\nDOMAIN: infra\n"
            "SUMMARY: Sentence one. Sentence two.\nMARKETING: false\nCONFIDENCE: 0.1"
        )
        candidate = MagicMock()
        candidate.finish_reason = FinishReason.STOP
        resp.candidates = [candidate]
        client.models.generate_content.return_value = resp
        return client

    def test_success_returns_enriched_item_and_ok_true(self):
        from src.pipeline.stages.enrich import enrich

        item, ok = enrich(self._make_item(), self._good_client())
        assert ok is True
        assert item.theme == "inference"
        assert item.domain == "infra"
        assert item.impact_vector == "capability"

    def test_client_error_propagates(self):
        """ClientError (transport failure) propagates so with_backoff can retry."""
        from google.genai.errors import ClientError

        from src.pipeline.stages.enrich import enrich

        client = MagicMock()
        client.models.generate_content.side_effect = ClientError(429, {"error": "quota"})
        with pytest.raises(ClientError):
            enrich(self._make_item(), client)

    def test_server_error_propagates(self):
        """ServerError (5xx) propagates so with_backoff can retry."""
        from google.genai.errors import ServerError

        from src.pipeline.stages.enrich import enrich

        client = MagicMock()
        client.models.generate_content.side_effect = ServerError(503, {"error": "unavailable"})
        with pytest.raises(ServerError):
            enrich(self._make_item(), client)

    def test_programming_error_propagates(self):
        """AttributeError and other programming errors must not be swallowed."""
        from src.pipeline.stages.enrich import enrich

        client = MagicMock()
        client.models.generate_content.side_effect = AttributeError("bug")
        with pytest.raises(AttributeError):
            enrich(self._make_item(), client)

    def test_non_stop_finish_reason_returns_ok_false(self):
        """SAFETY/MAX_TOKENS finish reasons return ok=False; response.text is never accessed."""
        from google.genai.types import FinishReason

        from src.pipeline.stages.enrich import enrich

        client = MagicMock()
        resp = MagicMock()
        # Raise if .text is accessed — ensures enrich() does not call it
        type(resp).text = property(
            lambda self: (_ for _ in ()).throw(ValueError("must not access .text"))
        )
        candidate = MagicMock()
        candidate.finish_reason = FinishReason.SAFETY
        resp.candidates = [candidate]
        client.models.generate_content.return_value = resp
        item, ok = enrich(self._make_item(), client)
        assert ok is False

    def test_max_output_tokens_parameter_passed_to_config(self):
        """enrich() passes max_output_tokens to GenerateContentConfig."""
        from google.genai import types

        from src.pipeline.stages.enrich import enrich

        client = self._good_client()
        enrich(self._make_item(), client, max_output_tokens=256)
        call_kwargs = client.models.generate_content.call_args
        config_arg = call_kwargs.kwargs.get("config") or call_kwargs.args[2]
        assert isinstance(config_arg, types.GenerateContentConfig)
        assert config_arg.max_output_tokens == 256

    def test_thinking_disabled_in_config(self):
        """thinking_budget=0 must be set so thinking tokens don't consume the output budget.

        gemini-2.5-flash is a thinking model. Without thinking_budget=0, thinking
        tokens compete with max_output_tokens, truncating the structured response
        with finish_reason=MAX_TOKENS and leaving items unenriched.
        """
        from google.genai import types

        from src.pipeline.stages.enrich import enrich

        client = self._good_client()
        enrich(self._make_item(), client)
        call_kwargs = client.models.generate_content.call_args
        config_arg = call_kwargs.kwargs.get("config") or call_kwargs.args[2]
        assert isinstance(config_arg, types.GenerateContentConfig)
        assert config_arg.thinking_config is not None, (
            "thinking_config must be set to disable thinking for structured extraction"
        )
        assert config_arg.thinking_config.thinking_budget == 0, (
            "thinking_budget must be 0 to prevent token competition with max_output_tokens"
        )

    def test_max_tokens_finish_reason_returns_ok_false_with_warning(self):
        """MAX_TOKENS finish_reason returns ok=False.

        This is the failure mode when thinking tokens consume the output budget.
        Verifying it returns ok=False (not crashing) ensures the pipeline can
        continue rather than stalling on this item.
        """
        from google.genai.types import FinishReason

        from src.pipeline.stages.enrich import enrich

        client = MagicMock()
        resp = MagicMock()
        type(resp).text = property(
            lambda self: (_ for _ in ()).throw(
                ValueError("must not access .text on truncated response")
            )
        )
        candidate = MagicMock()
        candidate.finish_reason = FinishReason.MAX_TOKENS
        resp.candidates = [candidate]
        client.models.generate_content.return_value = resp
        item, ok = enrich(self._make_item(), client)
        assert ok is False
        assert item.theme == ""
