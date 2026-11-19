# Checklist: observed TDD and verification

Completed on 2026-10-07 with the installed `tdd` skill at the session's previously authorized HTTP/HTML and browser boundaries. Tests use real temporary SQLite files. Browser tests use a temporary loopback Uvicorn server and installed Chrome; network/error tests intercept browser HTTP requests without mocking domain or persistence internals.

Only implementation step 4 was added: task create/list/rename/complete/reopen/delete, derived assignment progress in detail/list/edit responses and browser pages, and cascade deletion through both parents. Repository-reference management and MCP remain later slices.

## Incremental red → green sequence

Each implementation below followed an observed failing behavior test and a passing rerun. The fast verification handler checked the routine suite after relevant edits; browser tests ran separately.

| Behavior | Observed red | Minimal green change |
| --- | --- | --- |
| Create/list incomplete tasks within one assignment | POST returned 404 | Migration 003, concrete insert/list SQL, use cases, request schema, routes; response completion is a boolean |
| Require an existing assignment | Missing-parent GET returned 200/empty | Parent check for listing; creation already used an atomic parent-checked insert |
| Trim and bound task titles | Untrimmed title; invalid titles returned 500 | Pure task-title validation and strict transport validation |
| Count incomplete tasks in assignment progress | Detail returned total 0 after task creation | Indexed counts read with the assignment in a single SQL statement; pure progress calculation |
| Rename and restart | PATCH returned 404 | Partial task schema, atomic concrete update, use case, route, normalized missing-task error |
| Complete one of three tasks | Completion field returned 422 as unknown | Strict boolean patch field and SQL update preserving omitted title; progress becomes 1 / 3, 33% |
| Reject an empty task patch | Empty PATCH returned 200 | Require at least one submitted field |
| Retain progress in assignment-edit responses | Assignment PATCH returned zero progress despite a complete task | Read updated assignment and task counts inside the same mutation transaction |
| Delete and recompute progress | DELETE returned 405 | Concrete delete/use case/204 route; deleting the last task restores empty progress; repeats return 404 |
| Add tasks in the browser | Task title field was absent | Labelled creation form, checklist, POST script, visible progress and reload persistence |
| Complete/reopen using keyboard and mouse | Checkbox changed locally but progress stayed unchanged | Explicit boolean PATCH and reload; course page shows derived progress and No tasks only when empty |
| Rename completed tasks in the browser | Rename field was absent | Prefilled rename form and title-only PATCH, preserving completion |
| Confirm deletion and display an empty checklist | Delete task control was absent | Confirmation naming the task, cancellation, DELETE and reload |
| Show field validation and preserve entered titles | No visible error after 422 | Per-form/row error feedback; keep input and saved records unchanged |
| Prevent repeated saves and recover from network failure | Submit remained enabled while pending | Checklist pending guard, disable mutation controls together, safe error feedback, restore controls and allow retry |
| Recover from failed completion/reopening/deletion | Checkbox remained enabled while pending | Pending guards, network/database-busy feedback, checkbox restoration, preserved rename input, and successful retries |

Review coverage passed immediately for behavior already implemented: 33/66/100 percent progression, repeated completion/reopening, rename and combined edits preserving omitted fields, new incomplete tasks reducing progress, sixteen invalid-write cases, assignment/course cascade with unrelated data preserved after restart, version-2 migration upgrade, duplicate titles at the 200-character limit, and escaped text in checkbox/form/confirmation data. These are regression checks, not additional claimed red/green cycles. Existing browser parent-deletion tests were extended with real child tasks.

The first six-case failure-recovery run reported all six expected pending-control failures but then stalled on unresolved intercepted requests. That runner was interrupted (exit 2, six failures). The test now releases requests in `finally`, retaining every original behavior assertion. A subsequent red case exited normally in 7.54 seconds; after implementation all six passed in 5.56 seconds. This was a test cleanup repair, not a weakened assertion or hook timeout increase.

During green review the checklist received small CSS rules so native checkboxes keep their size and task controls fit the existing responsive page. No additional frontend infrastructure was introduced.

## Final verification

The explicit `python3 scripts/verify_before_finish.py` run completed at **2026-10-07T09:18:50.270232+00:00** and returned `StudyFlow final verification passed`:

| Command | Result |
| --- | --- |
| `uv run pytest -q` | **114 passed, 35 deselected**, exit 0, 10.93 seconds |
| `uv run pytest -q -m browser` | **35 passed, 114 deselected**, exit 0, 16.72 seconds, installed Chrome |
| `uv build` | Wheel and source archive built, exit 0 |

This slice adds **34 routine cases and 14 browser cases**. Task HTTP/HTML behavior is in `tests/test_tasks.py`; browser checklist and recovery behavior is in `tests/test_browser.py`.

Installed the built wheel without dependencies into an isolated temporary directory and ran from outside the source checkout using the existing dependency environment. Verified the import came from that installation, an existing version-2 database upgraded, task create/rename/complete/delete worked, assignment edits retained progress, saved state survived restart, assignment deletion cascaded to tasks, and packaged templates/JavaScript/CSS/migrations were available. The source archive contained no uv cache files. All app checks used temporary databases and left student data untouched.

The existing FastAPI TestClient/Starlette `httpx` deprecation warning remains; it did not fail either suite. Dependencies were unchanged.

## Hook results and documentation

This slice did not change hook definitions or their trusted approvals. Automatic dispatch feedback was not observed in this editing session. The documented explicit fast-handler fallback returned blocking feedback for intentional API failures and passing feedback after repair; its last source-change result was **114 passed, 35 deselected**. Browser red/green feedback came from the separate runner because the fast hook excludes browsers.

The final handler was also invoked explicitly and passed all three stages. Its recorded event metadata is `{}`, so this is manual verification rather than an automatic Stop demonstration. The earlier genuine automatic failure/repair evidence remains in [hook.md](hook.md) and [final-hook.md](final-hook.md). No hook was disabled or weakened.

`spec.md` and `AGENTS.md` now record step 4 completion, current test counts, schema version 3, and repository-reference management as the next slice. README and reflection were updated. The planned task table and index were added in migration 003; no settled domain rule, architecture decision, glossary, or ADR changed. Reading progress in assignment-edit responses completes the existing contract without redesigning it.
