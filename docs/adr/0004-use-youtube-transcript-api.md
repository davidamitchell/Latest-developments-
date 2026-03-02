# ADR-0004: Use youtube-transcript-api for YouTube Content

Date: 2026-02-21
Status: Partially superseded by ADR-0013 (channel discovery now uses YouTube Data API v3; transcript fetching via this library is unchanged)

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
- `youtube-transcript-api` requires no API key and no audio download — captions are fetched directly in seconds
- Auto-generated captions are available on the vast majority of YouTube videos, especially in the AI/tech space
- No compute cost for transcription; no audio files to store

### Negative / Trade-offs
- Dependent on YouTube's internal (undocumented) caption endpoint; breaking changes are possible without notice
- Live streams, very new uploads, and private videos have no captions and are skipped
- Auto-generated caption quality is lower than Whisper for highly technical content; members-only videos are not accessible

### Neutral
- Channel discovery previously used YouTube's free RSS feed; as of ADR-0013 it uses the YouTube Data API v3 (`search.list`).
- The fetcher interface is abstracted behind `src/fetchers/youtube.py`; switching to Whisper for all videos is a one-file change
- Whisper fallback (for videos without captions) is deferred to a later slice
