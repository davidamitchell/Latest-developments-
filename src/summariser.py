"""Google Gemini summarisation, with a plain link-digest fallback."""

from __future__ import annotations

import html as _html
import logging
import os
import re
import time
import urllib.parse
from datetime import UTC, date, datetime
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from src.config import DigestConfig
from src.fetchers import FetchedItem

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).parent.parent / "config"
_TEMPLATES_DIR = Path(__file__).parent / "templates"

# Maximum characters to include from each historical digest when building the
# history context block.  Keeps total token spend bounded even with many days of history.
_MAX_HISTORY_DIGEST_CHARS = 3000

# Load the default prompt from config/prompt.md so it is editable without touching Python.
try:
    _DEFAULT_PROMPT = (_CONFIG_DIR / "prompt.md").read_text().strip()
except OSError as _e:
    raise RuntimeError(
        f"Could not load default prompt from {_CONFIG_DIR / 'prompt.md'}: {_e}"
    ) from _e

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

# CSS and outer HTML frame are loaded from src/templates/ so they can be
# edited without touching Python source.
try:
    _EMAIL_CSS = (_TEMPLATES_DIR / "email.css").read_text().strip()
    _EMAIL_HTML_TEMPLATE = (_TEMPLATES_DIR / "email.html").read_text()
except OSError as _e:
    raise RuntimeError(f"Could not load email template from {_TEMPLATES_DIR}: {_e}") from _e


def _source_badge(item: FetchedItem) -> str:
    """Return HTML badge text for the item's source type."""
    stype = item.source_type or item.source_name
    emoji = _SOURCE_EMOJI.get(stype, "🔗")
    return f"{emoji} {_html.escape(stype)}"


def _render_item_card(
    item: FetchedItem,
    theme: str | None = None,
    summary: str | None = None,
    teaser: str | None = None,
) -> str:
    """Render a single FetchedItem as an HTML card.

    When both *teaser* and *summary* are provided the card shows the teaser with
    a ``(…)`` expand control that reveals the medium summary inline.  When only
    *summary* is provided it is shown directly (legacy / fallback behaviour).
    """
    title_esc = _html.escape(item.title)
    url_esc = _html.escape(item.url)
    source_esc = _html.escape(item.source_name)
    badge = _source_badge(item)
    pub = f" &nbsp;·&nbsp; {item.published.strftime('%d %b %Y')}" if item.published else ""
    theme_html = f' &nbsp;<span class="theme-badge">{_html.escape(theme)}</span>' if theme else ""

    # "Find out more" → Google search for the item title
    search_url = "https://www.google.com/search?" + urllib.parse.urlencode({"q": item.title})
    search_url_esc = _html.escape(search_url)

    if teaser and summary:
        # Expandable: teaser visible; medium summary revealed on click.
        teaser_esc = _html.escape(teaser)
        summary_esc = _html.escape(summary)
        summary_html = (
            f'<div class="card-summary">'
            f"{teaser_esc}"
            f'<details class="card-expand">'
            f"<summary>\u2026</summary>"
            f'<span class="card-summary-full">{summary_esc}</span>'
            f"</details>"
            f"</div>"
        )
    elif teaser:
        summary_html = f'<div class="card-summary">{_html.escape(teaser)}</div>'
    elif summary:
        # No dedicated teaser from AI — split on the first sentence boundary and
        # render the expandable pattern so multi-sentence summaries are always
        # expandable rather than shown as a wall of inline text.
        first, _, rest = summary.partition(". ")
        if rest:
            first_esc = _html.escape(first + ".")
            summary_esc = _html.escape(summary)
            summary_html = (
                f'<div class="card-summary">'
                f"{first_esc}"
                f'<details class="card-expand">'
                f"<summary>\u2026</summary>"
                f'<span class="card-summary-full">{summary_esc}</span>'
                f"</details>"
                f"</div>"
            )
        else:
            summary_html = f'<div class="card-summary">{_html.escape(summary)}</div>'
    else:
        summary_html = ""

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
    item URL to a medium-length summary string and *clean_text* has the section stripped.

    Expected format (one entry per line)::

        - https://example.com/video | Two to three sentence medium summary.

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


def _extract_item_teasers(text: str) -> tuple[dict[str, str], str]:
    """Extract and remove the ``## Item Teasers`` section from AI output.

    Returns ``(url_to_teaser, clean_text)`` where *url_to_teaser* maps each
    item URL to a single-sentence teaser and *clean_text* has the section stripped.

    Expected format (one entry per line)::

        - https://example.com/video | One punchy teaser sentence.

    Lines that do not match the ``<url> | <teaser>`` pattern are silently skipped.
    """
    teasers: dict[str, str] = {}
    pattern = re.compile(
        r"(?:^|\n)\s*## Item Teasers\s*\n(.*?)(?=\n## |\n[─═]{4,}|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return teasers, text

    for line in match.group(1).splitlines():
        stripped = line.strip().lstrip("- ").strip()
        if " | " in stripped:
            url_part, teaser_part = stripped.split(" | ", 1)
            url_part = url_part.strip()
            teaser_part = teaser_part.strip()
            if url_part and teaser_part:
                teasers[url_part] = teaser_part

    start = match.start()
    clean_text = text[:start].rstrip() + text[match.end() :]
    return teasers, clean_text


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


def _extract_trends(text: str) -> tuple[str, str]:
    """Extract and remove the ``## Trends`` section from AI output.

    Returns ``(trends_content, clean_text)`` where *trends_content* is the raw text
    inside the section and *clean_text* has the section stripped.
    """
    pattern = re.compile(
        r"(?:^|\n)\s*## Trends\s*\n(.*?)(?=\n## |\n[─═]{4,}|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return "", text

    trends_content = match.group(1).strip()
    start = match.start()
    clean_text = text[:start].rstrip() + text[match.end() :]
    return trends_content, clean_text


def _extract_synthesis(text: str) -> tuple[str, str]:
    """Extract and remove the ``## Synthesis`` section from AI output.

    Returns ``(synthesis_content, clean_text)`` where *synthesis_content* is the raw text
    inside the section and *clean_text* has the section stripped.
    """
    pattern = re.compile(
        r"(?:^|\n)\s*## Synthesis\s*\n(.*?)(?=\n## |\n[─═]{4,}|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return "", text

    synthesis_content = match.group(1).strip()
    start = match.start()
    clean_text = text[:start].rstrip() + text[match.end() :]
    return synthesis_content, clean_text


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
    item_teasers, display_digest = _extract_item_teasers(display_digest)
    tldr_content, display_digest = _extract_tldr(display_digest)
    trends_content, display_digest = _extract_trends(display_digest)
    synthesis_content, display_digest = _extract_synthesis(display_digest)

    # Apply AI slop filter to the remaining analysis text.
    display_digest = _filter_ai_slop(display_digest)

    # --- TL;DR section at the top ---
    tldr_html = ""
    if tldr_content:
        tldr_html = (
            f'<div class="sec">TL;DR</div><div class="tldr">{_plain_to_html(tldr_content)}</div>\n'
        )

    # --- Trends section (only present when history was used) ---
    trends_html = ""
    if trends_content:
        trends_html = (
            f'<div class="sec">📈 Trends</div>'
            f'<div class="trends">{_plain_to_html(trends_content)}</div>\n'
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
            teaser = item_teasers.get(item.url)
            items_html += (
                _render_item_card(item, theme=theme, summary=summary, teaser=teaser) + "\n"
            )

    # --- AI analysis section ---
    analysis_html = _plain_to_html(display_digest)

    # --- Synthesis section at the bottom ---
    synthesis_html = ""
    if synthesis_content:
        synthesis_html = (
            f'<div class="sec">🔗 Synthesis</div>'
            f'<div class="synthesis">{_plain_to_html(synthesis_content)}</div>\n'
        )

    content = f"""\
<div class="hdr"><h1>🤖 Daily AI Digest &mdash; {date_str}</h1></div>
{tldr_html}
{trends_html}
{items_html}
<div class="sec">AI Analysis</div>
<div class="analysis">{analysis_html}</div>
{synthesis_html}"""

    return _EMAIL_HTML_TEMPLATE.replace("<!--%%CSS%%-->", _EMAIL_CSS).replace(
        "<!--%%CONTENT%%-->", content
    )


def _digest_header(today: date) -> str:
    return f"Daily AI Digest — {today.strftime('%d %b %Y')}\n{'=' * 40}\n\n"


def _build_history_context(history: list[str]) -> str:
    """Build a history context block to append to the system prompt.

    *history* is a list of plain-text digests, newest first.  The block
    instructs Gemini to compare today's content to recent days and add a
    ``## Trends`` section naming recurring topics, emerging threads, and
    notable absences.
    """
    snippets: list[str] = []
    for i, digest in enumerate(history):
        # Truncate each historical digest to avoid blowing the context window.
        truncated = digest[:_MAX_HISTORY_DIGEST_CHARS] + (
            "…[truncated]" if len(digest) > _MAX_HISTORY_DIGEST_CHARS else ""
        )
        snippets.append(f"### Historical digest {i + 1} (most recent first)\n{truncated}")

    history_block = "\n\n".join(snippets)
    return (
        "HISTORICAL CONTEXT (last "
        + str(len(history))
        + " digest(s) for trend comparison — do NOT re-summarise these):\n\n"
        + history_block
        + "\n\nAfter your normal analysis, add a ## Trends section (3–5 bullets) that compares"
        " today's content to the historical context above."
        " Name any recurring topics, emerging threads, and notable absences."
        " If no history is available or the content is too sparse, omit this section."
    )


def format_link_digest(
    items: list[FetchedItem], config: DigestConfig, today: date | None = None
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


def summarise(
    items: list[FetchedItem],
    config: DigestConfig,
    today: date | None = None,
    history: list[str] | None = None,
) -> str:
    """
    Return a formatted plain-text digest.

    If config.enabled is False, returns a plain link list without calling Gemini.
    Otherwise groups items by source, sends to the Gemini API, and returns the summary.
    Items are truncated at 12,000 chars before reaching this function by the fetcher.

    When *history* is provided (a list of recent plain-text digests, newest first),
    it is appended to the system prompt so Gemini can surface trend comparisons.
    """
    if not items:
        return ""

    if not os.environ.get("GEMINI_API_KEY"):
        logger.info("GEMINI_API_KEY not set — producing link digest")
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
    date_context = (
        f"Today's date is {today.strftime('%d %B %Y')}."
        " Each item below is attributed to its source (shown in the 'Source:' field):"
        " a YouTube channel, RSS feed, Hacker News post, or newsletter."
        " Ground all summaries in what that source material states;"
        " attribute claims to their source rather than asserting them as universal facts.\n\n"
    )
    system_prompt = date_context + system_prompt

    if history:
        history_block = _build_history_context(history)
        system_prompt = system_prompt + "\n\n" + history_block
        logger.info("Including %d historical digest(s) as trend context", len(history))

    logger.info("Summarising %d item(s) with %s", len(items), config.model)

    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))
    max_attempts = 4
    backoff_base = 15  # seconds — 15, 30, 60
    last_error: genai_errors.APIError | None = None
    for attempt in range(1, max_attempts + 1):
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
        except genai_errors.ServerError as e:
            # 5xx — transient overload or server error; retry with backoff
            last_error = e
            if attempt < max_attempts:
                wait = backoff_base * (2 ** (attempt - 1))
                logger.warning(
                    "Gemini server error (attempt %d/%d), retrying in %ds: %s",
                    attempt,
                    max_attempts,
                    wait,
                    e,
                )
                time.sleep(wait)
            else:
                logger.warning(
                    "Gemini server error after %d attempts — falling back to link digest: %s",
                    max_attempts,
                    e,
                )
        except genai_errors.ClientError as e:
            # 4xx — bad key, quota, invalid request; no point retrying
            logger.warning("Gemini client error — falling back to link digest: %s", e)
            last_error = e
            break
        except genai_errors.APIError as e:
            # Unknown API error — fall back immediately
            logger.warning("Gemini API error — falling back to link digest: %s", e)
            last_error = e
            break

    header = _digest_header(today)
    err_cls = last_error.__class__.__name__ if last_error else "UnknownError"
    notice = (
        f"[AI summarisation failed: {err_cls} — "
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
