"""Tests for src/summariser.py."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from src.config import SummaryConfig
from src.fetchers import FetchedItem
from src.summariser import format_link_digest, summarise


def _make_item(
    id: str = "id1",
    title: str = "Test Article",
    source: str = "Test Source",
    content: str = "Some content here",
) -> FetchedItem:
    return FetchedItem(
        id=id,
        title=title,
        url=f"https://example.com/{id}",
        content=content,
        source_name=source,
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

        # Should fall back cleanly — no exception, contains the item
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
