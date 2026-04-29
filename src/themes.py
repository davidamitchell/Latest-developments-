"""Theme clustering, normalization, and relationship graph extraction."""

from __future__ import annotations

import json
import logging
import os
import re
from collections import Counter

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from src.models import CanonicalRecord, GraphEdge, ThemeNode

logger = logging.getLogger(__name__)

# ── Canonical domain taxonomy ────────────────────────────────────────
DOMAIN_TAXONOMY: list[str] = [
    "multimodal", "agents", "infra", "reasoning",
    "safety", "evals", "data", "hardware", "general",
]

# Keyword → canonical theme name for fast normalization without an API call.
# These collapse common synonyms before Gemini sees the text.
_SYNONYM_MAP: dict[str, str] = {
    "tool use":         "Agent Tool Use",
    "function calling": "Agent Tool Use",
    "tool calling":     "Agent Tool Use",
    "function call":    "Agent Tool Use",
    "rag":              "Retrieval-Augmented Generation",
    "retrieval augmented": "Retrieval-Augmented Generation",
    "rlhf":             "RLHF & Alignment",
    "rlaif":            "RLHF & Alignment",
    "dpo":              "RLHF & Alignment",
    "inference cost":   "Inference Cost Reduction",
    "inference efficiency": "Inference Cost Reduction",
    "llm cost":         "Inference Cost Reduction",
    "agent reliability": "Agent Reliability",
    "multi-agent":      "Multi-Agent Systems",
    "multiagent":       "Multi-Agent Systems",
    "synthetic data":   "Synthetic Data Pipelines",
    "data synthesis":   "Synthetic Data Pipelines",
    "reasoning model":  "Long-Context Reasoning",
    "chain of thought": "Long-Context Reasoning",
    "long context":     "Long-Context Reasoning",
    "context length":   "Long-Context Reasoning",
    "fine-tuning":      "Fine-Tuning & Adaptation",
    "finetuning":       "Fine-Tuning & Adaptation",
    "lora":             "Fine-Tuning & Adaptation",
    "distillation":     "Model Distillation",
    "model compression": "Model Distillation",
    "quantization":     "Model Distillation",
    "benchmark":        "Benchmarks & Evals",
    "evaluation":       "Benchmarks & Evals",
    "leaderboard":      "Benchmarks & Evals",
    "safety":           "AI Safety & Alignment",
    "alignment":        "AI Safety & Alignment",
    "jailbreak":        "AI Safety & Alignment",
    "red team":         "AI Safety & Alignment",
    "multimodal":       "Multimodal Models",
    "vision language":  "Multimodal Models",
    "vla":              "Multimodal Models",
    "open source model": "Open-Source Models",
    "open weight":      "Open-Source Models",
    "open weights":     "Open-Source Models",
    "code generation":  "Code Generation",
    "coding model":     "Code Generation",
    "ai coding":        "Code Generation",
}


def normalize_theme_name(raw: str) -> str:
    """Apply synonym map to collapse common rebranding variants."""
    lower = raw.lower().strip()
    for pattern, canonical in _SYNONYM_MAP.items():
        if pattern in lower:
            return canonical
    return raw.strip().title()


def _build_clustering_prompt(records: list[CanonicalRecord], existing_themes: list[str]) -> str:
    items_block = "\n".join(
        f"- URL: {r.url}\n  Claim: {r.claim or r.title}\n  Domain: {r.domain}\n  Evidence: {r.evidence_type}"
        for r in records[:60]  # cap to keep token budget bounded
    )
    existing_block = "\n".join(f"- {t}" for t in existing_themes) if existing_themes else "None yet."

    return f"""You are a theme clustering engine for AI/ML research trend analysis.

Existing themes (preserve these names where applicable):
{existing_block}

New items to cluster:
{items_block}

Tasks:
1. Assign each item to a canonical theme name. Use existing theme names when a match is clear.
   Create new theme names only when no existing theme fits.
   Theme names should be 2–5 words, noun-phrase form (e.g. "Inference Cost Reduction").
2. For each theme, write a one-sentence definition (max 20 words).
3. Identify up to 10 pairwise theme relationships. Use one of:
   causal (A enables/improves B), competitive (A vs B), compositional (A+B used together),
   contradictory (A conflicts with B).

Respond ONLY with valid JSON matching this schema (no markdown fences):
{{
  "assignments": [
    {{"url": "...", "theme": "...", "domain": "..."}}
  ],
  "theme_definitions": [
    {{"theme": "...", "domain": "...", "definition": "..."}}
  ],
  "relationships": [
    {{"source": "ThemeA", "target": "ThemeB", "rel_type": "causal", "weight": 1}}
  ]
}}
Domains must be one of: {", ".join(DOMAIN_TAXONOMY)}.
"""


def cluster_themes(
    records: list[CanonicalRecord],
    existing_themes: list[str],
) -> tuple[dict[str, str], list[dict], list[dict]]:
    """Use Gemini to assign theme labels and extract relationships.

    Returns:
        url_to_theme: dict mapping item URL → canonical theme name
        theme_definitions: list of {theme, domain, definition}
        relationships: list of {source, target, rel_type, weight}
    """
    if not records:
        return {}, [], []

    # Fast pre-normalization: apply synonym map before calling Gemini
    for rec in records:
        if rec.claim:
            rec.claim = rec.claim  # synonyms applied in final theme name, not claim
    existing_normalized = [normalize_theme_name(t) for t in existing_themes]

    prompt = _build_clustering_prompt(records, existing_normalized)
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(max_output_tokens=4096),
        )
        raw = response.text.strip()
        # Strip markdown fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)
        data = json.loads(raw)
    except (genai_errors.APIError, json.JSONDecodeError, Exception) as exc:
        logger.warning("Theme clustering Gemini call failed: %s", exc)
        # Fallback: assign "General" theme to everything
        url_to_theme = {r.url: normalize_theme_name(r.domain or "General") for r in records}
        return url_to_theme, [], []

    assignments = data.get("assignments", [])
    definitions = data.get("theme_definitions", [])
    relationships = data.get("relationships", [])

    # Normalize all theme names through synonym map
    url_to_theme: dict[str, str] = {}
    for a in assignments:
        url = a.get("url", "")
        theme = normalize_theme_name(a.get("theme", "General"))
        if url:
            url_to_theme[url] = theme

    for d in definitions:
        d["theme"] = normalize_theme_name(d.get("theme", ""))

    for r in relationships:
        r["source"] = normalize_theme_name(r.get("source", ""))
        r["target"] = normalize_theme_name(r.get("target", ""))

    return url_to_theme, definitions, relationships


def build_theme_nodes(
    records: list[CanonicalRecord],
    url_to_theme: dict[str, str],
    definitions: list[dict],
    existing_nodes: list[ThemeNode],
) -> list[ThemeNode]:
    """Merge today's clustering results with existing theme nodes."""
    def_map = {d["theme"]: d for d in definitions}

    # Count items and source classes per theme
    theme_items: Counter = Counter()
    theme_source_classes: dict[str, Counter] = {}
    for rec in records:
        theme = url_to_theme.get(rec.url, "General")
        theme_items[theme] += 1
        theme_source_classes.setdefault(theme, Counter())[rec.source_class] += 1

    # Build lookup of existing nodes
    existing_map = {n.name: n for n in existing_nodes}

    nodes: list[ThemeNode] = []
    all_themes = set(theme_items.keys()) | set(existing_map.keys())

    for theme_name in sorted(all_themes):
        existing = existing_map.get(theme_name, ThemeNode(name=theme_name))
        defn = def_map.get(theme_name, {})

        sc_counter = theme_source_classes.get(theme_name, Counter())
        classes_present = [cls for cls, _ in sc_counter.most_common()]

        node = ThemeNode(
            name=theme_name,
            domain=defn.get("domain") or existing.domain or "unknown",
            definition=defn.get("definition") or existing.definition,
            state=existing.state,  # state updated later by trend_state
            item_count=theme_items.get(theme_name, 0),
            source_classes=classes_present or existing.source_classes,
            source_class_counts=dict(sc_counter) if sc_counter else existing.source_class_counts,
            hype_risk=existing.hype_risk,
        )
        nodes.append(node)

    return nodes


def build_graph_edges(relationships: list[dict]) -> list[GraphEdge]:
    """Convert raw relationship dicts to GraphEdge objects, deduplicating."""
    seen: set[tuple] = set()
    edges: list[GraphEdge] = []
    for r in relationships:
        src = r.get("source", "")
        tgt = r.get("target", "")
        rel = r.get("rel_type", "causal")
        if not src or not tgt or src == tgt:
            continue
        key = (src, tgt, rel)
        if key in seen:
            continue
        seen.add(key)
        edges.append(GraphEdge(
            source=src,
            target=tgt,
            rel_type=rel,
            weight=float(r.get("weight", 1.0)),
        ))
    return edges
