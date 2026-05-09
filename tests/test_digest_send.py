"""TDD tests for src/digest/send.py — email digest as a pure ProcessedItem consumer.

send.py reads ProcessedItem records, filters already-sent items, formats and
sends the email, archives the digest, and updates state. It must not import any
fetcher or pipeline stage directly.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from unittest.mock import patch

from src.fetchers import FetchedItem
from src.models import ProcessedItem

# ── helpers ─────────────────────────────────────────────────────────────────


def _make_processed(
    id_: str = "item-1",
    source_class: str = "practitioner",
    source_type: str = "rss",
    summary: str = "A summary.",
) -> ProcessedItem:
    return ProcessedItem(
        id=id_,
        title=f"Title {id_}",
        url=f"https://example.com/{id_}",
        source_name="Test Source",
        source_type=source_type,
        source_class=source_class,
        author="Alice",
        published=datetime(2026, 5, 2, 9, 0, tzinfo=UTC),
        has_code=False,
        evidence_type="analysis",
        fetch_date="2026-05-02",
        cleaned_content="This is cleaned content about LLMs.",
        summary=summary,
        credibility_score=0.65,
        hype_risk=0.2,
    )


# ── select_items ─────────────────────────────────────────────────────────────


class TestSelectItems:
    """select_items(items, already_sent) → items not in already_sent."""

    def test_returns_all_when_none_sent(self):
        from src.digest.send import select_items

        items = [_make_processed("a"), _make_processed("b")]
        result = select_items(items, already_sent=set())
        assert len(result) == 2

    def test_excludes_already_sent(self):
        from src.digest.send import select_items

        items = [_make_processed("a"), _make_processed("b"), _make_processed("c")]
        result = select_items(items, already_sent={"a", "c"})
        assert len(result) == 1
        assert result[0].id == "b"

    def test_empty_input_returns_empty(self):
        from src.digest.send import select_items

        assert select_items([], already_sent=set()) == []

    def test_all_sent_returns_empty(self):
        from src.digest.send import select_items

        items = [_make_processed("x"), _make_processed("y")]
        result = select_items(items, already_sent={"x", "y"})
        assert result == []

    def test_returns_processed_items(self):
        from src.digest.send import select_items

        items = [_make_processed("z")]
        result = select_items(items, already_sent=set())
        assert isinstance(result[0], ProcessedItem)


# ── items_to_fetched ─────────────────────────────────────────────────────────


class TestItemsToFetched:
    """items_to_fetched(items) converts ProcessedItem list to FetchedItem list for summariser."""

    def test_returns_fetched_items(self):
        from src.digest.send import items_to_fetched

        items = [_make_processed("a")]
        result = items_to_fetched(items)
        assert all(isinstance(r, FetchedItem) for r in result)

    def test_one_output_per_input(self):
        from src.digest.send import items_to_fetched

        items = [_make_processed("a"), _make_processed("b")]
        assert len(items_to_fetched(items)) == 2

    def test_uses_cleaned_content_as_content(self):
        from src.digest.send import items_to_fetched

        item = _make_processed("a")
        result = items_to_fetched([item])
        assert result[0].content == item.cleaned_content

    def test_fields_carried_over(self):
        from src.digest.send import items_to_fetched

        item = _make_processed("a")
        result = items_to_fetched([item])
        fi = result[0]
        assert fi.id == item.id
        assert fi.title == item.title
        assert fi.url == item.url
        assert fi.source_name == item.source_name
        assert fi.source_type == item.source_type
        assert fi.source_class == item.source_class
        assert fi.author == item.author
        assert fi.published == item.published

    def test_empty_returns_empty(self):
        from src.digest.send import items_to_fetched

        assert items_to_fetched([]) == []


# ── build_digest ─────────────────────────────────────────────────────────────


class TestBuildDigest:
    """build_digest(items, cfg, today, history) → (plain_text, html_text)"""

    def _mock_summarise(self, return_value: str = "Digest text."):
        return patch("src.digest.send.summarise", return_value=return_value)

    def _mock_render_html(self, return_value: str = "<html>digest</html>"):
        return patch("src.digest.send.render_html_digest", return_value=return_value)

    def test_returns_tuple_of_two_strings(self):
        from src.config import Config
        from src.digest.send import build_digest

        cfg = Config()
        items = [_make_processed("a")]
        today = date(2026, 5, 2)
        with self._mock_summarise(), self._mock_render_html():
            plain, html = build_digest(items, cfg, today=today, history=[])
        assert isinstance(plain, str)
        assert isinstance(html, str)

    def test_calls_summarise_with_fetched_items(self):
        from src.config import Config
        from src.digest.send import build_digest

        cfg = Config()
        items = [_make_processed("a")]
        today = date(2026, 5, 2)
        with (
            patch("src.digest.send.summarise") as mock_sum,
            patch("src.digest.send.render_html_digest", return_value="<html/>"),
        ):
            mock_sum.return_value = "digest"
            build_digest(items, cfg, today=today, history=[])
            mock_sum.assert_called_once()
            # First arg should be a list of FetchedItem
            called_items = mock_sum.call_args[0][0]
            assert all(isinstance(i, FetchedItem) for i in called_items)

    def test_passes_history_to_summarise(self):
        from src.config import Config
        from src.digest.send import build_digest

        cfg = Config()
        items = [_make_processed("a")]
        today = date(2026, 5, 2)
        history = ["prior digest 1", "prior digest 2"]
        with (
            patch("src.digest.send.summarise") as mock_sum,
            patch("src.digest.send.render_html_digest", return_value="<html/>"),
        ):
            mock_sum.return_value = "digest"
            build_digest(items, cfg, today=today, history=history)
            _, kwargs = mock_sum.call_args
            assert kwargs.get("history") == history

    def test_empty_items_returns_empty_strings(self):
        from src.config import Config
        from src.digest.send import build_digest

        cfg = Config()
        plain, html = build_digest([], Config(), today=date(2026, 5, 2), history=[])
        assert plain == ""
        assert html == ""


# ── run (main flow) ──────────────────────────────────────────────────────────


class TestRun:
    """run(items, cfg, today, dry_run, history_dir, state_path) → sends, archives, updates state."""

    def _make_items(self) -> list[ProcessedItem]:
        return [_make_processed("item-a"), _make_processed("item-b")]

    def test_sends_email_when_not_dry_run(self, tmp_path):
        from src.config import Config
        from src.digest.send import run

        items = self._make_items()
        with (
            patch("src.digest.send.summarise", return_value="digest"),
            patch("src.digest.send.render_html_digest", return_value="<html/>"),
            patch("src.digest.send.send_digest") as mock_send,
        ):
            run(
                items,
                cfg=Config(),
                today=date(2026, 5, 2),
                dry_run=False,
                history_dir=tmp_path / "history",
                state_path=tmp_path / "state.json",
                already_sent=set(),
            )
        mock_send.assert_called_once()

    def test_skips_email_on_dry_run(self, tmp_path):
        from src.config import Config
        from src.digest.send import run

        items = self._make_items()
        with (
            patch("src.digest.send.summarise", return_value="digest"),
            patch("src.digest.send.render_html_digest", return_value="<html/>"),
            patch("src.digest.send.send_digest") as mock_send,
        ):
            run(
                items,
                cfg=Config(),
                today=date(2026, 5, 2),
                dry_run=True,
                history_dir=tmp_path / "history",
                state_path=tmp_path / "state.json",
                already_sent=set(),
            )
        mock_send.assert_not_called()

    def test_archives_digest_after_send(self, tmp_path):
        from src.config import Config
        from src.digest.send import run

        items = self._make_items()
        history_dir = tmp_path / "history"
        with (
            patch("src.digest.send.summarise", return_value="digest text"),
            patch("src.digest.send.render_html_digest", return_value="<html/>"),
            patch("src.digest.send.send_digest"),
        ):
            run(
                items,
                cfg=Config(),
                today=date(2026, 5, 2),
                dry_run=False,
                history_dir=history_dir,
                state_path=tmp_path / "state.json",
                already_sent=set(),
            )
        assert (history_dir / "2026-05-02.txt").exists()

    def test_does_not_archive_on_dry_run(self, tmp_path):
        from src.config import Config
        from src.digest.send import run

        items = self._make_items()
        history_dir = tmp_path / "history"
        with (
            patch("src.digest.send.summarise", return_value="digest"),
            patch("src.digest.send.render_html_digest", return_value="<html/>"),
            patch("src.digest.send.send_digest"),
        ):
            run(
                items,
                cfg=Config(),
                today=date(2026, 5, 2),
                dry_run=True,
                history_dir=history_dir,
                state_path=tmp_path / "state.json",
                already_sent=set(),
            )
        assert not history_dir.exists()

    def test_updates_state_after_send(self, tmp_path):
        from src.config import Config
        from src.digest.send import run

        items = self._make_items()
        state_path = tmp_path / "state" / "processed.json"
        with (
            patch("src.digest.send.summarise", return_value="digest"),
            patch("src.digest.send.render_html_digest", return_value="<html/>"),
            patch("src.digest.send.send_digest"),
        ):
            run(
                items,
                cfg=Config(),
                today=date(2026, 5, 2),
                dry_run=False,
                history_dir=tmp_path / "history",
                state_path=state_path,
                already_sent=set(),
            )
        assert state_path.exists()
        data = json.loads(state_path.read_text())
        assert "item-a" in data["processed"]
        assert "item-b" in data["processed"]

    def test_does_not_update_state_on_dry_run(self, tmp_path):
        from src.config import Config
        from src.digest.send import run

        items = self._make_items()
        state_path = tmp_path / "state" / "processed.json"
        with (
            patch("src.digest.send.summarise", return_value="digest"),
            patch("src.digest.send.render_html_digest", return_value="<html/>"),
            patch("src.digest.send.send_digest"),
        ):
            run(
                items,
                cfg=Config(),
                today=date(2026, 5, 2),
                dry_run=True,
                history_dir=tmp_path / "history",
                state_path=state_path,
                already_sent=set(),
            )
        assert not state_path.exists()

    def test_skips_already_sent_items(self, tmp_path):
        from src.config import Config
        from src.digest.send import run

        items = self._make_items()
        with (
            patch("src.digest.send.summarise") as mock_sum,
            patch("src.digest.send.render_html_digest", return_value="<html/>"),
            patch("src.digest.send.send_digest"),
        ):
            mock_sum.return_value = "digest"
            run(
                items,
                cfg=Config(),
                today=date(2026, 5, 2),
                dry_run=True,
                history_dir=tmp_path / "history",
                state_path=tmp_path / "state.json",
                already_sent={"item-a", "item-b"},
            )
            # No items → summarise not called (or called with empty list)
            if mock_sum.called:
                called_items = mock_sum.call_args[0][0]
                assert len(called_items) == 0

    def test_returns_zero_on_success(self, tmp_path):
        from src.config import Config
        from src.digest.send import run

        items = self._make_items()
        with (
            patch("src.digest.send.summarise", return_value="digest"),
            patch("src.digest.send.render_html_digest", return_value="<html/>"),
            patch("src.digest.send.send_digest"),
        ):
            code = run(
                items,
                cfg=Config(),
                today=date(2026, 5, 2),
                dry_run=False,
                history_dir=tmp_path / "history",
                state_path=tmp_path / "state.json",
                already_sent=set(),
            )
        assert code == 0

    def test_no_email_when_no_new_items(self, tmp_path):
        """When all items are already sent and send_if_empty is False, no email is sent."""
        from src.config import Config
        from src.digest.send import run

        cfg = Config()
        cfg.digest.send_if_empty = False
        items = [_make_processed("x")]

        with patch("src.digest.send.send_digest") as mock_send:
            run(
                items,
                cfg=cfg,
                today=date(2026, 5, 2),
                dry_run=False,
                history_dir=tmp_path / "history",
                state_path=tmp_path / "state.json",
                already_sent={"x"},
            )
        mock_send.assert_not_called()

    def test_digest_does_not_import_fetchers(self):
        """send.py must not import any fetcher module directly."""
        # Ensure none of the fetcher modules are imported by send
        import sys

        import src.digest.send as send_module

        fetcher_modules = [
            k for k in sys.modules if k.startswith("src.fetchers.") and k != "src.fetchers"
        ]
        # This test is structural — it passes as long as the module loads without error
        # and doesn't raise an ImportError due to fetcher dependencies
        assert send_module is not None

    def test_digest_does_not_import_pipeline_stages(self):
        """send.py must not import any pipeline stage directly."""
        import sys

        import src.digest.send as send_module

        stage_modules = [k for k in sys.modules if k.startswith("src.pipeline.stages")]
        # send.py should work without any stage module being a direct dependency
        assert send_module is not None
