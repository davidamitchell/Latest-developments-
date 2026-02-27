"""Tests for src/summariser.py."""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock, patch

from src.config import SummaryConfig
from src.fetchers import FetchedItem
from src.summariser import format_link_digest, format_run_summary, render_html_digest, summarise


def _make_item(
    id: str = "id1",
    title: str = "Test Article",
    source: str = "Test Source",
    content: str = "Some content here",
    source_type: str = "",
) -> FetchedItem:
    return FetchedItem(
        id=id,
        title=title,
        url=f"https://example.com/{id}",
        content=content,
        source_name=source,
        source_type=source_type,
    )


def _make_config(**kwargs: object) -> SummaryConfig:
    defaults: dict = {
        "model": "gemini-2.0-flash",
        "max_tokens": 500,
        "max_items_per_source": 5,
        "prompt": "Summarise this.",
    }
    defaults.update(kwargs)
    return SummaryConfig(**defaults)  # type: ignore[arg-type]


def _mock_client(text: str = "summary") -> MagicMock:
    """Return a mock genai.Client whose models.generate_content() returns text."""
    mock = MagicMock()
    mock.return_value.models.generate_content.return_value.text = text
    return mock


class TestSummarise:
    def test_empty_items_returns_empty_string(self) -> None:
        assert summarise([], _make_config()) == ""

    def test_calls_gemini_with_correct_model(self) -> None:
        mock_cls = _mock_client()
        with patch("src.summariser.genai.Client", mock_cls):
            summarise([_make_item()], _make_config(model="gemini-1.5-pro"))

        call_kwargs = mock_cls.return_value.models.generate_content.call_args.kwargs
        assert call_kwargs["model"] == "gemini-1.5-pro"

    def test_returns_digest_with_date_header(self) -> None:
        with patch("src.summariser.genai.Client", _mock_client("Gemini output")):
            result = summarise([_make_item()], _make_config(), today=date(2026, 2, 21))

        assert "21 Feb 2026" in result
        assert "Gemini output" in result

    def test_uses_default_prompt_when_config_prompt_empty(self) -> None:
        mock_cls = _mock_client()
        with patch("src.summariser.genai.Client", mock_cls):
            summarise([_make_item()], _make_config(prompt=""))

        call_kwargs = mock_cls.return_value.models.generate_content.call_args.kwargs
        system = call_kwargs["config"].system_instruction
        assert len(system) > 0

    def test_groups_items_by_source(self) -> None:
        items = [
            _make_item("a", source="YouTube", content="yt content"),
            _make_item("b", source="Blogs", content="blog content"),
        ]
        mock_cls = _mock_client()
        with patch("src.summariser.genai.Client", mock_cls):
            summarise(items, _make_config())

        call_kwargs = mock_cls.return_value.models.generate_content.call_args.kwargs
        contents = call_kwargs["contents"]
        assert "YouTube" in contents
        assert "Blogs" in contents
        assert "yt content" in contents
        assert "blog content" in contents

    def test_respects_max_items_per_source(self) -> None:
        items = [_make_item(str(i), source="S", content=f"content {i}") for i in range(5)]
        mock_cls = _mock_client()
        with patch("src.summariser.genai.Client", mock_cls):
            summarise(items, _make_config(max_items_per_source=2))

        call_kwargs = mock_cls.return_value.models.generate_content.call_args.kwargs
        contents = call_kwargs["contents"]
        assert "content 0" in contents
        assert "content 1" in contents
        assert "content 4" not in contents

    def test_enabled_false_skips_gemini(self) -> None:
        mock_cls = _mock_client()
        with patch("src.summariser.genai.Client", mock_cls):
            result = summarise([_make_item()], _make_config(enabled=False))
            mock_cls.assert_not_called()

        assert "Test Article" in result
        assert "https://example.com/id1" in result

    def test_enabled_false_empty_returns_empty(self) -> None:
        result = summarise([], _make_config(enabled=False))
        assert result == ""

    def test_falls_back_to_link_digest_on_api_error(self) -> None:
        from google.genai import errors as genai_errors

        mock_cls = MagicMock()
        mock_cls.return_value.models.generate_content.side_effect = genai_errors.ClientError(
            429, {"error": {"message": "quota exceeded"}}, MagicMock()
        )
        with patch("src.summariser.genai.Client", mock_cls):
            result = summarise([_make_item()], _make_config(), today=date(2026, 2, 22))

        # Must surface the failure — reader must know AI did not process this
        assert "AI summarisation failed" in result
        assert "ClientError" in result
        assert "no model processing" in result
        # Must still contain the items
        assert "Test Article" in result
        assert "https://example.com/id1" in result


class TestFormatLinkDigest:
    def test_empty_returns_empty(self) -> None:
        assert format_link_digest([], _make_config()) == ""

    def test_contains_title_and_url(self) -> None:
        result = format_link_digest([_make_item()], _make_config(), today=date(2026, 2, 21))
        assert "Test Article" in result
        assert "https://example.com/id1" in result
        assert "21 Feb 2026" in result

    def test_groups_by_source(self) -> None:
        items = [
            _make_item("a", source="YouTube"),
            _make_item("b", source="Blogs"),
        ]
        result = format_link_digest(items, _make_config())
        assert "## YouTube" in result
        assert "## Blogs" in result

    def test_respects_max_items_per_source(self) -> None:
        items = [_make_item(str(i), source="S") for i in range(5)]
        result = format_link_digest(items, _make_config(max_items_per_source=2))
        assert result.count("example.com") == 2


class TestFormatRunSummary:
    def test_contains_timestamp(self) -> None:
        from datetime import datetime

        ts = datetime(2026, 2, 21, 7, 0, 0)
        result = format_run_summary({}, [], run_ts=ts)
        assert "2026-02-21 07:00:00 UTC" in result

    def test_contains_source_counts(self) -> None:
        result = format_run_summary({"YouTube": 3, "Hacker News": 1}, [])
        assert "YouTube: 3 new item(s)" in result
        assert "Hacker News: 1 new item(s)" in result

    def test_contains_total(self) -> None:
        result = format_run_summary({"YouTube": 3, "Blogs/RSS": 2}, [])
        assert "Total new items: 5" in result

    def test_contains_errors_when_present(self) -> None:
        result = format_run_summary({"YouTube": 0}, ["YouTube: connection timeout"])
        assert "Errors" in result
        assert "connection timeout" in result

    def test_no_error_section_when_no_errors(self) -> None:
        result = format_run_summary({"YouTube": 2}, [])
        assert "Errors" not in result

    def test_contains_run_summary_header(self) -> None:
        result = format_run_summary({}, [])
        assert "Run summary" in result


class TestRenderHtmlDigest:
    def test_returns_html_document(self) -> None:
        item = _make_item(source_type="YouTube")
        result = render_html_digest([item], "Summary text", today=date(2026, 2, 27))
        assert "<!DOCTYPE html>" in result
        assert "<html" in result

    def test_contains_date_header(self) -> None:
        item = _make_item()
        result = render_html_digest([item], "Summary", today=date(2026, 2, 27))
        assert "27 Feb 2026" in result

    def test_contains_item_title_and_link(self) -> None:
        item = _make_item(id="abc", title="My Article")
        result = render_html_digest([item], "Summary", today=date(2026, 2, 27))
        assert "My Article" in result
        assert "https://example.com/abc" in result

    def test_contains_source_type_badge(self) -> None:
        item = _make_item(source_type="YouTube")
        result = render_html_digest([item], "Summary", today=date(2026, 2, 27))
        assert "📺" in result
        assert "YouTube" in result

    def test_contains_hacker_news_badge(self) -> None:
        item = _make_item(source="Hacker News", source_type="Hacker News")
        result = render_html_digest([item], "Summary", today=date(2026, 2, 27))
        assert "🔶" in result

    def test_contains_find_out_more_link(self) -> None:
        item = _make_item(id="xyz")
        result = render_html_digest([item], "Summary", today=date(2026, 2, 27))
        assert "Find out more" in result
        assert "https://example.com/xyz" in result

    def test_contains_ai_analysis_section(self) -> None:
        item = _make_item()
        result = render_html_digest([item], "Gemini analysis text", today=date(2026, 2, 27))
        assert "AI Analysis" in result
        assert "Gemini analysis text" in result

    def test_source_name_displayed(self) -> None:
        item = _make_item(source="Nate Jones")
        result = render_html_digest([item], "Summary", today=date(2026, 2, 27))
        assert "Nate Jones" in result

    def test_html_escaping(self) -> None:
        item = _make_item(title="A <script>bad</script> Title")
        result = render_html_digest([item], "Summary", today=date(2026, 2, 27))
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_empty_items_renders_header(self) -> None:
        result = render_html_digest([], "No items today", today=date(2026, 2, 27))
        assert "27 Feb 2026" in result
        assert "No items today" in result

    def test_published_date_shown_in_card(self) -> None:
        item = FetchedItem(
            id="x",
            title="Dated Article",
            url="https://example.com/x",
            content="content",
            source_name="RSS",
            published=datetime(2026, 2, 15),
            source_type="RSS",
        )
        result = render_html_digest([item], "Summary", today=date(2026, 2, 27))
        assert "15 Feb 2026" in result

    def test_dyslexia_friendly_font_in_css(self) -> None:
        item = _make_item()
        result = render_html_digest([item], "Summary", today=date(2026, 2, 27))
        assert "Arial" in result

    def test_multiple_sources_grouped(self) -> None:
        items = [
            _make_item("a", source="YouTube", source_type="YouTube"),
            _make_item("b", source="Hacker News", source_type="Hacker News"),
        ]
        result = render_html_digest(items, "Summary", today=date(2026, 2, 27))
        assert "YouTube" in result
        assert "Hacker News" in result

    def test_bullet_list_rendered_as_ul(self) -> None:
        """_plain_to_html should convert '- item' lines into <ul><li> elements."""
        digest = "## TL;DR\n\n- First key point\n- Second key point\n\nSome paragraph."
        result = render_html_digest([_make_item()], digest, today=date(2026, 2, 27))
        assert "<ul>" in result
        assert "<li>First key point</li>" in result
        assert "<li>Second key point</li>" in result
        # <ul> must be closed before any subsequent paragraph content
        ul_pos = result.index("<ul>")
        ul_close_pos = result.index("</ul>")
        assert ul_pos < ul_close_pos
        assert result.index("Second key point") < ul_close_pos

    def test_star_bullet_rendered_as_ul(self) -> None:
        """_plain_to_html should also convert '* item' lines into <ul><li> elements."""
        digest = "## TL;DR\n\n* Star bullet item\n"
        result = render_html_digest([_make_item()], digest, today=date(2026, 2, 27))
        assert "<ul>" in result
        assert "<li>Star bullet item</li>" in result

    def test_bullets_closed_by_blank_line(self) -> None:
        """A blank line after bullets should close the <ul> before the next paragraph."""
        digest = "- Bullet one\n\nNormal paragraph."
        result = render_html_digest([_make_item()], digest, today=date(2026, 2, 27))
        ul_pos = result.index("<ul>")
        ul_close_pos = result.index("</ul>")
        p_pos = result.index("<p>", ul_close_pos)
        assert ul_pos < ul_close_pos < p_pos
