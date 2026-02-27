"""Google Gemini summarisation, with a plain link-digest fallback."""

from __future__ import annotations

import html as _html
import logging
import os
import re
import urllib.parse
from datetime import UTC, date, datetime

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from src.config import SummaryConfig
from src.fetchers import FetchedItem

logger = logging.getLogger(__name__)

_DEFAULT_PROMPT = (
    "Summarise the following AI/ML content for a senior software engineer who follows"
    " the space closely. Be concise and technical.\n\n"
    "For each item, write:\n"
    "Theme: [1–3 word label, e.g. 'inference cost', 'agentic RAG', 'fine-tuning']\n"
    "Summary: [2–3 sentences: what it is, why it matters, one concrete takeaway]\n\n"
    "After all items, add a ## Suggested Sources section with 2–3 YouTube channels,"
    " newsletters, or blogs that would complement today's content themes and that the"
    " reader is unlikely to already follow. For each, write the name in bold and one"
    " sentence explaining why it is worth following.\n\n"
    "Then add a ## TL;DR section: exactly 3 bullet points (no more), each a single"
    " concise sentence naming the most impactful item and why it matters."
    " Follow with one 'Recurring theme: …' line.\n\n"
    "Finally, add a ## Item Themes section listing each item's URL"
    " and its theme label, one per line, in exactly this format:\n"
    "- <url> | <theme label>\n\n"
    "Also add a ## Item Summaries section listing each item's URL and a one-to-two"
    " sentence summary, one per line, in exactly this format:\n"
    "- <url> | <summary>\n"
    "Use the exact URL from the 'URL:' field provided for each item."
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
# AI slop filter
# ---------------------------------------------------------------------------

_SLOP_PATTERNS: list[re.Pattern] = [
    # AI self-reference
    re.compile(r"\bAs an AI( language model| assistant)?,?\s*", re.IGNORECASE),
    # Conversational openers on their own line
    re.compile(
        r"^(Certainly|Of course|Absolutely|Sure|Great|Indeed)[!,]?\s*",
        re.IGNORECASE | re.MULTILINE,
    ),
    re.compile(
        r"^(I'?d be happy to|I'?m happy to|I would be happy to)\s*",
        re.IGNORECASE | re.MULTILINE,
    ),
    # Filler closers
    re.compile(r"\bI hope (this helps|this is helpful|that helps)\.?\s*", re.IGNORECASE),
    re.compile(
        r"\b(Feel free to ask|Let me know if you have|Don't hesitate to)[^.]*\.\s*",
        re.IGNORECASE,
    ),
    # Generic filler openers
    re.compile(
        r"\bIn today'?s (fast-paced|rapidly changing|ever-changing) (world|landscape)\b[,.]?\s*",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bIn the (ever|rapidly|constantly)[-\s](evolving|changing)"
        r" (field|landscape|world|realm) of\b\s*",
        re.IGNORECASE,
    ),
    # Redundant transition phrases
    re.compile(
        r"\b(That being said|With that said|Having said that|That said)[,.]?\s*",
        re.IGNORECASE,
    ),
    # Note-qualifying fillers
    re.compile(
        r"\bIt'?s (worth noting|important to note|crucial to note|interesting to note) that\s*",
        re.IGNORECASE,
    ),
    re.compile(r"\bPlease note that\s*", re.IGNORECASE),
    # Hollow summary openers (the actual content follows; the opener adds nothing)
    re.compile(
        r"^(In conclusion|To summarize|In summary|To sum up)[,:]?\s*", re.IGNORECASE | re.MULTILINE
    ),
]


def _filter_ai_slop(text: str) -> str:
    """Remove common AI filler phrases from generated text."""
    for pattern in _SLOP_PATTERNS:
        text = pattern.sub("", text)
    # Collapse three or more blank lines left behind by removed content
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# HTML email rendering
# ---------------------------------------------------------------------------

_HTML_CSS = """\
body{font-family:Arial,Helvetica,sans-serif;font-size:17px;line-height:1.7;\
letter-spacing:.03em;word-spacing:.08em;background:#f5f0e8;color:#2a2a2a;\
margin:0;padding:0;text-align:left}
.wrap{max-width:640px;margin:0 auto;padding:16px 12px}
.hdr{border-bottom:3px solid #4a7c59;padding-bottom:10px;margin-bottom:18px}
.hdr h1{font-size:20px;color:#2a2a2a;margin:0;letter-spacing:.04em}
.tldr{background:#eaf4ea;border-left:4px solid #4a7c59;\
padding:12px 14px;margin-bottom:16px;border-radius:0 4px 4px 0;font-size:16px}
.tldr ul{margin:6px 0 4px 18px;padding:0}
.tldr ul li{margin-bottom:4px}
.sec{font-size:18px;font-weight:700;color:#4a7c59;\
border-bottom:2px solid #c8d8c0;padding-bottom:5px;\
margin:22px 0 12px;letter-spacing:.03em}
.card{background:#fff;border-left:4px solid #4a7c59;\
padding:12px 14px;margin-bottom:10px;border-radius:0 4px 4px 0}
.card-title{font-size:17px;font-weight:700;margin:0 0 5px}
.card-title a{color:#1a5c96;text-decoration:none}
.badge{display:inline-block;background:#e8f0e8;color:#2a6040;\
border-radius:3px;padding:2px 6px;font-size:13px;font-weight:700;margin-right:6px}
.meta{font-size:14px;color:#555;margin-bottom:6px;line-height:1.4}
.card-summary{font-size:15px;color:#333;line-height:1.6;margin:6px 0 8px}
.more{font-size:14px;margin-top:4px}
.more a{color:#1a5c96;font-weight:700;text-decoration:none}
.analysis{background:#fffef5;border:1px solid #d8d0b8;\
padding:14px 16px;margin-top:20px;border-radius:4px;\
font-size:16px;line-height:1.8}
.analysis h2{color:#4a7c59;font-size:17px;margin:14px 0 4px}
.analysis h3{color:#2a6040;font-size:15px;margin:12px 0 4px}
.analysis p{margin:0 0 10px;text-align:left}
.runsummary{font-size:13px;color:#666;border-top:1px solid #ccc;\
margin-top:24px;padding-top:10px;line-height:1.6}
.analysis ul{margin:4px 0 10px 18px;padding:0}
.analysis ul li{margin-bottom:4px}
.theme-badge{display:inline-block;background:#f0e8ff;color:#5a2a8a;\
border-radius:3px;padding:2px 6px;font-size:12px;font-weight:700;margin-left:6px}
@media(max-width:480px){
.wrap{padding:10px 8px}
.hdr h1{font-size:18px}
.sec{font-size:16px}
.card{padding:10px 10px}
.card-title{font-size:16px}
.card-summary{font-size:14px}
.analysis{padding:10px 12px;font-size:15px}
}
"""


def _source_badge(item: FetchedItem) -> str:
    """Return HTML badge text for the item's source type."""
    stype = item.source_type or item.source_name
    emoji = _SOURCE_EMOJI.get(stype, "🔗")
    return f"{emoji} {_html.escape(stype)}"


def _render_item_card(
    item: FetchedItem, theme: str | None = None, summary: str | None = None
) -> str:
    """Render a single FetchedItem as an HTML card."""
    title_esc = _html.escape(item.title)
    url_esc = _html.escape(item.url)
    source_esc = _html.escape(item.source_name)
    badge = _source_badge(item)
    pub = f" &nbsp;·&nbsp; {item.published.strftime('%d %b %Y')}" if item.published else ""
    theme_html = f' &nbsp;<span class="theme-badge">{_html.escape(theme)}</span>' if theme else ""

    # "Find out more" → Google search for the item title
    search_url = "https://www.google.com/search?" + urllib.parse.urlencode({"q": item.title})
    search_url_esc = _html.escape(search_url)

    summary_html = f'<div class="card-summary">{_html.escape(summary)}</div>' if summary else ""

    return (
        '<div class="card">'
        f'<p class="card-title"><a href="{url_esc}">{title_esc}</a></p>'
        f'<div class="meta"><span class="badge">{badge}</span>'
        f"<strong>{source_esc}</strong>{pub}{theme_html}</div>"
        f"{summary_html}"
        f'<div class="more"><a href="{search_url_esc}">Find out more →</a></div>'
        "</div>"
    )


def _extract_item_themes(text: str) -> tuple[dict[str, str], str]:
    """Extract and remove the ``## Item Themes`` section from AI output.

    Returns ``(url_to_theme, clean_text)`` where *url_to_theme* maps each item
    URL to its 1–3 word theme label and *clean_text* has the section stripped so
    it does not appear in the rendered analysis.

    The expected format inside the section is one entry per line::

        - https://example.com/video | inference cost

    Lines that do not match the ``<url> | <theme>`` pattern are silently skipped.
    """
    themes: dict[str, str] = {}
    # Match the section header plus everything up to the next ## header,
    # a run-summary separator line (────…), or end-of-string.
    pattern = re.compile(
        r"(?:^|\n)\s*## Item Themes\s*\n(.*?)(?=\n## |\n[─═]{4,}|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return themes, text

    for line in match.group(1).splitlines():
        stripped = line.strip().lstrip("- ").strip()
        if " | " in stripped:
            url_part, theme_part = stripped.split(" | ", 1)
            url_part = url_part.strip()
            theme_part = theme_part.strip()
            if url_part and theme_part:
                themes[url_part] = theme_part

    # Remove the matched section (keep the leading newline so surrounding text
    # still flows correctly).
    start = match.start()
    clean_text = text[:start].rstrip() + text[match.end() :]
    return themes, clean_text


def _extract_item_summaries(text: str) -> tuple[dict[str, str], str]:
    """Extract and remove the ``## Item Summaries`` section from AI output.

    Returns ``(url_to_summary, clean_text)`` where *url_to_summary* maps each
    item URL to a short summary string and *clean_text* has the section stripped.

    Expected format (one entry per line)::

        - https://example.com/video | One to two sentence summary.

    Lines that do not match the ``<url> | <summary>`` pattern are silently skipped.
    """
    summaries: dict[str, str] = {}
    pattern = re.compile(
        r"(?:^|\n)\s*## Item Summaries\s*\n(.*?)(?=\n## |\n[─═]{4,}|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return summaries, text

    for line in match.group(1).splitlines():
        stripped = line.strip().lstrip("- ").strip()
        if " | " in stripped:
            url_part, summary_part = stripped.split(" | ", 1)
            url_part = url_part.strip()
            summary_part = summary_part.strip()
            if url_part and summary_part:
                summaries[url_part] = summary_part

    start = match.start()
    clean_text = text[:start].rstrip() + text[match.end() :]
    return summaries, clean_text


def _extract_tldr(text: str) -> tuple[str, str]:
    """Extract and remove the ``## TL;DR`` section from AI output.

    Returns ``(tldr_content, clean_text)`` where *tldr_content* is the raw text
    inside the section and *clean_text* has the section stripped.
    """
    pattern = re.compile(
        r"(?:^|\n)\s*## TL;DR\s*\n(.*?)(?=\n## |\n[─═]{4,}|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return "", text

    tldr_content = match.group(1).strip()
    start = match.start()
    clean_text = text[:start].rstrip() + text[match.end() :]
    return tldr_content, clean_text


def _plain_to_html(text: str) -> str:
    """Convert lightly-formatted plain text (markdown headers + bold + bullets) to HTML."""
    out: list[str] = []
    in_p = False
    in_ul = False

    def _close_p() -> None:
        nonlocal in_p
        if in_p:
            out.append("</p>")
            in_p = False

    def _close_ul() -> None:
        nonlocal in_ul
        if in_ul:
            out.append("</ul>")
            in_ul = False

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            _close_p()
            _close_ul()
            continue
        # Escape HTML first so user content cannot inject tags.
        # The bold replacement below inserts only literal <strong>…</strong> with
        # already-escaped inner text, so the order is intentionally: escape → replace.
        esc = _html.escape(stripped)
        esc = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc)
        if esc.startswith("### "):
            _close_p()
            _close_ul()
            out.append(f"<h3>{esc[4:]}</h3>")
        elif esc.startswith("## "):
            _close_p()
            _close_ul()
            out.append(f"<h2>{esc[3:]}</h2>")
        elif re.match(r"^[=─\-]{4,}$", stripped):
            _close_p()
            _close_ul()
            out.append("<hr>")
        elif stripped.startswith("- ") or stripped.startswith("* "):
            _close_p()
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{esc[2:]}</li>")
        else:
            _close_ul()
            if not in_p:
                out.append("<p>")
                in_p = True
            out.append(esc + "<br>")

    _close_p()
    _close_ul()
    return "\n".join(out)


def render_html_digest(
    items: list[FetchedItem],
    plain_digest: str,
    today: date | None = None,
) -> str:
    """Return a mobile-friendly HTML email digest.

    Renders a TL;DR section at the top, followed by per-item metadata cards
    (source type, name, link, date, AI summary) grouped by source, and finally
    the full AI analysis converted from *plain_digest*.
    """
    if today is None:
        today = datetime.now(UTC).date()

    date_str = _html.escape(today.strftime("%d %b %Y"))

    # Extract structured sections and remove them from the display digest.
    item_themes, display_digest = _extract_item_themes(plain_digest)
    item_summaries, display_digest = _extract_item_summaries(display_digest)
    tldr_content, display_digest = _extract_tldr(display_digest)

    # Apply AI slop filter to the remaining analysis text.
    display_digest = _filter_ai_slop(display_digest)

    # --- TL;DR section at the top ---
    tldr_html = ""
    if tldr_content:
        tldr_html = (
            f'<div class="sec">TL;DR</div><div class="tldr">{_plain_to_html(tldr_content)}</div>\n'
        )

    # --- Items section ---
    by_source: dict[str, list[FetchedItem]] = {}
    for item in items:
        by_source.setdefault(item.source_name, []).append(item)

    items_html = f'<div class="sec">Today\'s Stories ({len(items)})</div>\n'
    for source, source_items in by_source.items():
        items_html += f'<div class="sec" style="font-size:16px">{_html.escape(source)}</div>\n'
        for item in source_items:
            theme = item_themes.get(item.url)
            summary = item_summaries.get(item.url)
            items_html += _render_item_card(item, theme=theme, summary=summary) + "\n"

    # --- AI analysis section ---
    analysis_html = _plain_to_html(display_digest)

    content = f"""\
<div class="hdr"><h1>🤖 Daily AI Digest &mdash; {date_str}</h1></div>
{tldr_html}
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
