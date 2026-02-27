"""Google Gemini summarisation, with a plain link-digest fallback."""

from __future__ import annotations

import html as _html
import logging
import os
import re
from datetime import UTC, date, datetime

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from src.config import SummaryConfig
from src.fetchers import FetchedItem

logger = logging.getLogger(__name__)

_DEFAULT_PROMPT = (
    "Summarise the following AI/ML content for a senior software engineer who follows"
    " the space closely. Be concise and technical. For each item, write:\n"
    "Theme: [1–3 word label, e.g. 'inference cost', 'agentic RAG', 'fine-tuning']\n"
    "Summary: [2–4 sentences: what it is, why it matters, one concrete takeaway]"
)

_ITEM_HEADER = "### {title}\nSource: {source} [{source_type}]\nURL: {url}\n\n"

# Source type → display emoji
_SOURCE_EMOJI: dict[str, str] = {
    "YouTube": "📺",
    "Hacker News": "🔶",
    "RSS": "📰",
    "Substack": "📧",
}

# ---------------------------------------------------------------------------
# HTML email rendering
# ---------------------------------------------------------------------------

_HTML_CSS = """\
body{font-family:Arial,Helvetica,sans-serif;font-size:18px;line-height:1.8;\
letter-spacing:.04em;word-spacing:.1em;background:#f5f0e8;color:#2a2a2a;\
margin:0;padding:0;text-align:left}
.wrap{max-width:680px;margin:0 auto;padding:24px 20px}
.hdr{border-bottom:3px solid #4a7c59;padding-bottom:12px;margin-bottom:24px}
.hdr h1{font-size:22px;color:#2a2a2a;margin:0;letter-spacing:.05em}
.sec{font-size:20px;font-weight:700;color:#4a7c59;\
border-bottom:2px solid #c8d8c0;padding-bottom:6px;\
margin:28px 0 14px;letter-spacing:.04em}
.card{background:#fff;border-left:4px solid #4a7c59;\
padding:14px 16px;margin-bottom:12px;border-radius:0 4px 4px 0}
.card-title{font-size:18px;font-weight:700;margin:0 0 6px}
.card-title a{color:#1a5c96;text-decoration:none}
.badge{display:inline-block;background:#e8f0e8;color:#2a6040;\
border-radius:3px;padding:2px 8px;font-size:14px;font-weight:700;margin-right:8px}
.meta{font-size:15px;color:#555;margin-bottom:8px;line-height:1.5}
.more{font-size:15px;margin-top:6px}
.more a{color:#1a5c96;font-weight:700;text-decoration:none}
.analysis{background:#fffef5;border:1px solid #d8d0b8;\
padding:16px 20px;margin-top:24px;border-radius:4px;\
font-size:17px;line-height:1.9}
.analysis h2{color:#4a7c59;font-size:18px;margin:16px 0 4px}
.analysis h3{color:#2a6040;font-size:16px;margin:14px 0 4px}
.analysis p{margin:0 0 12px;text-align:left}
.runsummary{font-size:14px;color:#666;border-top:1px solid #ccc;\
margin-top:28px;padding-top:12px;line-height:1.7}
"""


def _source_badge(item: FetchedItem) -> str:
    """Return HTML badge text for the item's source type."""
    stype = item.source_type or item.source_name
    emoji = _SOURCE_EMOJI.get(stype, "🔗")
    return f"{emoji} {_html.escape(stype)}"


def _render_item_card(item: FetchedItem) -> str:
    """Render a single FetchedItem as an HTML card."""
    title_esc = _html.escape(item.title)
    url_esc = _html.escape(item.url)
    source_esc = _html.escape(item.source_name)
    badge = _source_badge(item)
    pub = f" &nbsp;·&nbsp; {item.published.strftime('%d %b %Y')}" if item.published else ""
    return (
        '<div class="card">'
        f'<p class="card-title"><a href="{url_esc}">{title_esc}</a></p>'
        f'<div class="meta"><span class="badge">{badge}</span>'
        f"<strong>{source_esc}</strong>{pub}</div>"
        f'<div class="more"><a href="{url_esc}">Find out more →</a></div>'
        "</div>"
    )


def _plain_to_html(text: str) -> str:
    """Convert lightly-formatted plain text (markdown headers + bold) to HTML."""
    out: list[str] = []
    in_p = False

    def _close_p() -> None:
        nonlocal in_p
        if in_p:
            out.append("</p>")
            in_p = False

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            _close_p()
            continue
        # Escape HTML first so user content cannot inject tags.
        # The bold replacement below inserts only literal <strong>…</strong> with
        # already-escaped inner text, so the order is intentionally: escape → replace.
        esc = _html.escape(stripped)
        esc = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc)
        if esc.startswith("### "):
            _close_p()
            out.append(f"<h3>{esc[4:]}</h3>")
        elif esc.startswith("## "):
            _close_p()
            out.append(f"<h2>{esc[3:]}</h2>")
        elif re.match(r"^[=─\-]{4,}$", stripped):
            _close_p()
            out.append("<hr>")
        else:
            if not in_p:
                out.append("<p>")
                in_p = True
            out.append(esc + "<br>")

    _close_p()
    return "\n".join(out)


def render_html_digest(
    items: list[FetchedItem],
    plain_digest: str,
    today: date | None = None,
) -> str:
    """Return a dyslexia-friendly HTML email digest.

    Renders per-item metadata cards (source type, name, link, date) from the
    FetchedItem list, followed by the full AI analysis converted from
    *plain_digest* (which may include the run summary appended by main.py).
    """
    if today is None:
        today = datetime.now(UTC).date()

    date_str = _html.escape(today.strftime("%d %b %Y"))

    # --- Items section ---
    by_source: dict[str, list[FetchedItem]] = {}
    for item in items:
        by_source.setdefault(item.source_name, []).append(item)

    items_html = f'<div class="sec">Today\'s Stories ({len(items)})</div>\n'
    for source, source_items in by_source.items():
        items_html += f'<div class="sec" style="font-size:17px">{_html.escape(source)}</div>\n'
        for item in source_items:
            items_html += _render_item_card(item) + "\n"

    # --- AI analysis section ---
    analysis_html = _plain_to_html(plain_digest)

    content = f"""\
<div class="hdr"><h1>🤖 Daily AI Digest &mdash; {date_str}</h1></div>
{items_html}
<div class="sec">AI Analysis</div>
<div class="analysis">{analysis_html}</div>
"""

    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<style>{_HTML_CSS}</style></head>"
        f'<body><div class="wrap">{content}</div></body></html>'
    )


def _digest_header(today: date) -> str:
    return f"Daily AI Digest — {today.strftime('%d %b %Y')}\n{'=' * 40}\n\n"


def format_link_digest(
    items: list[FetchedItem], config: SummaryConfig, today: date | None = None
) -> str:
    """Plain link-list digest — no AI required."""
    if not items:
        return ""

    if today is None:
        today = datetime.now(UTC).date()

    by_source: dict[str, list[FetchedItem]] = {}
    for item in items:
        by_source.setdefault(item.source_name, []).append(item)

    sections: list[str] = []
    for source, source_items in by_source.items():
        capped = source_items[: config.max_items_per_source]
        block = f"## {source}\n\n"
        for item in capped:
            pub = f" ({item.published.strftime('%d %b')})" if item.published else ""
            block += f"- {item.title}{pub}\n  {item.url}\n"
        sections.append(block.strip())

    return _digest_header(today) + "\n\n".join(sections)


def summarise(items: list[FetchedItem], config: SummaryConfig, today: date | None = None) -> str:
    """
    Return a formatted plain-text digest.

    If config.enabled is False, returns a plain link list without calling Gemini.
    Otherwise groups items by source, sends to the Gemini API, and returns the summary.
    Items are truncated at 12,000 chars before reaching this function by the fetcher.
    """
    if not items:
        return ""

    if not config.enabled:
        logger.info("AI summarisation disabled — producing link digest")
        return format_link_digest(items, config, today)

    if today is None:
        today = datetime.now(UTC).date()

    by_source: dict[str, list[FetchedItem]] = {}
    for item in items:
        by_source.setdefault(item.source_name, []).append(item)

    sections: list[str] = []
    for source, source_items in by_source.items():
        capped = source_items[: config.max_items_per_source]
        block = f"## {source}\n\n"
        for item in capped:
            block += _ITEM_HEADER.format(
                title=item.title,
                source=source,
                url=item.url,
                source_type=item.source_type or source,
            )
            block += item.content + "\n\n"
        sections.append(block.strip())

    user_content = "\n\n---\n\n".join(sections)
    system_prompt = config.prompt.strip() or _DEFAULT_PROMPT

    logger.info("Summarising %d item(s) with %s", len(items), config.model)

    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))
    try:
        response = client.models.generate_content(
            model=config.model,
            contents=user_content,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=config.max_tokens,
            ),
        )
        return _digest_header(today) + response.text
    except genai_errors.APIError as e:
        logger.warning("Gemini API error — falling back to link digest: %s", e)
        header = _digest_header(today)
        notice = (
            f"[AI summarisation failed: {e.__class__.__name__} — "
            f"no model processing was applied. Raw links only.]\n\n"
        )
        link_digest = format_link_digest(items, config, today)
        return header + notice + link_digest[len(header) :]


def format_run_summary(
    source_counts: dict[str, int],
    source_errors: list[str],
    run_ts: datetime | None = None,
) -> str:
    """Return a plain-text pipeline run summary to append at the end of the digest.

    source_counts maps source name → number of new items fetched.
    source_errors is a list of human-readable error strings.
    run_ts is the UTC time the pipeline ran (defaults to now).
    """
    if run_ts is None:
        run_ts = datetime.now(UTC)

    lines: list[str] = [
        "",
        "",
        "─" * 40,
        "Run summary",
        f"  UTC timestamp : {run_ts.strftime('%Y-%m-%d %H:%M:%S')} UTC",
        f"  Total new items: {sum(source_counts.values())}",
        "",
        "  Sources fetched:",
    ]
    for name, count in source_counts.items():
        lines.append(f"    {name}: {count} new item(s)")

    if source_errors:
        lines.append("")
        lines.append("  Errors:")
        for err in source_errors:
            lines.append(f"    ✗ {err}")

    lines.append("─" * 40)
    return "\n".join(lines)
