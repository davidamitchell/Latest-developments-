# 0016 — YouTube transcript proxy support

Date: 2026-03-17
Status: accepted

## Context

GitHub Actions runners use cloud/datacenter IP addresses (AWS `us-east-1`). YouTube
actively blocks transcript API requests from these IP ranges. The `youtube-transcript-api`
library raises `IpBlocked` (a subclass of `CouldNotRetrieveTranscript`) for every video
when running in CI. The current fallback uses the brief YouTube Data API `snippet.description`
field — typically 100–200 characters — which is too thin for useful summarisation.

Prior research (`Research/completed/2026-02-28-transcript-via-yt-dlp-whisper.md`) concluded:

- `yt-dlp` audio download is blocked by the same CDN infrastructure as the transcript API;
  the hypothesis that audio and transcript endpoints differ is false.
- Cookie-based auth risks permanent account bans and requires manual periodic maintenance.
- The `youtube-transcript-api` library (`>=1.x`) exposes a first-class `proxy_config`
  parameter on `YouTubeTranscriptApi.__init__()` that routes all transcript requests
  through a user-supplied proxy.
- **Residential rotating proxies** (e.g. Webshare) are not subject to YouTube's cloud IP
  block because they use non-datacenter IP pools.

## Decision

`YouTubeFetcher.__init__()` calls a new helper `_build_proxy_config()` that reads env vars
and returns an appropriate proxy config object:

| Env vars present | Proxy used | Notes |
|---|---|---|
| `WEBSHARE_PROXY_USERNAME` + `WEBSHARE_PROXY_PASSWORD` | `WebshareProxyConfig` | Recommended; Webshare's rotating residential pool |
| `YOUTUBE_PROXY_URL` | `GenericProxyConfig` | Any HTTP/HTTPS proxy URL |
| Neither | `None` | Falls back to API description (existing behaviour) |

Webshare takes priority over a generic URL when both are set.

The chosen approach is **additive and backward-compatible**: existing deployments without
proxy secrets continue to work (description fallback), while operators who add the secrets
get full transcripts.

### Alternatives considered

| Option | Why rejected |
|---|---|
| `yt-dlp` audio + local Whisper | Same CDN block; 72–120 min per video on `ubuntu-latest` CPU even if unblocked |
| Cookie auth | Risks permanent Google account ban; requires manual cookie refresh; youtube-transcript-api disabled cookie support temporarily |
| Third-party transcript SaaS (AssemblyAI, Supadata) | Requires a new paid credential; higher cost; adds a new API dependency |
| Self-hosted runner | Significant operational overhead; outside current scope |

## Consequences

- Transcript fetching works on GitHub Actions when Webshare (or any HTTP proxy) secrets
  are configured.
- No new Python dependency — `youtube_transcript_api.proxies` ships with the existing
  `youtube-transcript-api` package.
- New optional GitHub Secrets: `WEBSHARE_PROXY_USERNAME`, `WEBSHARE_PROXY_PASSWORD`,
  `YOUTUBE_PROXY_URL`. These are optional; existing pipelines are unaffected.
- The fallback to API description remains unchanged for installations without proxy secrets.

## Related

- `docs/adr/0004-use-youtube-transcript-api.md` — original decision to use this library
- `docs/adr/0013-switch-to-youtube-data-api.md` — switch to YouTube Data API for discovery
- `Research/completed/2026-02-28-transcript-via-yt-dlp-whisper.md` — research that ruled out yt-dlp/Whisper
