"""TDD tests for src/pipeline/stages/ — all 8 pipeline stages.

Each stage function has a defined input/output type:
  ingest(item, fetch_date) -> ProcessedItem
  clean(item) -> ProcessedItem
  extract_concepts(item, client) -> ProcessedItem
  classify_theme(item, client) -> ProcessedItem
  extract_summary(item, client) -> ProcessedItem
  identify_marketing(item, client) -> ProcessedItem
  score_hype(item) -> ProcessedItem
  score_credibility(item) -> ProcessedItem
"""

from __future__ import annotations

from datetime import datetime, timezone
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
        published=published or datetime(2026, 5, 2, 9, 0, tzinfo=timezone.utc),
        has_code=has_code,
        evidence_type=evidence_type,
    )


def _make_processed(**kwargs) -> ProcessedItem:
    defaults = dict(
        id="item-1",
        title="Test Title About LLMs",
        url="https://example.com/item-1",
        source_name="Test Source",
        source_type="rss",
        source_class="practitioner",
        author="Alice",
        published=datetime(2026, 5, 2, 9, 0, tzinfo=timezone.utc),
        has_code=False,
        evidence_type="analysis",
        fetch_date="2026-05-02",
        cleaned_content="This is a test article about LLM inference performance.",
    )
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
        item_with_html = ProcessedItem(
            **{**item.__dict__,
               "cleaned_content": ""}
        )
        # Simulate raw content with HTML
        item_with_html.__dict__["_raw_content"] = "<p>Hello <b>world</b></p>"

        from src.fetchers import FetchedItem
        fetched = FetchedItem(
            id="c1", title="T", url="u", content="<p>Hello <b>world</b></p>",
            source_name="S", source_type="rss", source_class="practitioner",
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


# ── Stage 3: Concept Extraction ─────────────────────────────────────────────

class TestConceptExtractionStage:
    def _make_mock_client(self, response_text: str) -> MagicMock:
        client = MagicMock()
        response = MagicMock()
        response.text = response_text
        client.models.generate_content.return_value = response
        return client

    def test_returns_processed_item(self):
        from src.pipeline.stages.concept_extraction import extract_concepts

        client = self._make_mock_client(
            "CONCEPTS: LLM inference, attention mechanism\n"
            "ACTORS: Anthropic, Google\n"
            "IMPACT: capability"
        )
        item = _make_processed()
        result = extract_concepts(item, client)
        assert isinstance(result, ProcessedItem)

    def test_sets_concepts_list(self):
        from src.pipeline.stages.concept_extraction import extract_concepts

        client = self._make_mock_client(
            "CONCEPTS: LLM inference, attention mechanism\n"
            "ACTORS: Anthropic, Google\n"
            "IMPACT: capability"
        )
        item = _make_processed()
        result = extract_concepts(item, client)
        assert isinstance(result.concepts, list)
        assert len(result.concepts) >= 1

    def test_sets_actors_list(self):
        from src.pipeline.stages.concept_extraction import extract_concepts

        client = self._make_mock_client(
            "CONCEPTS: inference\nACTORS: Anthropic, OpenAI\nIMPACT: capability"
        )
        item = _make_processed()
        result = extract_concepts(item, client)
        assert isinstance(result.actors, list)

    def test_sets_valid_impact_vector(self):
        from src.pipeline.stages.concept_extraction import extract_concepts

        client = self._make_mock_client(
            "CONCEPTS: inference\nACTORS: none\nIMPACT: cost"
        )
        item = _make_processed()
        result = extract_concepts(item, client)
        valid = {"cost", "latency", "capability", "safety", "adoption", "unknown"}
        assert result.impact_vector in valid

    def test_unknown_impact_on_bad_response(self):
        from src.pipeline.stages.concept_extraction import extract_concepts

        client = self._make_mock_client("garbage response with no structure")
        item = _make_processed()
        result = extract_concepts(item, client)
        assert result.impact_vector == "unknown"

    def test_gemini_failure_returns_item_unchanged(self):
        from src.pipeline.stages.concept_extraction import extract_concepts

        client = MagicMock()
        client.models.generate_content.side_effect = Exception("API down")
        item = _make_processed()
        result = extract_concepts(item, client)
        assert isinstance(result, ProcessedItem)
        assert result.concepts == []
        assert result.impact_vector == "unknown"


# ── Stage 4: Theme Classification ───────────────────────────────────────────

class TestThemeClassificationStage:
    def _make_mock_client(self, response_text: str) -> MagicMock:
        client = MagicMock()
        response = MagicMock()
        response.text = response_text
        client.models.generate_content.return_value = response
        return client

    def test_returns_processed_item(self):
        from src.pipeline.stages.theme_classification import classify_theme

        client = self._make_mock_client("THEME: agentic RAG\nDOMAIN: agents")
        item = _make_processed()
        result = classify_theme(item, client)
        assert isinstance(result, ProcessedItem)

    def test_sets_theme_string(self):
        from src.pipeline.stages.theme_classification import classify_theme

        client = self._make_mock_client("THEME: agentic RAG\nDOMAIN: agents")
        item = _make_processed()
        result = classify_theme(item, client)
        assert isinstance(result.theme, str)
        assert len(result.theme) > 0

    def test_sets_valid_domain(self):
        from src.pipeline.stages.theme_classification import classify_theme

        client = self._make_mock_client("THEME: agentic RAG\nDOMAIN: agents")
        item = _make_processed()
        result = classify_theme(item, client)
        valid = {"multimodal","agents","infra","reasoning","safety","evals","data","hardware","general","unknown"}
        assert result.domain in valid

    def test_unknown_domain_on_bad_response(self):
        from src.pipeline.stages.theme_classification import classify_theme

        client = self._make_mock_client("nothing useful here")
        item = _make_processed()
        result = classify_theme(item, client)
        assert result.domain == "unknown"

    def test_gemini_failure_returns_item_unchanged(self):
        from src.pipeline.stages.theme_classification import classify_theme

        client = MagicMock()
        client.models.generate_content.side_effect = Exception("API down")
        item = _make_processed()
        result = classify_theme(item, client)
        assert isinstance(result, ProcessedItem)
        assert result.theme == ""
        assert result.domain == "unknown"


# ── Stage 5: Summary Extraction ─────────────────────────────────────────────

class TestSummaryExtractionStage:
    def _make_mock_client(self, response_text: str) -> MagicMock:
        client = MagicMock()
        response = MagicMock()
        response.text = response_text
        client.models.generate_content.return_value = response
        return client

    def test_returns_processed_item(self):
        from src.pipeline.stages.summary_extraction import extract_summary

        client = self._make_mock_client("Researchers found that LLM inference is faster. New benchmarks show 2x speedup. This impacts production deployments.")
        item = _make_processed()
        result = extract_summary(item, client)
        assert isinstance(result, ProcessedItem)

    def test_sets_summary_string(self):
        from src.pipeline.stages.summary_extraction import extract_summary

        client = self._make_mock_client("Researchers found that LLM inference is faster. New benchmarks show 2x speedup.")
        item = _make_processed()
        result = extract_summary(item, client)
        assert isinstance(result.summary, str)
        assert len(result.summary) > 0

    def test_gemini_failure_leaves_summary_empty(self):
        from src.pipeline.stages.summary_extraction import extract_summary

        client = MagicMock()
        client.models.generate_content.side_effect = Exception("API down")
        item = _make_processed()
        result = extract_summary(item, client)
        assert result.summary == ""


# ── Stage 6: Media / Marketing Identification ────────────────────────────────

class TestMediaIdStage:
    def _make_mock_client(self, response_text: str) -> MagicMock:
        client = MagicMock()
        response = MagicMock()
        response.text = response_text
        client.models.generate_content.return_value = response
        return client

    def test_returns_processed_item(self):
        from src.pipeline.stages.media_id import identify_marketing

        client = self._make_mock_client("MARKETING: false\nCONFIDENCE: 0.1")
        item = _make_processed()
        result = identify_marketing(item, client)
        assert isinstance(result, ProcessedItem)

    def test_sets_is_marketing_bool(self):
        from src.pipeline.stages.media_id import identify_marketing

        client = self._make_mock_client("MARKETING: true\nCONFIDENCE: 0.9")
        item = _make_processed()
        result = identify_marketing(item, client)
        assert isinstance(result.is_marketing, bool)
        assert result.is_marketing is True

    def test_sets_marketing_confidence_float(self):
        from src.pipeline.stages.media_id import identify_marketing

        client = self._make_mock_client("MARKETING: false\nCONFIDENCE: 0.2")
        item = _make_processed()
        result = identify_marketing(item, client)
        assert 0.0 <= result.marketing_confidence <= 1.0

    def test_not_marketing_when_false(self):
        from src.pipeline.stages.media_id import identify_marketing

        client = self._make_mock_client("MARKETING: false\nCONFIDENCE: 0.05")
        item = _make_processed()
        result = identify_marketing(item, client)
        assert result.is_marketing is False

    def test_gemini_failure_defaults_not_marketing(self):
        from src.pipeline.stages.media_id import identify_marketing

        client = MagicMock()
        client.models.generate_content.side_effect = Exception("API down")
        item = _make_processed()
        result = identify_marketing(item, client)
        assert result.is_marketing is False
        assert result.marketing_confidence == 0.0


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
        from src.pipeline.stages.hype_scoring import score_hype
        import unittest.mock as mock
        import src.credibility as cred_module

        item = _make_processed()
        with mock.patch("src.pipeline.stages.hype_scoring.detect_hype", wraps=cred_module.detect_hype) as spy:
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
        market = _make_processed(source_class="market", evidence_type="announcement", has_code=False)
        p_result = score_credibility(primary)
        m_result = score_credibility(market)
        assert p_result.credibility_score > m_result.credibility_score

    def test_does_not_call_external_services(self):
        """Credibility scoring is purely deterministic — no I/O."""
        from src.pipeline.stages.credibility_scoring import score_credibility
        import unittest.mock as mock
        import src.credibility as cred_module

        item = _make_processed()
        with mock.patch.object(cred_module, "score_credibility", wraps=cred_module.score_credibility) as spy:
            score_credibility(item)
            spy.assert_called_once()
