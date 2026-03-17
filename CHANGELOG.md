# Changelog

All notable changes to this project will be documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- **YouTube transcript proxy support**: `YouTubeFetcher` now reads optional environment
  variables `WEBSHARE_PROXY_USERNAME` + `WEBSHARE_PROXY_PASSWORD` (for Webshare residential
  proxies) or `YOUTUBE_PROXY_URL` (for a generic HTTP/HTTPS proxy) and routes all
  transcript API requests through the configured proxy. This bypasses YouTube's cloud IP
  block on GitHub Actions, enabling full transcript-based summaries instead of falling back
  to the short API description. No proxy → existing fallback behaviour is unchanged.
  See `docs/adr/0016-youtube-transcript-proxy-support.md`.
- `.github/copilot-instructions.md`: unified **Continuous Improvement & Learning** framework (supersedes old Mini-Retro and Continuous Improvement — Always On sections)
- `.github/copilot-instructions.md`: **Chain-of-Thought Reasoning** section with 7 pipeline-specific reasoning steps
- `PROGRESS.md` entry for 2026-03-07 session

### Changed
- `.github/copilot-instructions.md`: replaced "Mini-Retro — After Each Piece of Work" and "Continuous Improvement — Always On" sections with unified **Continuous Improvement & Learning** framework

### Removed
- `.github/copilot-instructions.md`: old "Mini-Retro — After Each Piece of Work" section (superseded by unified framework)
- `.github/copilot-instructions.md`: old "Continuous Improvement — Always On" section (superseded by unified framework)
