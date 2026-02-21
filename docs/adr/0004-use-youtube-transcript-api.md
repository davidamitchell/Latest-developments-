# ADR-0004: Use youtube-transcript-api for YouTube Content

Date: 2026-02-21
Status: Accepted

## Context

The pipeline needs to extract text from YouTube videos to feed into Claude for summarisation. Options:

1. **`youtube-transcript-api`** — fetches auto-generated or manually added captions directly from YouTube's internal API, no audio download needed
2. **`yt-dlp` + OpenAI Whisper** — downloads audio, runs local speech-to-text transcription
3. **YouTube Data API v3** — official Google API; returns metadata and captions but requires OAuth or API key with quota limits
4. **`pytube`** — lighter YouTube client; less maintained than `yt-dlp`

## Decision

Use **`youtube-transcript-api`** as the primary method.

Fall back to **`yt-dlp` + `openai-whisper`** (tiny model, CPU) only when no transcript is available, with a warning log. The fallback is implemented in a later slice (Epic 7+) and is optional.

## Consequences

### Positive
- `youtube-transcript-api` requires no API key, no OAuth, and no audio download — it fetches captions in seconds
- Auto-generated captions are available on the vast majority of YouTube videos, especially in the AI/tech space
- No compute cost for transcription in the common case
- No storage needed (no audio files to manage)
- Library is lightweight and actively maintained

### Negative / Trade-offs
- Dependent on YouTube's internal (undocumented) caption endpoint — could break if YouTube changes its API
- No captions available for some videos (live streams, very new uploads, private videos); these are silently skipped in MVP
- Auto-generated captions have errors; quality is lower than Whisper transcription for highly technical content
- Does not handle age-restricted or members-only content

### Neutral
- The fetcher interface is abstracted behind `src/fetchers/youtube.py`; switching to Whisper for all videos is a one-file change
- A future ADR will address Whisper fallback if caption quality proves insufficient
