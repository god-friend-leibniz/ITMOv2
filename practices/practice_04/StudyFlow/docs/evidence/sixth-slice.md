# Useful MCP slice, 2026-10-07

Step 6 is complete, including actual agent discovery and live success/invalid-input/missing-repository calls. The initial unauthenticated attempts hit GitHub rate limits; a user-provided local token enabled the successful retry. [MCP runtime evidence](mcp.md) preserves both outcomes and distinguishes actual calls from deterministic fixtures. Step 7's final coursework review has not been started.

## Behavior and boundaries

The single read-only `get_repository_summary(owner, repo)` tool publishes closed input/output schemas and returns matching structured/JSON-text results. It normalizes identifiers, reads only repository metadata and language byte counts, rejects private repositories, and returns safe validation, missing/moved, rate-limit, authentication, unavailable, and internal errors. GitHub API version `2026-03-10` is pinned; HTTPX is the only production GitHub HTTP boundary.

The application calls the tool over real stdio, validates its response, maps errors to API statuses, forwards an optional server-only token, and enforces a call deadline with child-process cleanup. Summary GETs do not mutate coursework. The assignment panel loads/refreshes explicitly, renders text safely, handles null metadata, preserves input after errors, reports retry delays, and discards old data after reference edits or failed refresh. No summary, status, token, or new database column is persisted.

The installed TDD skill guided work at the user-confirmed boundaries: MCP `tools/list`/`tools/call` with controlled GitHub HTTP, the web route through actual stdio, and browser load/refresh/error behavior. Existing HTTP/HTML/browser boundaries remained in use. Tests exercise real temporary SQLite data and mock external boundaries only.

## Observed red → green sequence

Each row describes a behavior test (including parameterized examples of the same behavior), its observed failure, and the minimum repair. Subsequent behavior work followed green feedback.

| Behavior | Observed red | Green implementation |
| --- | --- | --- |
| Tool discovery and normalized summary | `studyflow_mcp.server` absent | SDK server, schemas, fixed GitHub endpoints, sorted top-three languages |
| Web summary through actual stdio | MCP client module absent | Client, read use case, summary GET and panel-independent response |
| Invalid arguments without HTTP | SDK call raised instead of returning readable failure | Typed `INVALID_INPUT` response |
| Missing/private repository and failed languages request | Exception or incorrect success | Safe not-found error, no partial summary |
| Redirect/rate-limit/auth/server statuses | Upstream body caused exceptions | Explicit safe error codes; no retry or redirect |
| Timeout/connection/malformed upstream data | Exception or accepted invalid summary | Validate metadata/languages and return unavailable |
| Optional token with public-only access | Authorization header absent | Server-only bearer header; private data still rejected |
| Unexpected server exception | Exception escaped the tool | Safe internal error with diagnostics only in stderr |
| Missing repository through web stdio | HTTP 500 | Typed tool failure decoding and HTTP 404 mapping |
| Unlinked assignment | HTTP 500 | HTTP 409 before integration starts |
| Startup/protocol/untrusted tool result | HTTP 500 or accepted unsafe success | Safe 502/422 responses and contract validation |
| Total deadline and child reaping | Timeout option unsupported | Bounded call/startup, HTTP 504, SDK cleanup |
| Explicit browser load/refresh | Load control absent | Conditional panel and explicit fetch |
| Missing repository in browser | Error feedback absent | Recoverable error and reference correction |
| Failed refresh/network/rate limit | Missing error/retry feedback or old summary retained | Clear old summary, restore controls, preserve input |
| Reference changed during pending success/error | Loading state remained | Reference generation tracking and discarded stale response |
| Boolean discriminator / matching text | Integer `ok` and mismatched text accepted | Reject both at the client boundary |
| Secondary rate limit / HTTP retry date | Misclassified 403 and missing delay | Recognize secondary limit and normalize retry dates |
| Token forwarding across stdio | Web HTTP 502 | Explicit token in subprocess environment |
| Missing-assignment summary caching | `Cache-Control` absent | No-store header on that 404 |

Public tool tests are in [test_mcp.py](../../tests/test_mcp.py) (43 cases); real stdio/web tests are in [test_repository_summary.py](../../tests/test_repository_summary.py) (24 cases). Eight new browser cases are in [test_browser.py](../../tests/test_browser.py). Totals rose from 149/45 to **216 routine / 53 browser**.

Review coverage for existing error mappings, additional result-schema cases, nullable metadata, escaped text, reference replacement/removal, and unchanged checklist data passed immediately; these are regression checks, not invented red/green cycles. Strengthening the successful web test to include one completed and one incomplete task initially used the wrong existing response key (`percentage`); fixing it to `percent` repaired the test without changing the application. It now proves the tasks and `50%` progress remain unchanged after fetching.

## Verification and hooks

Hook definitions, timeouts, and trust were preserved. Automatic PostToolUse dispatch was not observed in this editing session; the documented explicit handler fallback ran after relevant edits. Deliberate failures returned `decision: block`; repairs returned passing test summaries. The latest fast handler result was **216 passed, 53 deselected**, exit 0, at `2026-10-07T11:14:26.128194+00:00`; its event metadata is empty, so it is a manual check.

A fresh Codex 0.160.1 runtime used the registered MCP and actually invoked the trusted **Stop** hook. Captured [runtime records](mcp-runtime.json) contain `hook_event_name: Stop`, `stop_hook_active: false`, session/turn IDs, and these command results:

| Command | Actual result |
| --- | --- |
| `uv run pytest -q` | 216 passed, 53 deselected, 21.87 seconds; exit 0 |
| `uv run pytest -q -m browser` | 53 passed, 216 deselected, 31.96 seconds; exit 0 |
| `uv build` | Wheel and source archive built; exit 0 |

Codex emitted `turn.completed` after that automatic gate passed. The initial live-call evidence probe separately failed its success/404 assertions because GitHub rate-limited those requests. After the user supplied a token in ignored `.env`, another fresh runtime passed all three live-call checks and automatically reran Stop: **216 routine / 53 browser / build**, each exit 0. [Authenticated runtime evidence](mcp-authenticated-runtime.json) records the successful summary and actual missing-repository error, plus the final check at `2026-10-07T11:39:39.289119+00:00`. The token remained in process environment and is absent from evidence; `.env` is excluded from distributions. This retry changed no application code/tests and adds no claimed TDD cycle. Earlier genuine fast-hook and final failure → continuation → repair demonstrations remain in [hook.md](hook.md) and [final-hook.md](final-hook.md).

An isolated wheel installation outside the checkout passed coursework/restart/cascade/resource checks and real packaged MCP discovery/invalid-input calls. Initial offline installation could not resolve incomplete cache metadata; retry used exact lockfile constraints and fetched the missing dependency, without changing the lockfile. The existing uv warning about the local cache directory during build remains nonfatal.

## Design and documentation

No domain, persistence, or architecture decision changed; GLOSSARY.md and ADR 0001 are unchanged. The SDK/HTTP client dependencies, packaged MCP module, project-relative Codex registration, and API detail follow the specification. `spec.md`, `AGENTS.md`, README, reflection, and evidence now describe implemented behavior, completed live demonstrations, and explicit `.env` launch commands. No extra skill, general GitHub client, caching service, repository layer, or background refresh was added.
