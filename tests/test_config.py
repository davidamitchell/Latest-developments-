"""Tests for the new unified config schema (ADR-0018).

src/config.py exposes:
  - SourceEntry: flat source list entry with type discriminator
  - DigestConfig: independent email-digest settings; references only ProcessedItem fields
  - Config: sources (list[SourceEntry]) + digest (DigestConfig) + history + logging
  - load_config(path): loads config/sources.yaml and returns Config

DigestConfig must have ZERO knowledge of which sources are configured — its
filter predicates reference only ProcessedItem field names.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from src.config import Config, DigestConfig, HistoryConfig, LoggingConfig, SourceEntry, load_config

# ── helpers ─────────────────────────────────────────────────────────────────


def _write_yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "sources.yaml"
    p.write_text(textwrap.dedent(content))
    return p


# ── SourceEntry ──────────────────────────────────────────────────────────────


class TestSourceEntry:
    def test_required_fields(self):
        entry = SourceEntry(type="rss", name="Test", source_class="operator")
        assert entry.type == "rss"
        assert entry.name == "Test"
        assert entry.source_class == "operator"

    def test_enabled_defaults_true(self):
        entry = SourceEntry(type="rss", name="Test", source_class="operator")
        assert entry.enabled is True

    def test_options_defaults_empty(self):
        entry = SourceEntry(type="rss", name="Test", source_class="operator")
        assert entry.options == {}

    def test_disabled_entry(self):
        entry = SourceEntry(type="rss", name="Test", source_class="operator", enabled=False)
        assert entry.enabled is False

    def test_options_carries_type_specific_data(self):
        entry = SourceEntry(
            type="youtube",
            name="Nate Jones",
            source_class="practitioner",
            options={"channel_id": "UCabc", "max_videos": 3},
        )
        assert entry.options["channel_id"] == "UCabc"
        assert entry.options["max_videos"] == 3


# ── DigestConfig ─────────────────────────────────────────────────────────────


class TestDigestConfig:
    def test_defaults(self):
        cfg = DigestConfig()
        assert cfg.subject == "Daily AI Digest — {date}"
        assert cfg.send_if_empty is False
        assert cfg.min_credibility == 0.0
        assert cfg.max_hype_risk == 1.0
        assert cfg.exclude_marketing is False
        assert "gemini" in cfg.model
        assert cfg.max_tokens > 0
        assert cfg.max_items_per_source > 0

    def test_is_independent_of_source_config(self):
        """DigestConfig must not reference source names, types, or source topology."""
        import inspect

        src_text = inspect.getsource(DigestConfig)
        forbidden = ["source_name", "source_type", "channel_id", "slug", "url"]
        for token in forbidden:
            assert token not in src_text, (
                f"DigestConfig must not reference {token!r} — it must only know ProcessedItem fields"
            )

    def test_filter_predicates_are_processed_item_fields(self):
        """The three filter predicates correspond to ProcessedItem fields."""
        import dataclasses

        from src.models import ProcessedItem

        pi_fields = {f.name for f in dataclasses.fields(ProcessedItem)}
        assert "credibility_score" in pi_fields  # min_credibility predicate
        assert "hype_risk" in pi_fields  # max_hype_risk predicate
        assert "is_marketing" in pi_fields  # exclude_marketing predicate


# ── Config dataclass ─────────────────────────────────────────────────────────


class TestConfigDataclass:
    def test_has_sources_list(self):
        cfg = Config()
        assert isinstance(cfg.sources, list)

    def test_has_digest(self):
        cfg = Config()
        assert isinstance(cfg.digest, DigestConfig)

    def test_has_history(self):
        cfg = Config()
        assert isinstance(cfg.history, HistoryConfig)

    def test_has_logging(self):
        cfg = Config()
        assert isinstance(cfg.logging, LoggingConfig)

    def test_does_not_have_old_youtube_field(self):
        cfg = Config()
        assert not hasattr(cfg, "youtube"), "Config must not have legacy youtube field"

    def test_does_not_have_old_blogs_field(self):
        cfg = Config()
        assert not hasattr(cfg, "blogs"), "Config must not have legacy blogs field"

    def test_does_not_have_old_summary_field(self):
        cfg = Config()
        assert not hasattr(cfg, "summary"), "Config must not have legacy summary field"

    def test_does_not_have_old_email_field(self):
        cfg = Config()
        assert not hasattr(cfg, "email"), "Config must not have legacy email field"

    def test_does_not_have_old_trends_field(self):
        cfg = Config()
        assert not hasattr(cfg, "trends"), "Config must not have legacy trends field"


# ── load_config ───────────────────────────────────────────────────────────────


class TestLoadConfig:
    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.yaml")

    def test_empty_yaml_returns_defaults(self, tmp_path):
        p = _write_yaml(tmp_path, "")
        cfg = load_config(p)
        assert isinstance(cfg, Config)
        assert cfg.sources == []
        assert isinstance(cfg.digest, DigestConfig)

    def test_loads_rss_source(self, tmp_path):
        p = _write_yaml(
            tmp_path,
            """
            sources:
              - type: rss
                name: Anthropic Blog
                url: "https://www.anthropic.com/rss.xml"
                source_class: operator
                enabled: true
        """,
        )
        cfg = load_config(p)
        assert len(cfg.sources) == 1
        entry = cfg.sources[0]
        assert entry.type == "rss"
        assert entry.name == "Anthropic Blog"
        assert entry.source_class == "operator"
        assert entry.enabled is True
        assert entry.options["url"] == "https://www.anthropic.com/rss.xml"

    def test_loads_youtube_source(self, tmp_path):
        p = _write_yaml(
            tmp_path,
            """
            sources:
              - type: youtube
                name: Nate Jones
                channel_id: "UC0C-17n9iuUQPylguM1d-lQ"
                source_class: practitioner
                enabled: true
                max_videos: 5
        """,
        )
        cfg = load_config(p)
        entry = cfg.sources[0]
        assert entry.type == "youtube"
        assert entry.options["channel_id"] == "UC0C-17n9iuUQPylguM1d-lQ"
        assert entry.options["max_videos"] == 5

    def test_loads_substack_source(self, tmp_path):
        p = _write_yaml(
            tmp_path,
            """
            sources:
              - type: substack
                name: Nate's Newsletter
                slug: natesnewsletter
                source_class: media
                enabled: true
        """,
        )
        cfg = load_config(p)
        entry = cfg.sources[0]
        assert entry.type == "substack"
        assert entry.options["slug"] == "natesnewsletter"

    def test_loads_hackernews_singleton(self, tmp_path):
        p = _write_yaml(
            tmp_path,
            """
            sources:
              - type: hackernews
                name: Hacker News
                source_class: practitioner
                enabled: true
                min_score: 150
                max_stories: 20
                keywords:
                  - llm
                  - agents
        """,
        )
        cfg = load_config(p)
        entry = cfg.sources[0]
        assert entry.type == "hackernews"
        assert entry.options["min_score"] == 150
        assert entry.options["max_stories"] == 20
        assert "llm" in entry.options["keywords"]

    def test_loads_arxiv_singleton(self, tmp_path):
        p = _write_yaml(
            tmp_path,
            """
            sources:
              - type: arxiv
                name: arXiv
                source_class: primary
                enabled: true
                categories: [cs.AI, cs.LG]
                max_papers: 25
        """,
        )
        cfg = load_config(p)
        entry = cfg.sources[0]
        assert entry.type == "arxiv"
        assert entry.options["categories"] == ["cs.AI", "cs.LG"]
        assert entry.options["max_papers"] == 25

    def test_disabled_entry_is_still_loaded(self, tmp_path):
        """Disabled sources are loaded but have enabled=False."""
        p = _write_yaml(
            tmp_path,
            """
            sources:
              - type: huggingface
                name: HuggingFace Models
                source_class: primary
                enabled: false
                max_models: 50
        """,
        )
        cfg = load_config(p)
        assert len(cfg.sources) == 1
        assert cfg.sources[0].enabled is False

    def test_loads_multiple_sources(self, tmp_path):
        p = _write_yaml(
            tmp_path,
            """
            sources:
              - type: rss
                name: Blog A
                url: "https://a.example.com/feed"
                source_class: operator
                enabled: true
              - type: rss
                name: Blog B
                url: "https://b.example.com/feed"
                source_class: practitioner
                enabled: true
              - type: hackernews
                name: Hacker News
                source_class: practitioner
                enabled: true
        """,
        )
        cfg = load_config(p)
        assert len(cfg.sources) == 3
        types = [e.type for e in cfg.sources]
        assert types.count("rss") == 2
        assert "hackernews" in types

    def test_loads_digest_section(self, tmp_path):
        p = _write_yaml(
            tmp_path,
            """
            digest:
              subject: "My AI Digest — {date}"
              send_if_empty: true
              min_credibility: 0.4
              max_hype_risk: 0.7
              exclude_marketing: true
              model: "gemini-2.5-flash"
              max_tokens: 1500
              max_items_per_source: 3
              prompt: "Summarise these items."
        """,
        )
        cfg = load_config(p)
        d = cfg.digest
        assert d.subject == "My AI Digest — {date}"
        assert d.send_if_empty is True
        assert d.min_credibility == pytest.approx(0.4)
        assert d.max_hype_risk == pytest.approx(0.7)
        assert d.exclude_marketing is True
        assert d.model == "gemini-2.5-flash"
        assert d.max_tokens == 1500
        assert d.max_items_per_source == 3
        assert d.prompt == "Summarise these items."

    def test_digest_defaults_when_section_absent(self, tmp_path):
        p = _write_yaml(tmp_path, "sources: []")
        cfg = load_config(p)
        d = cfg.digest
        assert d.min_credibility == 0.0
        assert d.max_hype_risk == 1.0
        assert d.exclude_marketing is False

    def test_history_section_loads(self, tmp_path):
        p = _write_yaml(
            tmp_path,
            """
            history:
              enabled: false
              history_days: 14
              history_dir: "digests"
        """,
        )
        cfg = load_config(p)
        assert cfg.history.enabled is False
        assert cfg.history.history_days == 14
        assert cfg.history.history_dir == "digests"

    def test_logging_section_loads(self, tmp_path):
        p = _write_yaml(
            tmp_path,
            """
            logging:
              level: DEBUG
              log_file: "logs/out.log"
        """,
        )
        cfg = load_config(p)
        assert cfg.logging.level == "DEBUG"
        assert cfg.logging.log_file == "logs/out.log"

    def test_null_sources_returns_empty_list(self, tmp_path):
        """sources: null (all items commented out) must not raise TypeError."""
        p = _write_yaml(tmp_path, "sources:\n")
        cfg = load_config(p)
        assert cfg.sources == []

    def test_digest_and_sources_are_independent(self, tmp_path):
        """Changing sources section does not affect digest section and vice versa."""
        p = _write_yaml(
            tmp_path,
            """
            sources:
              - type: rss
                name: Blog A
                url: "https://a.example.com/feed"
                source_class: operator
                enabled: true
            digest:
              min_credibility: 0.5
        """,
        )
        cfg = load_config(p)
        assert len(cfg.sources) == 1
        assert cfg.digest.min_credibility == pytest.approx(0.5)
        # digest has no knowledge of source names or types
        assert not hasattr(cfg.digest, "sources")
        assert not hasattr(cfg.digest, "source_name")
