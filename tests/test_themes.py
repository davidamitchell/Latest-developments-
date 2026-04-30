"""Tests for src/themes.py — synonym normalization and clustering (Epic 13, slice 13.4)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from src.models import CanonicalRecord
from src.themes import (
    DOMAIN_TAXONOMY,
    cluster_themes,
    normalize_theme_name,
)

# ---------------------------------------------------------------------------
# normalize_theme_name — idempotency
# ---------------------------------------------------------------------------


class TestNormalizeThemeName:
    def test_idempotent_on_canonical_form(self):
        """Normalizing an already-normalized name returns the same value."""
        canonical = normalize_theme_name("Agent Tool Use")
        assert normalize_theme_name(canonical) == canonical

    def test_idempotent_on_multiple_passes(self):
        """Three passes should produce the same result as two."""
        raw = "tool use"
        once = normalize_theme_name(raw)
        twice = normalize_theme_name(once)
        three = normalize_theme_name(twice)
        assert once == twice == three

    def test_synonym_collapse_function_calling(self):
        assert normalize_theme_name("function calling") == "Agent Tool Use"

    def test_synonym_collapse_tool_calling(self):
        assert normalize_theme_name("tool calling") == "Agent Tool Use"

    def test_synonym_collapse_rag(self):
        name = normalize_theme_name("rag")
        assert name == "Retrieval-Augmented Generation"

    def test_synonym_collapse_finetuning(self):
        assert normalize_theme_name("finetuning") == "Fine-Tuning & Adaptation"

    def test_synonym_collapse_safety(self):
        assert normalize_theme_name("safety") == "AI Safety & Alignment"

    def test_acronym_fix_ai(self):
        """Title case should produce 'AI', not 'Ai'."""
        name = normalize_theme_name("ai workforce impact")
        assert "AI" in name
        assert "Ai " not in name

    def test_acronym_fix_llm(self):
        name = normalize_theme_name("llm capabilities")
        assert "LLM" in name
        assert "Llm" not in name

    def test_unknown_term_title_cased(self):
        # Use a phrase with no overlap with any synonym substring
        name = normalize_theme_name("Sparse Expert Routing")
        assert name == "Sparse Expert Routing"

    def test_empty_string_safe(self):
        result = normalize_theme_name("")
        assert isinstance(result, str)

    def test_whitespace_stripped(self):
        assert normalize_theme_name("  benchmark  ") == "Benchmarks & Evals"

    def test_benchmark_synonym(self):
        assert normalize_theme_name("benchmark") == "Benchmarks & Evals"
        assert normalize_theme_name("evaluation") == "Benchmarks & Evals"

    def test_multimodal_collapse(self):
        assert normalize_theme_name("multimodal") == "Multimodal Models"

    def test_longest_match_wins(self):
        """'local llm inference' is more specific than 'local llm'."""
        result = normalize_theme_name("local llm inference")
        assert result == "Local LLM Inference"


# ---------------------------------------------------------------------------
# cluster_themes — graceful API failure fallback
# ---------------------------------------------------------------------------


def _make_records(*titles: str) -> list[CanonicalRecord]:
    return [
        CanonicalRecord(
            url=f"https://example.com/{i}",
            title=title,
            source_class="practitioner",
        )
        for i, title in enumerate(titles)
    ]


class TestClusterThemes:
    def test_empty_records_returns_empty(self):
        url_to_theme, defs, rels = cluster_themes([], [])
        assert url_to_theme == {}
        assert defs == []
        assert rels == []

    def test_api_failure_returns_fallback(self):
        """When Gemini call fails, cluster_themes returns empty assignments gracefully."""
        records = _make_records("Multi-agent coordination", "RAG with tools")

        with patch("src.themes.genai.Client") as mock_client:
            mock_instance = mock_client.return_value
            mock_instance.models.generate_content.side_effect = Exception("API down")

            url_to_theme, defs, rels = cluster_themes(records, [])

        # Fallback: should not raise; return empty or safe defaults
        assert isinstance(url_to_theme, dict)
        assert isinstance(defs, list)
        assert isinstance(rels, list)

    def test_json_decode_failure_returns_fallback(self):
        """When Gemini returns invalid JSON, cluster_themes falls back gracefully."""
        records = _make_records("Agent orchestration systems")

        with patch("src.themes.genai.Client") as mock_client:
            mock_instance = mock_client.return_value
            mock_response = MagicMock()
            mock_response.text = "not valid json at all {{{"
            mock_instance.models.generate_content.return_value = mock_response

            url_to_theme, defs, rels = cluster_themes(records, [])

        assert isinstance(url_to_theme, dict)
        assert isinstance(defs, list)
        assert isinstance(rels, list)

    def test_valid_gemini_response_parsed(self):
        """When Gemini returns valid JSON, assignments and definitions are extracted."""
        records = _make_records("Inference cost optimization", "LoRA fine-tuning")

        gemini_payload = {
            "assignments": [
                {
                    "url": "https://example.com/0",
                    "theme": "Inference Cost Reduction",
                    "domain": "infra",
                },
                {
                    "url": "https://example.com/1",
                    "theme": "Fine-Tuning & Adaptation",
                    "domain": "general",
                },
            ],
            "theme_definitions": [
                {
                    "theme": "Inference Cost Reduction",
                    "domain": "infra",
                    "definition": "Reducing the compute cost of running LLMs at inference time.",
                },
                {
                    "theme": "Fine-Tuning & Adaptation",
                    "domain": "general",
                    "definition": "Adapting pre-trained models to specific tasks.",
                },
            ],
            "relationships": [
                {
                    "source": "Inference Cost Reduction",
                    "target": "Fine-Tuning & Adaptation",
                    "rel_type": "causal",
                    "weight": 1,
                },
            ],
        }

        with patch("src.themes.genai.Client") as mock_client:
            mock_instance = mock_client.return_value
            mock_response = MagicMock()
            mock_response.text = json.dumps(gemini_payload)
            mock_instance.models.generate_content.return_value = mock_response

            url_to_theme, defs, rels = cluster_themes(records, [])

        assert "https://example.com/0" in url_to_theme
        assert url_to_theme["https://example.com/0"] == "Inference Cost Reduction"
        assert len(defs) == 2
        assert any(d["theme"] == "Inference Cost Reduction" for d in defs)
        assert len(rels) == 1
        assert rels[0]["rel_type"] == "causal"

    def test_valid_response_with_markdown_fences(self):
        """Markdown code fences in Gemini response are stripped before parsing."""
        records = _make_records("New benchmark results")

        payload = {
            "assignments": [
                {"url": "https://example.com/0", "theme": "Benchmarks & Evals", "domain": "evals"}
            ],
            "theme_definitions": [
                {
                    "theme": "Benchmarks & Evals",
                    "domain": "evals",
                    "definition": "Testing model performance.",
                }
            ],
            "relationships": [],
        }
        fenced = f"```json\n{json.dumps(payload)}\n```"

        with patch("src.themes.genai.Client") as mock_client:
            mock_instance = mock_client.return_value
            mock_response = MagicMock()
            mock_response.text = fenced
            mock_instance.models.generate_content.return_value = mock_response

            url_to_theme, defs, rels = cluster_themes(records, [])

        assert url_to_theme.get("https://example.com/0") == "Benchmarks & Evals"


# ---------------------------------------------------------------------------
# DOMAIN_TAXONOMY completeness
# ---------------------------------------------------------------------------


class TestDomainTaxonomy:
    def test_taxonomy_has_expected_entries(self):
        expected = {
            "multimodal",
            "agents",
            "infra",
            "reasoning",
            "safety",
            "evals",
            "data",
            "hardware",
            "general",
        }
        assert set(DOMAIN_TAXONOMY) >= expected

    def test_taxonomy_entries_are_lowercase(self):
        assert all(d == d.lower() for d in DOMAIN_TAXONOMY)
