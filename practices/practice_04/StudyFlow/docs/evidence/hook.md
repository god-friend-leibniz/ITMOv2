# Automatic verification evidence

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
