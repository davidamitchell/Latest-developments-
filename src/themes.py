"""Theme clustering, normalization, and relationship graph extraction."""

from __future__ import annotations

import json
import logging
import os
import re
from collections import Counter

from google import genai
from google.genai import types

from src.models import CanonicalRecord, GraphEdge, ThemeNode
from src.retry import with_backoff

logger = logging.getLogger(__name__)

# ── Canonical domain taxonomy ────────────────────────────────────────
DOMAIN_TAXONOMY: list[str] = [
    "multimodal",
    "agents",
    "infra",
    "reasoning",
    "safety",
    "evals",
    "data",
    "hardware",
    "general",
]

# Keyword → canonical theme name for fast normalization without an API call.
# These collapse common synonyms before Gemini sees the text.
_SYNONYM_MAP: dict[str, str] = {
    # Agentic
    "tool use": "Agent Tool Use",
    "function calling": "Agent Tool Use",
    "tool calling": "Agent Tool Use",
    "function call": "Agent Tool Use",
    "agent reliability": "Agent Reliability",
    "multi-agent": "Multi-Agent Systems",
    "multiagent": "Multi-Agent Systems",
    "agentic": "Agentic Workflows",
    # Retrieval / RAG
    "rag": "Retrieval-Augmented Generation",
    "retrieval augmented": "Retrieval-Augmented Generation",
    # Alignment / Safety
    "rlhf": "RLHF & Alignment",
    "rlaif": "RLHF & Alignment",
    "dpo": "RLHF & Alignment",
    "safety": "AI Safety & Alignment",
    "alignment": "AI Safety & Alignment",
    "jailbreak": "AI Safety & Alignment",
    "red team": "AI Safety & Alignment",
    # Inference / Cost
    "inference cost": "Inference Cost Reduction",
    "inference efficiency": "Inference Cost Reduction",
    "llm cost": "Inference Cost Reduction",
    "token cost": "Inference Cost Reduction",
    "token pricing": "Inference Cost Reduction",
    "pricing per token": "Inference Cost Reduction",
    "cost per token": "Inference Cost Reduction",
    # Local / self-hosted models
    "local llm inference": "Local LLM Inference",
    "local llm": "Local LLM Applications",
    "local model": "Local LLM Applications",
    "on-device": "Local LLM Applications",
    "self-hosted": "Local LLM Applications",
    "self hosted": "Local LLM Applications",
    "ollama": "Local LLM Applications",
    "llama.cpp": "Local LLM Applications",
    "localai": "Local LLM Applications",
    "lm studio": "Local LLM Applications",
    "local inference": "Local LLM Applications",
    "edge inference": "Local LLM Applications",
    # Reasoning / Context
    "reasoning model": "Long-Context Reasoning",
    "chain of thought": "Long-Context Reasoning",
    "long context": "Long-Context Reasoning",
    "context length": "Long-Context Reasoning",
    # Fine-tuning
    "fine-tuning": "Fine-Tuning & Adaptation",
    "finetuning": "Fine-Tuning & Adaptation",
    "lora": "Fine-Tuning & Adaptation",
    # Distillation / Compression
    "distillation": "Model Distillation",
    "model compression": "Model Distillation",
    "quantization": "Model Distillation",
    # Evals
    "benchmark": "Benchmarks & Evals",
    "evaluation": "Benchmarks & Evals",
    "leaderboard": "Benchmarks & Evals",
    # Multimodal
    "multimodal": "Multimodal Models",
    "vision language": "Multimodal Models",
    "vla": "Multimodal Models",
    # Open source
    "open source model": "Open-Source Models",
    "open weight": "Open-Source Models",
    "open weights": "Open-Source Models",
    # Coding
    "code generation": "Code Generation",
    "coding model": "Code Generation",
    "ai coding": "Code Generation",
    # Data
    "synthetic data": "Synthetic Data Pipelines",
    "data synthesis": "Synthetic Data Pipelines",
    # Workforce / Jobs
    "workforce": "AI Workforce & Jobs",
    "job displacement": "AI Workforce & Jobs",
    "labour": "AI Workforce & Jobs",
    "employment": "AI Workforce & Jobs",
    # Infrastructure / Cost
    "ai infrastructure": "AI Infrastructure",
    "gpu cost": "AI Infrastructure",
    "datacenter": "AI Infrastructure",
    # Supply chain
    "supply chain": "Supply Chain Security",
    # Capabilities
    "llm capabilities": "LLM Capabilities",
    "advanced llm": "LLM Capabilities",
    "frontier model": "LLM Capabilities",
    # Business / Strategy
    "ai business": "AI Business Strategy",
    "ai strategy": "AI Business Strategy",
    # Pace / Acceleration
    "ai pace": "AI Development Pace",
    "acceleration": "AI Development Pace",
}

# Known acronyms that title() breaks — restored after title-casing.
_ACRONYM_FIXES: list[tuple[str, str]] = [
    ("Ai ", "AI "),
    (" Ai", " AI"),
    ("Llm", "LLM"),
    ("Rlhf", "RLHF"),
    ("Rag", "RAG"),
    ("Api", "API"),
    ("Gpu", "GPU"),
    ("Vla", "VLA"),
    ("Dpo", "DPO"),
    ("Lora", "LoRA"),
    ("Nlp", "NLP"),
    ("Ml ", "ML "),
    (" Ml", " ML"),
]


def normalize_theme_name(raw: str) -> str:
    """Collapse synonyms and title-case with acronym preservation."""
    lower = raw.lower().strip()
    # Longest-match synonym lookup
    for pattern, canonical in _SYNONYM_MAP.items():
        if pattern in lower:
            return canonical
    # Title-case with acronym fixes
    result = raw.strip().title()
    for broken, fixed in _ACRONYM_FIXES:
        result = result.replace(broken, fixed)
    # Also fix trailing acronym (no trailing space)
    result = re.sub(r"\bAi\b", "AI", result)
    result = re.sub(r"\bLlm\b", "LLM", result)
    return result


def _build_clustering_prompt(records: list[CanonicalRecord], existing_themes: list[str]) -> str:
    items_block = "\n".join(
        f"- URL: {r.url}\n  Claim: {r.claim or r.title}\n  Domain: {r.domain}\n  Evidence: {r.evidence_type}"
        for r in records[:60]  # cap to keep token budget bounded
    )
    existing_block = (
        "\n".join(f"- {t}" for t in existing_themes) if existing_themes else "None yet."
    )

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


def _call_gemini_cluster(client, prompt: str) -> dict:
    """Make the Gemini call and parse the JSON response; raises on any failure."""
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(max_output_tokens=4096),
    )
    raw = response.text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)
    return json.loads(raw)


def cluster_themes(
    records: list[CanonicalRecord],
    existing_themes: list[str],
) -> tuple[dict[str, str], list[dict], list[dict]]:
    """Use Gemini to assign theme labels and extract relationships.

    Returns:
        url_to_theme: dict mapping item URL → canonical theme name
        theme_definitions: list of {theme, domain, definition}
        relationships: list of {source, target, rel_type, weight}

    Retries up to 3 times, honouring any retryDelay from 429 responses.
    Falls back to domain-based theme assignment if all attempts fail.
    """
    if not records:
        return {}, [], []

    existing_normalized = [normalize_theme_name(t) for t in existing_themes]
    prompt = _build_clustering_prompt(records, existing_normalized)
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))

    try:
        data = with_backoff(
            lambda: _call_gemini_cluster(client, prompt),
            max_attempts=3,
            base_delay=2.0,
            label="theme-clustering",
        )
    except RuntimeError as exc:
        logger.warning("Theme clustering failed after retries: %s", exc)
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
        edges.append(
            GraphEdge(
                source=src,
                target=tgt,
                rel_type=rel,
                weight=float(r.get("weight", 1.0)),
            )
        )
    return edges
