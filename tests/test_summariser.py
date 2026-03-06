"""Tests for src/summariser.py."""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock, patch

from src.config import SummaryConfig
from src.fetchers import FetchedItem
from src.summariser import (
    _extract_item_summaries,
    _extract_item_teasers,
    _extract_item_themes,
    _extract_synthesis,
    _extract_tldr,
    _extract_trends,
    _filter_ai_slop,
    format_link_digest,
    format_run_summary,
    render_html_digest,
    summarise,
)


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

    def test_today_date_injected_into_system_prompt(self) -> None:
        """The current date must appear in the system prompt so the LLM can anchor partial
        dates in content (e.g. '27 Feb' → 27 February 2026, not February 2027) and treat
        all fetched content as real, current events rather than fictional future scenarios."""
        mock_cls = _mock_client()
        with patch("src.summariser.genai.Client", mock_cls):
            summarise([_make_item()], _make_config(), today=date(2026, 2, 27))

        call_kwargs = mock_cls.return_value.models.generate_content.call_args.kwargs
        system = call_kwargs["config"].system_instruction
        assert "27 February 2026" in system

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
        item = _make_item(id="xyz", title="GPT-5 Released")
        result = render_html_digest([item], "Summary", today=date(2026, 2, 27))
        assert "Find out more" in result
        # Title still links to the item URL
        assert "https://example.com/xyz" in result
        # "Find out more" now points to a Google search for the title
        assert "google.com/search" in result
        assert "GPT-5+Released" in result or "GPT-5%20Released" in result

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


class TestExtractItemThemes:
    def test_parses_url_theme_pairs(self) -> None:
        text = "Some analysis.\n\n## Item Themes\n- https://example.com/v1 | inference cost\n- https://example.com/v2 | agentic RAG\n"
        themes, clean = _extract_item_themes(text)
        assert themes == {
            "https://example.com/v1": "inference cost",
            "https://example.com/v2": "agentic RAG",
        }

    def test_section_removed_from_clean_text(self) -> None:
        text = "Analysis text.\n\n## Item Themes\n- https://example.com/v1 | fine-tuning\n"
        _, clean = _extract_item_themes(text)
        assert "## Item Themes" not in clean
        assert "fine-tuning" not in clean
        assert "Analysis text." in clean

    def test_no_section_returns_original_text(self) -> None:
        text = "Just some analysis with no themes section."
        themes, clean = _extract_item_themes(text)
        assert themes == {}
        assert clean == text

    def test_stops_before_run_summary_separator(self) -> None:
        text = (
            "Analysis.\n\n## Item Themes\n- https://example.com/v1 | inference cost\n"
            "\n────────────────────────────────────────\nRun summary\n"
        )
        themes, clean = _extract_item_themes(text)
        assert "https://example.com/v1" in themes
        assert "Run summary" in clean

    def test_skips_malformed_lines(self) -> None:
        text = "## Item Themes\n- not a valid line\n- https://example.com/v1 | valid theme\n"
        themes, _ = _extract_item_themes(text)
        assert len(themes) == 1
        assert themes["https://example.com/v1"] == "valid theme"

    def test_case_insensitive_header(self) -> None:
        text = "## item themes\n- https://example.com/v1 | open source\n"
        themes, _ = _extract_item_themes(text)
        assert themes["https://example.com/v1"] == "open source"


class TestRenderHtmlDigestThemes:
    def test_theme_badge_shown_on_card(self) -> None:
        """When AI output includes an Item Themes section, the theme badge appears on the card."""
        item = _make_item(id="v1")
        digest = "Analysis text.\n\n## Item Themes\n- https://example.com/v1 | inference cost\n"
        result = render_html_digest([item], digest, today=date(2026, 2, 27))
        assert '<span class="theme-badge">inference cost</span>' in result

    def test_item_themes_section_not_in_analysis(self) -> None:
        """The ## Item Themes section must be stripped from the rendered AI Analysis."""
        item = _make_item(id="v1")
        digest = "Analysis.\n\n## Item Themes\n- https://example.com/v1 | agentic RAG\n"
        result = render_html_digest([item], digest, today=date(2026, 2, 27))
        assert "## Item Themes" not in result

    def test_no_theme_badge_when_url_not_matched(self) -> None:
        """Item cards without a matching URL in themes section have no theme badge."""
        item = _make_item(id="v1")
        digest = "Analysis.\n\n## Item Themes\n- https://example.com/other | some theme\n"
        result = render_html_digest([item], digest, today=date(2026, 2, 27))
        # The CSS contains the class name; check no span element with that class is present.
        assert '<span class="theme-badge">' not in result

    def test_theme_html_escaped(self) -> None:
        """Theme labels are HTML-escaped before insertion into the card."""
        item = _make_item(id="v1")
        digest = "## Item Themes\n- https://example.com/v1 | <script>xss</script>\n"
        result = render_html_digest([item], digest, today=date(2026, 2, 27))
        assert "<script>" not in result
        assert "&lt;script&gt;" in result


class TestExtractItemSummaries:
    def test_parses_url_summary_pairs(self) -> None:
        text = (
            "Analysis.\n\n## Item Summaries\n"
            "- https://example.com/v1 | First summary sentence. Second sentence.\n"
            "- https://example.com/v2 | Another summary here.\n"
        )
        summaries, clean = _extract_item_summaries(text)
        assert summaries == {
            "https://example.com/v1": "First summary sentence. Second sentence.",
            "https://example.com/v2": "Another summary here.",
        }

    def test_section_removed_from_clean_text(self) -> None:
        text = "Analysis.\n\n## Item Summaries\n- https://example.com/v1 | Summary text.\n"
        _, clean = _extract_item_summaries(text)
        assert "## Item Summaries" not in clean
        assert "Summary text." not in clean
        assert "Analysis." in clean

    def test_no_section_returns_original(self) -> None:
        text = "Just analysis text with no summaries section."
        summaries, clean = _extract_item_summaries(text)
        assert summaries == {}
        assert clean == text

    def test_skips_malformed_lines(self) -> None:
        text = "## Item Summaries\n- not valid\n- https://example.com/v1 | Valid summary.\n"
        summaries, _ = _extract_item_summaries(text)
        assert len(summaries) == 1
        assert summaries["https://example.com/v1"] == "Valid summary."

    def test_case_insensitive_header(self) -> None:
        text = "## item summaries\n- https://example.com/v1 | A summary.\n"
        summaries, _ = _extract_item_summaries(text)
        assert summaries["https://example.com/v1"] == "A summary."


class TestExtractTldr:
    def test_extracts_tldr_content(self) -> None:
        text = "## TL;DR\n\n- Bullet one.\n- Bullet two.\n\nRecurring theme: agents.\n\n## Next Section\nMore text."
        tldr, clean = _extract_tldr(text)
        assert "Bullet one." in tldr
        assert "Recurring theme: agents." in tldr
        assert "## TL;DR" not in clean
        assert "## Next Section" in clean

    def test_no_tldr_returns_empty_and_original(self) -> None:
        text = "Just analysis with no TL;DR."
        tldr, clean = _extract_tldr(text)
        assert tldr == ""
        assert clean == text

    def test_case_insensitive(self) -> None:
        text = "## tl;dr\n\n- A bullet.\n\n## Other\nContent."
        tldr, _ = _extract_tldr(text)
        assert "A bullet." in tldr

    def test_stops_before_run_summary_separator(self) -> None:
        text = "## TL;DR\n- Key point.\n\n────────────────────────────────────────\nRun summary\n"
        tldr, clean = _extract_tldr(text)
        assert "Key point." in tldr
        assert "Run summary" in clean


class TestFilterAiSlop:
    def test_removes_ai_self_reference(self) -> None:
        text = "As an AI language model, I can summarise this."
        result = _filter_ai_slop(text)
        assert "As an AI" not in result
        assert "I can summarise this." in result

    def test_removes_certainly_opener(self) -> None:
        text = "Certainly! Here is the summary."
        result = _filter_ai_slop(text)
        assert "Certainly" not in result

    def test_removes_it_is_worth_noting(self) -> None:
        text = "It's worth noting that the model improved significantly."
        result = _filter_ai_slop(text)
        assert "worth noting" not in result
        assert "the model improved significantly." in result

    def test_removes_in_conclusion(self) -> None:
        text = "In conclusion, the results are promising."
        result = _filter_ai_slop(text)
        assert "In conclusion" not in result
        assert "the results are promising." in result

    def test_leaves_technical_content_intact(self) -> None:
        text = "GPT-4 achieves 87% on MMLU. The transformer uses 175B parameters."
        result = _filter_ai_slop(text)
        assert "GPT-4 achieves 87% on MMLU" in result
        assert "175B parameters" in result

    def test_collapses_excess_blank_lines(self) -> None:
        text = "Line one.\n\n\n\nLine two."
        result = _filter_ai_slop(text)
        assert "\n\n\n" not in result


class TestRenderHtmlDigestTldr:
    def test_tldr_rendered_at_top_before_items(self) -> None:
        item = _make_item(id="v1")
        digest = "## TL;DR\n\n- Key insight.\n\nRecurring theme: agents.\n\n## Analysis\nContent."
        result = render_html_digest([item], digest, today=date(2026, 2, 27))
        # TL;DR div class appears before the card class in the rendered HTML
        assert 'class="tldr"' in result
        assert 'class="card"' in result
        assert result.index('class="tldr"') < result.index('class="card"')

    def test_tldr_section_removed_from_analysis(self) -> None:
        item = _make_item(id="v1")
        digest = "## TL;DR\n\n- Only bullet.\n\n## Analysis\nReal content."
        result = render_html_digest([item], digest, today=date(2026, 2, 27))
        # TL;DR content should appear in the tldr div, not duplicated in analysis
        assert result.count("Only bullet.") == 1

    def test_no_tldr_section_renders_without_error(self) -> None:
        item = _make_item(id="v1")
        digest = "Just analysis text with no TL;DR section."
        result = render_html_digest([item], digest, today=date(2026, 2, 27))
        assert "<!DOCTYPE html>" in result
        assert "Just analysis text" in result


class TestRenderHtmlDigestItemSummaries:
    def test_item_summary_shown_in_card(self) -> None:
        item = _make_item(id="v1")
        digest = (
            "Analysis.\n\n## Item Summaries\n"
            "- https://example.com/v1 | This model achieves state-of-the-art results.\n"
        )
        result = render_html_digest([item], digest, today=date(2026, 2, 27))
        assert "This model achieves state-of-the-art results." in result
        assert 'class="card-summary"' in result

    def test_item_summaries_section_not_in_analysis(self) -> None:
        item = _make_item(id="v1")
        digest = "Analysis.\n\n## Item Summaries\n- https://example.com/v1 | A summary.\n"
        result = render_html_digest([item], digest, today=date(2026, 2, 27))
        assert "## Item Summaries" not in result

    def test_no_summary_card_when_url_not_matched(self) -> None:
        item = _make_item(id="v1")
        digest = "Analysis.\n\n## Item Summaries\n- https://example.com/other | Different item.\n"
        result = render_html_digest([item], digest, today=date(2026, 2, 27))
        assert 'class="card-summary"' not in result

    def test_summary_html_escaped(self) -> None:
        item = _make_item(id="v1")
        digest = "## Item Summaries\n- https://example.com/v1 | <script>xss</script>\n"
        result = render_html_digest([item], digest, today=date(2026, 2, 27))
        assert "<script>" not in result
        assert "&lt;script&gt;" in result


class TestExtractTrends:
    def test_extracts_trends_content(self) -> None:
        text = "Analysis.\n\n## Trends\n\n- LLMs dominating again.\n- Agents are recurring.\n\n## Next\nMore."
        trends, clean = _extract_trends(text)
        assert "LLMs dominating again." in trends
        assert "Agents are recurring." in trends
        assert "## Trends" not in clean
        assert "## Next" in clean

    def test_no_trends_returns_empty_and_original(self) -> None:
        text = "Just analysis with no trends section."
        trends, clean = _extract_trends(text)
        assert trends == ""
        assert clean == text

    def test_case_insensitive_header(self) -> None:
        text = "## trends\n\n- A bullet.\n\n## Other\nContent."
        trends, _ = _extract_trends(text)
        assert "A bullet." in trends

    def test_stops_before_run_summary_separator(self) -> None:
        text = "## Trends\n- Key trend.\n\n────────────────────────────────────────\nRun summary\n"
        trends, clean = _extract_trends(text)
        assert "Key trend." in trends
        assert "Run summary" in clean

    def test_analysis_text_preserved(self) -> None:
        text = "Pre-analysis.\n\n## Trends\n- Trend one.\n\n## Analysis\nPost-analysis."
        _, clean = _extract_trends(text)
        assert "Pre-analysis." in clean
        assert "Post-analysis." in clean


class TestRenderHtmlDigestTrends:
    def test_trends_section_rendered_when_present(self) -> None:
        item = _make_item(id="v1")
        digest = "## Trends\n\n- LLMs are everywhere again.\n\nAnalysis text."
        result = render_html_digest([item], digest, today=date(2026, 3, 1))
        assert 'class="trends"' in result
        assert "📈 Trends" in result
        assert "LLMs are everywhere again." in result

    def test_trends_section_not_in_analysis_area(self) -> None:
        item = _make_item(id="v1")
        digest = "## Trends\n\n- Recurring theme.\n\nAnalysis text."
        result = render_html_digest([item], digest, today=date(2026, 3, 1))
        assert "## Trends" not in result

    def test_no_trends_div_when_absent(self) -> None:
        item = _make_item(id="v1")
        digest = "Just analysis with no trends section."
        result = render_html_digest([item], digest, today=date(2026, 3, 1))
        assert 'class="trends"' not in result

    def test_trends_appears_before_items(self) -> None:
        item = _make_item(id="v1")
        digest = "## Trends\n\n- Trend here.\n\nAnalysis."
        result = render_html_digest([item], digest, today=date(2026, 3, 1))
        trends_pos = result.index('class="trends"')
        items_pos = result.index('class="card"')
        assert trends_pos < items_pos


class TestSummariseWithHistory:
    def test_history_included_in_system_prompt(self) -> None:
        mock_cls = _mock_client()
        with patch("src.summariser.genai.Client", mock_cls):
            summarise(
                [_make_item()],
                _make_config(),
                today=date(2026, 3, 1),
                history=["old digest one", "old digest two"],
            )

        call_kwargs = mock_cls.return_value.models.generate_content.call_args.kwargs
        system = call_kwargs["config"].system_instruction
        assert "HISTORICAL CONTEXT" in system
        assert "old digest one" in system
        assert "old digest two" in system

    def test_no_history_uses_normal_prompt(self) -> None:
        mock_cls = _mock_client()
        with patch("src.summariser.genai.Client", mock_cls):
            summarise(
                [_make_item()],
                _make_config(),
                today=date(2026, 3, 1),
                history=None,
            )

        call_kwargs = mock_cls.return_value.models.generate_content.call_args.kwargs
        system = call_kwargs["config"].system_instruction
        assert "HISTORICAL CONTEXT" not in system

    def test_empty_history_list_uses_normal_prompt(self) -> None:
        mock_cls = _mock_client()
        with patch("src.summariser.genai.Client", mock_cls):
            summarise(
                [_make_item()],
                _make_config(),
                today=date(2026, 3, 1),
                history=[],
            )

        call_kwargs = mock_cls.return_value.models.generate_content.call_args.kwargs
        system = call_kwargs["config"].system_instruction
        assert "HISTORICAL CONTEXT" not in system

    def test_history_truncated_to_3000_chars(self) -> None:
        long_digest = "x" * 5000
        mock_cls = _mock_client()
        with patch("src.summariser.genai.Client", mock_cls):
            summarise(
                [_make_item()],
                _make_config(),
                today=date(2026, 3, 1),
                history=[long_digest],
            )

        call_kwargs = mock_cls.return_value.models.generate_content.call_args.kwargs
        system = call_kwargs["config"].system_instruction
        assert "…[truncated]" in system
        # The full 5000-char digest must not appear verbatim
        assert "x" * 5000 not in system


class TestExtractItemTeasers:
    def test_parses_url_teaser_pairs(self) -> None:
        text = (
            "Analysis.\n\n## Item Teasers\n"
            "- https://example.com/v1 | The ban signals escalating API enforcement.\n"
            "- https://example.com/v2 | Inference costs just halved again.\n"
        )
        teasers, clean = _extract_item_teasers(text)
        assert teasers == {
            "https://example.com/v1": "The ban signals escalating API enforcement.",
            "https://example.com/v2": "Inference costs just halved again.",
        }

    def test_section_removed_from_clean_text(self) -> None:
        text = "Analysis.\n\n## Item Teasers\n- https://example.com/v1 | A hook.\n"
        _, clean = _extract_item_teasers(text)
        assert "## Item Teasers" not in clean
        assert "A hook." not in clean
        assert "Analysis." in clean

    def test_no_section_returns_original(self) -> None:
        text = "Just analysis text with no teasers section."
        teasers, clean = _extract_item_teasers(text)
        assert teasers == {}
        assert clean == text

    def test_skips_malformed_lines(self) -> None:
        text = "## Item Teasers\n- not valid\n- https://example.com/v1 | Valid teaser.\n"
        teasers, _ = _extract_item_teasers(text)
        assert len(teasers) == 1
        assert teasers["https://example.com/v1"] == "Valid teaser."

    def test_case_insensitive_header(self) -> None:
        text = "## item teasers\n- https://example.com/v1 | A teaser.\n"
        teasers, _ = _extract_item_teasers(text)
        assert teasers["https://example.com/v1"] == "A teaser."

    def test_stops_before_run_summary_separator(self) -> None:
        text = (
            "## Item Teasers\n- https://example.com/v1 | Teaser here.\n"
            "\n────────────────────────────────────────\nRun summary\n"
        )
        teasers, clean = _extract_item_teasers(text)
        assert "https://example.com/v1" in teasers
        assert "Run summary" in clean


class TestExtractSynthesis:
    def test_extracts_synthesis_content(self) -> None:
        text = (
            "Analysis.\n\n## Synthesis\n\nThe items collectively point to rising GPU costs.\n"
            "\n## Next\nMore."
        )
        synthesis, clean = _extract_synthesis(text)
        assert "rising GPU costs" in synthesis
        assert "## Synthesis" not in clean
        assert "## Next" in clean

    def test_no_synthesis_returns_empty_and_original(self) -> None:
        text = "Just analysis with no synthesis section."
        synthesis, clean = _extract_synthesis(text)
        assert synthesis == ""
        assert clean == text

    def test_case_insensitive_header(self) -> None:
        text = "## synthesis\n\nPatterns emerging.\n\n## Other\nContent."
        synthesis, _ = _extract_synthesis(text)
        assert "Patterns emerging." in synthesis

    def test_stops_before_run_summary_separator(self) -> None:
        text = (
            "## Synthesis\nKey signal.\n\n────────────────────────────────────────\nRun summary\n"
        )
        synthesis, clean = _extract_synthesis(text)
        assert "Key signal." in synthesis
        assert "Run summary" in clean


class TestRenderHtmlDigestExpandableSummary:
    def test_teaser_and_summary_renders_details_element(self) -> None:
        item = _make_item(id="v1")
        digest = (
            "Analysis.\n\n"
            "## Item Teasers\n- https://example.com/v1 | Short hook sentence.\n\n"
            "## Item Summaries\n- https://example.com/v1 | Longer medium summary here.\n"
        )
        result = render_html_digest([item], digest, today=date(2026, 2, 27))
        assert "<details" in result
        assert "Short hook sentence." in result
        assert "Longer medium summary here." in result
        assert 'class="card-expand"' in result

    def test_expand_toggle_shows_ellipsis(self) -> None:
        item = _make_item(id="v1")
        digest = (
            "## Item Teasers\n- https://example.com/v1 | Hook.\n\n"
            "## Item Summaries\n- https://example.com/v1 | Medium.\n"
        )
        result = render_html_digest([item], digest, today=date(2026, 2, 27))
        assert "\u2026" in result  # … character inside <summary>

    def test_summary_only_renders_plain_card_summary(self) -> None:
        """Single-sentence summary with no teaser shows inline (no expand control)."""
        item = _make_item(id="v1")
        digest = "Analysis.\n\n## Item Summaries\n- https://example.com/v1 | Plain summary.\n"
        result = render_html_digest([item], digest, today=date(2026, 2, 27))
        assert "Plain summary." in result
        assert 'class="card-summary"' in result
        assert "<details" not in result

    def test_multi_sentence_summary_only_renders_expandable(self) -> None:
        """Multi-sentence summary with no teaser is split: first sentence visible, rest on expand."""
        item = _make_item(id="v1")
        digest = (
            "Analysis.\n\n## Item Summaries\n"
            "- https://example.com/v1 | First sentence. Second sentence here.\n"
        )
        result = render_html_digest([item], digest, today=date(2026, 2, 27))
        assert "First sentence." in result
        assert "Second sentence here." in result
        assert "<details" in result
        assert 'class="card-expand"' in result
        assert "\u2026" in result

    def test_teaser_escaping(self) -> None:
        item = _make_item(id="v1")
        digest = "## Item Teasers\n- https://example.com/v1 | <script>xss</script>\n"
        result = render_html_digest([item], digest, today=date(2026, 2, 27))
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_item_teasers_section_not_in_analysis(self) -> None:
        item = _make_item(id="v1")
        digest = "Analysis.\n\n## Item Teasers\n- https://example.com/v1 | Hook.\n"
        result = render_html_digest([item], digest, today=date(2026, 2, 27))
        assert "## Item Teasers" not in result


class TestRenderHtmlDigestSynthesis:
    def test_synthesis_section_rendered_when_present(self) -> None:
        item = _make_item(id="v1")
        digest = "Analysis text.\n\n## Synthesis\n\nKey cross-cutting signal here.\n"
        result = render_html_digest([item], digest, today=date(2026, 2, 27))
        assert 'class="synthesis"' in result
        assert "🔗 Synthesis" in result
        assert "Key cross-cutting signal here." in result

    def test_synthesis_section_not_in_analysis_area(self) -> None:
        item = _make_item(id="v1")
        digest = "## Synthesis\n\nSome synthesis.\n\nAnalysis text."
        result = render_html_digest([item], digest, today=date(2026, 2, 27))
        assert "## Synthesis" not in result

    def test_no_synthesis_div_when_absent(self) -> None:
        item = _make_item(id="v1")
        digest = "Just analysis with no synthesis section."
        result = render_html_digest([item], digest, today=date(2026, 2, 27))
        assert 'class="synthesis"' not in result

    def test_synthesis_appears_after_analysis(self) -> None:
        item = _make_item(id="v1")
        digest = "Analysis text.\n\n## Synthesis\n\nSynthesis paragraph."
        result = render_html_digest([item], digest, today=date(2026, 2, 27))
        analysis_pos = result.index('class="analysis"')
        synthesis_pos = result.index('class="synthesis"')
        assert analysis_pos < synthesis_pos
