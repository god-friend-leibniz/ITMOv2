# Automatic verification evidence

This document records the original fast PostToolUse demonstration. The later synchronous Stop gate, installed lifecycle schema, trust review, and actual browser-failure → continuation → repair demonstration are in [final-hook.md](final-hook.md). The PostToolUse definition and trusted hash below remain unchanged. The current routine suite has 44 tests and the browser suite has 10 tests.

Runtime: Codex CLI 0.160.1 on macOS; project Python 3.12.15. The project definition is [.codex/hooks.json](../../.codex/hooks.json), with the handler in [verify_after_change.py](../../scripts/verify_after_change.py).

The user explicitly confirmed trust for the hook. The runtime initially still reported `untrusted`; after persisting that approval for the exact returned hash through Codex's configuration API, `hooks/list` returned `enabled: true`, `trustStatus: trusted`, and no configuration errors. The approved definition hash was `sha256:11a11971cdc9b12d1a03cf1249c23a1abed52255bebe0be83b3f301239ea20d0`. Trust is machine-local and is deliberately absent from committed project configuration.

The already-running editing session did not load this newly created hook. Its verification calls were explicit invocations and are not represented as automatic. Automatic execution was verified in three fresh Codex runtimes using a local deterministic Responses fixture that replayed a fixed shell edit, followed by a final message. No live model/API request or delegated development work was involved; the actual Codex tool dispatcher and hook engine executed the edits and the hook. The fixture's unimplemented model-catalog endpoint produced a metadata warning, which did not prevent tool or hook execution.

The runtime supplied `PostToolUse` input with `tool_name: Bash`, session/turn IDs, and a tool-use ID. The handler ran synchronously, before the following fixture request. Sanitized original run records are in [hook-runtime.json](hook-runtime.json).

| UTC time | Runtime edit | Actual hook outcome |
| --- | --- | --- |
| 2026-10-06 16:12:54 | Add an unused CSS probe file under watched source | Exit 0: 16 passed, 3 browser tests deselected |
| 2026-10-06 16:13:36 | Change POST course creation from 201 to 200 | Exit 1: `test_created_course_appears_in_course_list` failed; 15 passed. The next tool response was replaced with “StudyFlow verification failed. Repair failing tests before unrelated work.” |
| 2026-10-06 16:13:58 | Restore 201 and remove the probe file | Exit 0: 16 passed, 3 browser tests deselected |

The regression and probe file were removed. Later behavior tests increased the routine suite to 18 tests. The handler's command tests also cover document-only skip, new/deleted files, repeated failure feedback, missing environment, timeout, no tests, corrupt state, and concurrent events. Full local verification output and its current state are ignored under `data/verification/`.

To run in another workspace: start Codex from the StudyFlow directory, inspect/review this exact definition in `/hooks`, and trust it in that runtime. Check the journal for a genuine runtime event after the next source edit. `python3 scripts/verify_after_change.py --force` verifies manually and updates the stored result; it does not demonstrate automatic invocation.

## MCP slice update, 2026-10-07

The definition/trust stayed unchanged. Automatic PostToolUse dispatch was not observed in the editing session; explicit handler calls supplied red → green feedback as documented in [sixth-slice.md](sixth-slice.md). The last source-change check passed 216 routine tests, excluding 53 browser cases. Empty event metadata identifies these as manual invocations. A separate fresh MCP runtime did automatically execute Stop; see [mcp-runtime.json](mcp-runtime.json). Earlier automatic fast failure/repair evidence above remains historical and intact.

The subsequent authenticated live retry changed only environment/evidence/documentation, leaving the fast source fingerprint unchanged. Its fresh runtime again automatically executed Stop with all checks passing, captured in [mcp-authenticated-runtime.json](mcp-authenticated-runtime.json). No additional automatic fast test run is claimed for this documentation-only follow-up.

## Final review update, 2026-10-07

The unchanged trusted hook ran automatically in a fresh Codex 0.160.1 runtime. A temporary course POST status change from 201 to 200 produced **2 failed / 216 passed / 53 deselected**, exit 1, at `15:50:21 UTC`; feedback reached the next fixture request. Exact repair produced **218 passed / 53 deselected**, exit 0, at `15:51:38 UTC`. [Original runtime events](final-review-runtime.json) contain genuine PostToolUse session/turn IDs. The same runtime demonstrated Stop blocking continuation and green repair, then completed; see [seventh-slice.md](seventh-slice.md). The temporary regression was removed.

The two new behavior tests followed observed reds/greens through explicit editing-session handler fallback, preserved separately in [final-review-tdd.json](final-review-tdd.json). They are not claimed as automatic PostToolUse events. All earlier records remain historical evidence; definitions and trust were not changed.
