"""Tests for src/summariser.py."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from src.config import SummaryConfig
from src.fetchers import FetchedItem
from src.summariser import summarise


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
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 500,
        "max_items_per_source": 5,
        "prompt": "Summarise this.",
    }
    defaults.update(kwargs)
    return SummaryConfig(**defaults)  # type: ignore[arg-type]


def _mock_response(text: str) -> MagicMock:
    content_block = MagicMock()
    content_block.text = text
    response = MagicMock()
    response.content = [content_block]
    return response


class TestSummarise:
    def test_empty_items_returns_empty_string(self) -> None:
        assert summarise([], _make_config()) == ""

    def test_calls_claude_with_model_from_config(self) -> None:
        with patch("src.summariser.anthropic.Anthropic") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.messages.create.return_value = _mock_response("summary")

            summarise([_make_item()], _make_config(model="claude-sonnet-4-6"))

            call_kwargs = mock_client.messages.create.call_args.kwargs
            assert call_kwargs["model"] == "claude-sonnet-4-6"

    def test_returns_digest_with_date_header(self) -> None:
        with patch("src.summariser.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = _mock_response("Claude output")

            result = summarise([_make_item()], _make_config(), today=date(2026, 2, 21))

        assert "21 Feb 2026" in result
        assert "Claude output" in result

    def test_uses_default_prompt_when_config_prompt_empty(self) -> None:
        with patch("src.summariser.anthropic.Anthropic") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.messages.create.return_value = _mock_response("x")

            summarise([_make_item()], _make_config(prompt=""))

            call_kwargs = mock_client.messages.create.call_args.kwargs
            assert len(call_kwargs["system"]) > 0

    def test_groups_items_by_source(self) -> None:
        items = [
            _make_item("a", source="YouTube", content="yt content"),
            _make_item("b", source="Blogs", content="blog content"),
        ]
        with patch("src.summariser.anthropic.Anthropic") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.messages.create.return_value = _mock_response("ok")

            summarise(items, _make_config())

            user_content = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
            assert "YouTube" in user_content
            assert "Blogs" in user_content
            assert "yt content" in user_content
            assert "blog content" in user_content

    def test_respects_max_items_per_source(self) -> None:
        items = [_make_item(str(i), source="S", content=f"content {i}") for i in range(5)]
        with patch("src.summariser.anthropic.Anthropic") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.messages.create.return_value = _mock_response("ok")

            summarise(items, _make_config(max_items_per_source=2))

            user_content = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
            assert "content 0" in user_content
            assert "content 1" in user_content
            assert "content 4" not in user_content
