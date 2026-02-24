"""RSS / Atom feed fetcher.

Reads feeds listed in config.blogs.rss, fetches them with httpx,
and parses with stdlib xml.etree.ElementTree.  Supports both RSS 2.0
(<rss>/<channel>/<item>) and Atom 1.0 (<feed>/<entry>).

Deduplication key: the item URL, normalised (trailing slash stripped).
"""
import httpx
import feedparser
from datetime import datetime
from typing import List, Optional
from src.models import FeedConfig, NewsItem
from src.retry import with_backoff

class _PermanentHTTPError(Exception):
    """Exception raised for HTTP errors that should not be retried."""
    pass

def _fetch_url(url: str) -> bytes:
    """Fetch URL content with browser-like headers to avoid 403 Forbidden errors."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.get(url, headers=headers)
        
        # 403 and 404 are usually permanent configuration issues for Substack/RSS
        if response.status_code in (403, 404):
            raise _PermanentHTTPError(
                f"HTTP {response.status_code} fetching '{url}' — not retrying"
            )
            
        response.raise_for_status()
        return response.content

class RSSFetcher:
    def fetch(self, feed_cfg: FeedConfig, already_processed: set[str]) -> List[NewsItem]:
        items = []
        try:
            # Wrap the fetch in the existing backoff logic
            xml_bytes: bytes = with_backoff(
                lambda: _fetch_url(feed_cfg.url),
                label=f"RSS {feed_cfg.name}"
            )
            
            feed = feedparser.parse(xml_bytes)
            
            for entry in feed.entries:
                link = entry.get("link")
                if not link or link in already_processed:
                    continue
                
                # Extract published date
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6])
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    published = datetime(*entry.updated_parsed[:6])
                
                items.append(NewsItem(
                    title=entry.get("title", "No Title"),
                    url=link,
                    source_name=feed_cfg.name,
                    published_at=published,
                    summary=entry.get("summary", "")
                ))
                
        except _PermanentHTTPError as e:
            # Log and skip if it's a known permanent error (like the 403 you saw)
            print(f"Failed to fetch RSS feed '{feed_cfg.url}': {e}")
        except Exception as e:
            print(f"Error processing RSS feed {feed_cfg.name}: {e}")
            
        return items

