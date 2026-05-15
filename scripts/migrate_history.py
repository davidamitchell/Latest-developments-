"""One-off migration: seed data/processed/ from history/*.txt files.

Parses all 61 history plain-text digests and writes one
data/processed/YYYY-MM-DD.jsonl per day containing ProcessedItem records.

Three history file formats are handled:

  Format A (early, ~2026-03-03):
    ### Title
    Source: Name [Type]
    URL: https://...
    Theme: ...
    Summary: ...

  Format B (most common, section headers):
    ## Source Name
    ### Title
    Source: Name [Type]   (optional)
    URL: https://...      (optional)
    Theme: ...
    Summary: ...
    ## Item Themes        (optional — URL | Theme pairs at end)
    ## Item Summaries     (optional — URL | Summary pairs at end)

  Format C (AI failure days):
    [AI summarisation failed: ...]
    ## Source Name
    - Title (date)
      https://url
    (no theme or summary)

Items without themes are written with theme="" — they appear in items.json
drill-down but are excluded from trend metrics (items_to_entries filters them).

Run:
    python scripts/migrate_history.py [--history-dir history] [--out-dir data/processed] [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import html
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# ── repo root on sys.path so we can import from src ──────────────────────────
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from src.models import ProcessedItem, write_processed_jsonl  # noqa: E402

# ── source metadata lookup ────────────────────────────────────────────────────

_SOURCE_META: dict[str, dict] = {
    "nate jones": {"source_type": "youtube", "source_class": "practitioner"},
    "wes roth": {"source_type": "youtube", "source_class": "practitioner"},
    "matthew berman": {"source_type": "youtube", "source_class": "practitioner"},
    "hacker news": {"source_type": "hackernews", "source_class": "practitioner"},
}


def _source_meta(name: str) -> dict:
    return _SOURCE_META.get(name.lower(), {"source_type": "rss", "source_class": "practitioner"})


# ── URL / ID helpers ──────────────────────────────────────────────────────────


def _extract_id(url: str) -> str:
    """Extract a short canonical ID from a URL."""
    if not url:
        return ""
    parsed = urlparse(url)
    if "youtube.com" in parsed.netloc:
        qs = parse_qs(parsed.query)
        return qs.get("v", [""])[0]
    if "youtu.be" in parsed.netloc:
        return parsed.path.lstrip("/")
    if "news.ycombinator.com" in parsed.netloc:
        qs = parse_qs(parsed.query)
        return qs.get("id", [""])[0]
    # For RSS/blog URLs use the full URL as ID
    return url


def _synthetic_id(fetch_date: str, source_name: str, title: str) -> str:
    key = f"{fetch_date}:{source_name}:{title}"
    return "hist-" + hashlib.sha256(key.encode()).hexdigest()[:12]


# ── parsed item intermediate ──────────────────────────────────────────────────


@dataclass
class _RawItem:
    fetch_date: str
    source_name: str
    title: str
    url: str = ""
    theme: str = ""
    summary: str = ""

    def item_id(self) -> str:
        extracted = _extract_id(self.url)
        return extracted or _synthetic_id(self.fetch_date, self.source_name, self.title)

    def to_processed(self) -> ProcessedItem:
        meta = _source_meta(self.source_name)
        return ProcessedItem(
            id=self.item_id(),
            title=html.unescape(self.title),
            url=self.url,
            source_name=self.source_name,
            source_type=meta["source_type"],
            source_class=meta["source_class"],
            author="",
            published=None,
            has_code=False,
            evidence_type="analysis",
            fetch_date=self.fetch_date,
            cleaned_content=self.summary,
            theme=self.theme,
            summary=self.summary,
        )


# ── format-specific parsers ───────────────────────────────────────────────────


def _is_failure_file(lines: list[str]) -> bool:
    return any("AI summarisation failed" in line for line in lines[:5])


def _parse_format_c(lines: list[str], fetch_date: str) -> list[_RawItem]:
    """Format C: failure files — extract title+URL from bullet lines."""
    items: list[_RawItem] = []
    current_source = ""
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        # Section header
        if line.startswith("## ") and not line.startswith("## Item"):
            section = line[3:].strip()
            if section not in (
                "Suggested Sources",
                "TL;DR",
                "Trends",
                "Item Summaries",
                "Item Themes",
            ):
                current_source = section
        # Bullet item: "- Title (date)"
        elif line.startswith("- ") and current_source:
            title = re.sub(r"\s*\(\d{1,2}\s+\w+\)\s*$", "", line[2:].strip())
            url = ""
            # Next line may be the URL
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line.startswith("http"):
                    url = next_line
                    i += 1
            if title:
                items.append(
                    _RawItem(
                        fetch_date=fetch_date,
                        source_name=current_source,
                        title=title,
                        url=url,
                    )
                )
        i += 1
    return items


def _parse_format_ab(lines: list[str], fetch_date: str) -> list[_RawItem]:
    """Format A/B: items as ### headings with Source/URL/Theme/Summary fields.

    Also picks up URL→theme and URL→summary from the ## Item Themes /
    ## Item Summaries sections and back-fills matching items.
    """
    items: list[_RawItem] = []
    current_source = ""

    # Collect URL→theme and URL→summary overrides from end sections
    url_theme: dict[str, str] = {}
    url_summary: dict[str, str] = {}
    in_item_themes = False
    in_item_summaries = False
    for line in lines:
        line = line.rstrip()
        if line.startswith("## Item Themes"):
            in_item_themes = True
            in_item_summaries = False
            continue
        if line.startswith("## Item Summaries"):
            in_item_summaries = True
            in_item_themes = False
            continue
        if line.startswith("## "):
            in_item_themes = False
            in_item_summaries = False
        if in_item_themes and line.startswith("- "):
            parts = line[2:].split(" | ", 1)
            if len(parts) == 2:
                url_theme[parts[0].strip()] = parts[1].strip()
        if in_item_summaries and line.startswith("- "):
            parts = line[2:].split(" | ", 1)
            if len(parts) == 2:
                url_summary[parts[0].strip()] = parts[1].strip()

    # Parse items
    skip_sections = {"suggested sources", "tl;dr", "trends", "item themes", "item summaries"}

    current: _RawItem | None = None

    def _flush():
        nonlocal current
        if current is not None:
            items.append(current)
        current = None

    for line in lines:
        line_s = line.rstrip()

        # Section headers (##)
        if line_s.startswith("## ") and not line_s.startswith("### "):
            _flush()
            section = line_s[3:].strip()
            if section.lower() not in skip_sections:
                current_source = section
            continue

        # Separator (---) — no action needed
        if line_s.strip() == "---":
            continue

        # Item header (###)
        if line_s.startswith("### "):
            _flush()
            title = line_s[4:].strip()
            current = _RawItem(
                fetch_date=fetch_date,
                source_name=current_source,
                title=title,
            )
            continue

        if current is None:
            continue

        # Field lines within an item
        if line_s.startswith("Source: "):
            # Extract source name from "Name [Type]" format
            m = re.match(r"Source:\s*(.+?)\s*\[", line_s)
            if m:
                current.source_name = m.group(1).strip()
        elif line_s.startswith("URL: "):
            current.url = line_s[5:].strip()
        elif line_s.startswith("Theme: "):
            current.theme = line_s[7:].strip()
        elif line_s.startswith("Summary: "):
            current.summary = line_s[9:].strip()

    _flush()

    # Build reverse theme→url for items missing URLs
    theme_to_url: dict[str, str] = {v: k for k, v in url_theme.items() if v}

    # Back-fill URL/theme/summary
    for item in items:
        if item.url:
            if item.url in url_theme and not item.theme:
                item.theme = url_theme[item.url]
            if item.url in url_summary and not item.summary:
                item.summary = url_summary[item.url]
        elif item.theme and item.theme in theme_to_url:
            # Back-fill URL from Item Themes lookup (best effort — first match wins)
            item.url = theme_to_url[item.theme]

    return items


def parse_history_file(path: Path) -> list[_RawItem]:
    """Parse a single history file into _RawItem list."""
    fetch_date = path.stem  # e.g. "2026-05-01"
    lines = path.read_text(encoding="utf-8").splitlines()
    if _is_failure_file(lines):
        return _parse_format_c(lines, fetch_date)
    return _parse_format_ab(lines, fetch_date)


# ── deduplication ─────────────────────────────────────────────────────────────


def _deduplicate(items: list[_RawItem]) -> list[_RawItem]:
    """Remove duplicate IDs within a single day's items, keeping first seen."""
    seen: set[str] = set()
    result: list[_RawItem] = []
    for item in items:
        iid = item.item_id()
        if iid and iid not in seen:
            seen.add(iid)
            result.append(item)
    return result


# ── main ──────────────────────────────────────────────────────────────────────


def migrate(history_dir: Path, out_dir: Path, dry_run: bool = False) -> None:
    history_files = sorted(history_dir.glob("*.txt"))
    if not history_files:
        print(f"No history files found in {history_dir}", file=sys.stderr)
        return

    total_items = 0
    total_files = 0

    for hist_file in history_files:
        raw_items = parse_history_file(hist_file)
        raw_items = _deduplicate(raw_items)
        if not raw_items:
            print(f"  {hist_file.name}: 0 items — skipping")
            continue

        processed = [r.to_processed() for r in raw_items]
        out_path = out_dir / f"{hist_file.stem}.jsonl"

        if dry_run:
            print(f"  [dry-run] {hist_file.name}: {len(processed)} items → {out_path}")
        else:
            # Don't overwrite if already populated (today's real run)
            if out_path.exists() and out_path.stat().st_size > 0:
                print(f"  {hist_file.name}: {out_path} already exists — skipping")
                continue
            write_processed_jsonl(processed, out_path)
            print(f"  {hist_file.name}: wrote {len(processed)} items → {out_path}")

        total_items += len(processed)
        total_files += 1

    print(
        f"\nDone: {total_files} file(s), {total_items} item(s) total"
        + (" [dry-run]" if dry_run else "")
    )


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Migrate history/*.txt → data/processed/*.jsonl")
    p.add_argument("--history-dir", default="history", help="Source directory of .txt digests")
    p.add_argument("--out-dir", default="data/processed", help="Destination for .jsonl files")
    p.add_argument("--dry-run", action="store_true", help="Print plan without writing files")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    migrate(
        history_dir=Path(args.history_dir),
        out_dir=Path(args.out_dir),
        dry_run=args.dry_run,
    )
