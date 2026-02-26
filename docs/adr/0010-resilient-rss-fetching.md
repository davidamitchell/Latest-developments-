# ADR-0010: Resilient RSS Fetching — Browser-Like Headers and Fallback URL

**Date:** 2026-02-26
**Status:** Accepted

---

## Context

The RSS fetcher needs to retrieve feed content from third-party hosting platforms (Substack, Ghost, WordPress, etc.). Several of these platforms sit behind Cloudflare or similar CDN/bot-protection layers that inspect HTTP request headers and block requests that don't resemble a real browser.

Initial deployment revealed that `natesnewsletter.substack.com` returns HTTP 403 to requests sent with a minimal or RSS-specific `Accept` header (e.g. `application/rss+xml`). Cloudflare's bot-score heuristics check:

- `User-Agent` — bots typically send `python-httpx/...` or `feedfetcher/...`
- `Accept` — RSS-specific values are a reliable bot signal; browsers send `text/html` first
- `Sec-Fetch-*` headers — absent on non-browser clients; present on Chrome/Firefox
- `Accept-Language`, `Accept-Encoding`, `Connection` — browsers always send these

A second failure mode is a feed URL that permanently changes (301/302 redirect to a new canonical URL, or a 4xx on a stale URL). Without a fallback, the fetcher silently drops the entire feed.

## Decision

### 1. Browser-like HTTP headers for all RSS requests

The fetcher sends a full set of HTTP headers that mirror a Firefox browser making a navigation request:

```
User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0
Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8
Accept-Language: en-US,en;q=0.5
Accept-Encoding: gzip, deflate, br
Connection: keep-alive
Upgrade-Insecure-Requests: 1
Sec-Fetch-Dest: document
Sec-Fetch-Mode: navigate
Sec-Fetch-Site: none
Sec-Fetch-User: ?1
```

This lowers Cloudflare's bot score sufficiently to allow feed retrieval without requiring a proxy, external service, or Cloudflare bypass token.

### 2. `fallback_url` field in `RSSFeed` config

Each RSS feed entry in `sources.yaml` accepts an optional `fallback_url`. When the primary `url` returns a permanent HTTP error (4xx, excluding 429), the fetcher logs a warning and retries with `fallback_url`. 429 (rate limit) is excluded because it is transient and handled by the existing exponential-backoff retry loop.

## Consequences

### Positive

- Substack and other Cloudflare-protected feeds fetch successfully without any paid proxy or bypass service
- `fallback_url` provides a low-friction way to handle feed URL migrations without breaking the pipeline
- Both strategies degrade gracefully: browser headers are transparent to well-behaved servers; `fallback_url` is only tried when the primary URL fails permanently

### Negative / Trade-offs

- Impersonating a browser in HTTP headers is a grey area in terms of terms of service for some platforms. The pipeline makes at most one request per feed per day, which is far below any reasonable rate limit and mirrors normal subscriber behaviour
- The Firefox User-Agent string will become stale as Firefox versions advance; it may need periodic updating if platforms begin checking for outdated UA strings
- `fallback_url` adds config surface area; operators must keep both URLs correct

### Neutral

- The `_HEADERS` constant is defined once in `src/fetchers/rss.py` and applied to all RSS requests uniformly
- Permanent 4xx errors (other than 429) are raised as `_PermanentHTTPError` and bypass the retry loop; only transient errors (5xx, network timeouts) are retried with backoff
