"""Tests for src/themes.py — synonym normalization and clustering (Epic 13, slice 13.4)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from google.genai.errors import ClientError

from src.models import CanonicalRecord
from src.themes import (
    DOMAIN_TAXONOMY,
    build_graph_edges,
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
        """When Gemini call fails (after SDK-internal retries), cluster_themes returns safe defaults."""
        records = _make_records("Multi-agent coordination", "RAG with tools")

        with patch("src.themes.genai.Client") as mock_client, patch("src.retry.time.sleep"):
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

    def test_api_failure_maps_to_domain_fallback(self):
        """When the Gemini call fails, each item falls back to its domain as the theme."""
        records = [
            CanonicalRecord(
                url="https://example.com/0", title="x", source_class="practitioner", domain="agents"
            ),
            CanonicalRecord(
                url="https://example.com/1", title="y", source_class="practitioner", domain="infra"
            ),
        ]

        with patch("src.themes.genai.Client") as mock_client, patch("src.retry.time.sleep"):
            mock_instance = mock_client.return_value
            mock_instance.models.generate_content.side_effect = RuntimeError("quota exceeded")
            url_to_theme, defs, rels = cluster_themes(records, [])

        assert url_to_theme["https://example.com/0"] != ""
        assert url_to_theme["https://example.com/1"] != ""
        assert defs == []
        assert rels == []

    def test_client_created_without_http_retry_options(self):
        """Gemini client is created without SDK HttpRetryOptions."""
        records = _make_records("inference cost")

        with patch("src.themes.genai.Client") as mock_client, patch("src.retry.time.sleep"):
            mock_instance = mock_client.return_value
            mock_instance.models.generate_content.side_effect = Exception("fail")
            cluster_themes(records, [])

        call_kwargs = mock_client.call_args.kwargs
        http_options = call_kwargs.get("http_options")
        # An HttpOptions is injected for header capture, but SDK-level retry must not be set.
        assert http_options is not None
        assert http_options.retry_options is None

    def test_retries_on_client_error_429(self):
        """cluster_themes retries 429 ClientError and sleeps for RetryInfo.retryDelay."""
        records = _make_records("inference cost")
        err = ClientError(429, {"error": "quota exceeded"})
        err.details = [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "39s"}]
        response = MagicMock()
        response.text = json.dumps(
            {
                "assignments": [
                    {
                        "url": "https://example.com/0",
                        "theme": "Inference Cost Reduction",
                        "domain": "infra",
                    }
                ],
                "theme_definitions": [],
                "relationships": [],
            }
        )

        with (
            patch("src.themes.genai.Client") as mock_client,
            patch("src.retry.time.sleep") as retry_sleep,
        ):
            mock_instance = mock_client.return_value
            mock_instance.models.generate_content.side_effect = [err, response]
            url_to_theme, defs, rels = cluster_themes(records, [])

        assert url_to_theme["https://example.com/0"] == "Inference Cost Reduction"
        assert defs == []
        assert rels == []
        assert mock_instance.models.generate_content.call_count == 2
        retry_sleep.assert_called_once_with(39.0)


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


# ---------------------------------------------------------------------------
# build_graph_edges
# ---------------------------------------------------------------------------


class TestBuildGraphEdges:
    def test_empty_input_returns_empty_list(self):
        assert build_graph_edges([]) == []

    def test_converts_relationship_dict_to_graph_edge(self):
        rels = [{"source": "Theme A", "target": "Theme B", "rel_type": "causal", "weight": 2}]
        edges = build_graph_edges(rels)
        assert len(edges) == 1
        assert edges[0].source == "Theme A"
        assert edges[0].target == "Theme B"
        assert edges[0].rel_type == "causal"
        assert edges[0].weight == 2.0

    def test_deduplicates_identical_edges(self):
        rel = {"source": "Theme A", "target": "Theme B", "rel_type": "causal", "weight": 1}
        edges = build_graph_edges([rel, rel, rel])
        assert len(edges) == 1

    def test_same_source_and_target_different_rel_type_kept_separate(self):
        rels = [
            {"source": "Theme A", "target": "Theme B", "rel_type": "causal", "weight": 1},
            {"source": "Theme A", "target": "Theme B", "rel_type": "competitive", "weight": 1},
        ]
        edges = build_graph_edges(rels)
        assert len(edges) == 2

    def test_self_referential_edges_skipped(self):
        rels = [{"source": "Theme A", "target": "Theme A", "rel_type": "causal", "weight": 1}]
        edges = build_graph_edges(rels)
        assert edges == []

    def test_edges_with_missing_source_or_target_skipped(self):
        rels = [
            {"source": "", "target": "Theme B", "rel_type": "causal", "weight": 1},
            {"source": "Theme A", "target": "", "rel_type": "causal", "weight": 1},
            {"source": "Theme A", "target": "Theme B", "rel_type": "causal", "weight": 1},
        ]
        edges = build_graph_edges(rels)
        assert len(edges) == 1
        assert edges[0].source == "Theme A"

    def test_default_weight_is_one(self):
        rels = [{"source": "Theme A", "target": "Theme B", "rel_type": "causal"}]
        edges = build_graph_edges(rels)
        assert edges[0].weight == 1.0

    def test_default_rel_type_is_causal(self):
        rels = [{"source": "Theme A", "target": "Theme B"}]
        edges = build_graph_edges(rels)
        assert edges[0].rel_type == "causal"

    def test_multiple_distinct_edges_all_returned(self):
        rels = [
            {
                "source": "Inference Cost Reduction",
                "target": "Agent Tool Use",
                "rel_type": "causal",
                "weight": 1,
            },
            {
                "source": "Agent Tool Use",
                "target": "Multi-Agent Systems",
                "rel_type": "compositional",
                "weight": 2,
            },
            {
                "source": "Inference Cost Reduction",
                "target": "Multi-Agent Systems",
                "rel_type": "causal",
                "weight": 1,
            },
        ]
        edges = build_graph_edges(rels)
        assert len(edges) == 3
