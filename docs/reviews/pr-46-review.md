# PR #46 Code Review

Skills applied: code-review, swe, tdd, speculation-control
Foundations: SOLID, Google GenAI Python SDK docs, Python stdlib, GoF patterns
Date: 2026-05-05

## CORRECTNESS

**[Critical] Test suite broken: imports from deleted modules**

Location: tests/test_pipeline_stages.py lines 167-377
Problem: TestConceptExtractionStage, TestThemeClassificationStage, TestSummaryExtractionStage, TestMediaIdStage all import from modules replaced by enrich.py in this PR.
Consequence: pytest fails at collection with ImportError. The test suite does not run.
Recommendation: Delete the four dead test classes. Replace with partition-based tests for _parse() directly.

**[Critical] Tests import functions from the wrong module**

Location: tests/test_pipeline_run.py lines 221-308
Problem: TestWriteProcessedJsonl and TestReadProcessedJsonl import write_processed_jsonl and read_processed_jsonl from src.pipeline.run. These are defined in src.models and not re-exported from run.py.
Consequence: ImportError at collection. These tests never run.
Recommendation: Change both imports to: from src.models import write_processed_jsonl, read_processed_jsonl

**[Critical] Bare except Exception swallows programming errors**

Location: enrich.py line 122
Problem: except Exception catches AttributeError, TypeError, KeyError alongside transport errors. The Google GenAI SDK raises google.genai.errors.ClientError (4xx) and google.genai.errors.ServerError (5xx) for transport failures. response.text raises ValueError when finish_reason != STOP — this is documented SDK behaviour, not a transport exception.
Ground: Google GenAI SDK reference: response.text raises ValueError if the response does not contain a valid Part.
Consequence: A bug in _parse is indistinguishable from a quota error in logs. Safety-blocked items are logged as generic failures. Programming bugs are silently swallowed.
Recommendation: Catch only google.genai.errors.ClientError and google.genai.errors.ServerError. Check response.candidates[0].finish_reason before calling response.text. Propagate all other exceptions.

**[High] response.text accessed without checking finish_reason**

Location: enrich.py line 120
Problem: If finish_reason is SAFETY, MAX_TOKENS, or RECITATION, response.text raises ValueError. This is documented SDK behaviour.
Consequence: Responses truncated by max_output_tokens=500 raise and are counted as failures with no indication of cause.
Recommendation: Check finish_reason before accessing .text. Log the specific reason for non-STOP outcomes.

**[High] generate_content config passed as raw dict, not typed SDK object**

Location: enrich.py lines 117-118
Problem: The SDK accepts config: types.GenerateContentConfig. Passing a raw dict is undocumented. Field name mismatches may be silently dropped on SDK version changes.
Ground: Google GenAI SDK reference: client.models.generate_content(model, contents, config: types.GenerateContentConfig).
Consequence: max_output_tokens or system_instruction may be silently ignored. No type checker catches a wrong key.
Recommendation: from google.genai import types; use types.GenerateContentConfig(system_instruction=_SYSTEM_PROMPT, max_output_tokens=500).

## SECURITY

**[Medium] Inconsistent env var access pattern for credentials**

Location: run.py line 170 vs config.py lines 196-200
Problem: run.py uses os.environ.get("GEMINI_API_KEY") or None. config.py provides require_env() for mandatory vars. No documented contract distinguishes optional from required vars.
Consequence: A future caller using require_env("GEMINI_API_KEY") gets RuntimeError rather than graceful degradation.
Recommendation: Add a comment documenting that GEMINI_API_KEY is intentionally optional and naming the degraded-mode behaviour.

## PERFORMANCE

**[Medium] RPM hardcoded, not readable from config**

Location: run.py line 103
Problem: _RateLimiter(rpm=5) is hardcoded. No lever exists to adjust it without a code change. At 5 RPM and 100 items the pipeline blocks for a minimum of 20 minutes.
Consequence: Becomes a production constraint when the free tier is upgraded.
Recommendation: Add gemini_rpm: int = 5 to the pipeline config section. Pass it to _RateLimiter.

## MAINTAINABILITY

**[High] DIP violation: enrich() depends on untyped concrete client**

Location: enrich.py line 99
Problem: client has no type annotation and no Protocol defining the required interface. Per SOLID DIP: high-level modules define and depend on abstractions.
Consequence: Cannot enforce the contract at type-check time. Cannot substitute a different AI provider without modifying enrich. MagicMock in tests provides no contract verification.
Recommendation: Define a typing.Protocol with the generate_content signature. Annotate enrich(item, client: GenerativeModel).

**[High] OCP violation: _build_fetchers requires modification for every new source type**

Location: fetch.py lines 119-185
Problem: Every new source type requires modifying _build_fetchers. Per SOLID OCP: add behaviour by adding new code, not by changing existing code. The if/elif chain already has 8 branches.
Consequence: The function grows unboundedly. Every addition risks breaking existing type dispatch.
Recommendation: Replace the if/elif chain with a registry dict. New types register themselves; _build_fetchers becomes a lookup with no conditionals.

**[Medium] SRP violation: main() has five reasons to change**

Location: run.py lines 151-198
Problem: main() parses args, loads config, sets up logging, reads input, calls process(), merges results, writes output, and determines exit code. Per SOLID SRP: one function, one reason to change.
Consequence: Testing main() requires a full environment fixture.
Recommendation: Extract _merge_and_write(out_path, new_items) and _exit_code(failures, total, api_key_present). main() becomes orchestration only.

**[Medium] Dead config field: YouTubeConfig.max_videos_per_channel never consumed**

Location: config.py line 108; fetch.py lines 97-106
Problem: max_videos_per_channel = 5 is set but never read. _build_fetchers reads e.options.get("max_videos", 5) per channel instead.
Consequence: Setting max_videos_per_channel in sources.yaml has no effect.
Recommendation: Remove the field or wire it as the fallback default in the per-channel max_videos lookup.

**[Medium] max_output_tokens hardcoded in enrich, inconsistent with DigestConfig.max_tokens**

Location: enrich.py line 118; config.py line 53
Problem: Two Gemini call sites use different token limits with no shared config.
Consequence: Config and code diverge silently. No runtime lever to adjust enrichment output quality.
Recommendation: Add enrich_max_output_tokens: int = 500 to the pipeline config section. Pass it as a parameter to enrich.

**[Low] _parse fallbacks are silent**

Location: enrich.py _parse() lines 47-96
Problem: Every missing or invalid field falls back to a default with no log. Only THEME gets a debug log.
Consequence: Silent degradation in processed output.
Recommendation: Log at debug for each field that falls back to a default.

## TDD

**[High] _parse() has zero direct tests; only mock-mediated coverage**

Location: tests/test_pipeline_stages.py TestEnrich
Problem: _parse() is the primary logic unit of enrich.py. TestEnrich mocks the API client and tests only ok=True/ok=False. _parse is never called with real string inputs.
Ground: tdd skill: use real code, not mocks, unless the dependency is external. _parse takes a str and returns a dict with no external dependency.
Consequence: Bugs in field parsing pass all tests.

Required partitions not covered:
- All fields missing (empty response)
- IMPACT unrecognised value should default to unknown
- CONFIDENCE non-float string should default to 0.0
- CONFIDENCE outside 0.0-1.0 should clamp
- SUMMARY containing a colon mid-sentence should not split on inner colon
- ACTORS: none should produce [] not ["none"]
- CONCEPTS with 6 items (over stated max of 5) — behaviour undefined

## ROOT CAUSE ANALYSIS

These address the class of problem, not individual instances.

Root cause 1: AI defaults to except Exception without consulting the library exception hierarchy.
Class of problem: AI generates the shape of correct code without the domain knowledge to fill it correctly.

Root cause 2: AI does not execute the test suite; it generates code. When AI refactors N modules into 1 it does not audit the suite for broken imports.
Class of problem: AI completion is not AI verification.

Root cause 3: AI uses raw dicts where typed SDK objects are required. Training data contains both styles; without an explicit instruction AI defaults to dicts.
Class of problem: AI generates plausible-looking code from pattern frequency, not from provider API contracts.

Root cause 4: AI duplicates magic numbers when config is not explicitly threaded across components.
Class of problem: AI has local context, not global architectural context.

Root cause 5: AI under-covers failure partitions in tests. Tests mirror the implementation rather than adversarial inputs.
Class of problem: AI tests confirm what the code does, not what it should do under adversarial inputs.

## HARNESS IMPROVEMENTS — THIS REPO

These changes belong in the AI instructions in this repository.

1. Add pytest --collect-only to the Done checklist.
After any refactor that deletes or renames a module, pytest --collect-only must produce zero errors before any tests run.
Addresses root cause 2.

2. Add typed SDK objects requirement to Python code standards.
Use typed SDK objects for external library configuration. Verify the expected parameter type from the library API reference before implementing.
Addresses root cause 3.

3. Add swe pre-implementation checklist gate for integration code.
Before writing code that calls an external library or API, complete the integration-point and failure-mode checks in .github/skills/swe/SKILL.md section 6.1.
Addresses root causes 1 and 4.

4. Add partition testing reference to test standards.
Apply partition testing as defined in .github/skills/tdd/SKILL.md. Every function with conditional logic over its inputs requires partitions for: typical value, boundary, empty/zero, and invalid/malformed.
Addresses root cause 5.

## HARNESS IMPROVEMENTS — SKILLS SUBMODULE

These changes require a separate PR to davidamitchell/Skills.

5. code-review/SKILL.md section 1.1 — add explicit exception hierarchy check.
For every except clause, verify the caught type against the library published exception hierarchy. except Exception requires explicit justification.
Addresses root cause 1.

## SUMMARY

| Severity | Count |
|----------|-------|
| Critical | 3     |
| High     | 5     |
| Medium   | 4     |
| Low      | 1     |
| Total    | 13    |

The batching optimisation is correct in concept. Three critical defects make the test suite non-functional. Five high-severity defects are grounded in SDK misuse and SOLID violations. Four harness improvements belong in this repo. One improvement requires a PR to the Skills submodule.