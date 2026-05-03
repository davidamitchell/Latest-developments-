"""Stage 2 — Clean.

Strips HTML markup and collapses whitespace to produce cleaned_content.
Input: ProcessedItem + raw content string from the original FetchedItem.
"""

from __future__ import annotations

import dataclasses
import re
import xml.etree.ElementTree as ET

from src.models import ProcessedItem


def _strip_html(text: str) -> str:
    """Remove all HTML tags, returning plain text."""
    try:
        # Wrap in a root element so ElementTree can parse fragments
        root = ET.fromstring(f"<root>{text}</root>")
        return "".join(root.itertext())
    except ET.ParseError:
        # Fallback: strip with regex when the HTML is malformed
        return re.sub(r"<[^>]+>", " ", text)


def _collapse_whitespace(text: str) -> str:
    """Replace any run of whitespace (including newlines) with a single space and strip."""
    return re.sub(r"\s+", " ", text).strip()


def clean(item: ProcessedItem, raw_content: str) -> ProcessedItem:
    """Return item with cleaned_content populated from raw_content."""
    stripped = _strip_html(raw_content)
    cleaned = _collapse_whitespace(stripped)
    return dataclasses.replace(item, cleaned_content=cleaned)
