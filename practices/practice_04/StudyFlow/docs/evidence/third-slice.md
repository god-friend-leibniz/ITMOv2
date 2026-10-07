# Assignments: observed TDD and verification

Completed on 2026-10-07 using the installed `tdd` skill at the session's already authorized public HTTP/HTML and browser boundaries. HTTP tests use real temporary SQLite databases. Browser tests use a temporary loopback Uvicorn server and installed Chrome; failure scenarios intercept browser HTTP requests rather than application or persistence internals.

Only implementation step 3 was implemented: assignment create/list/detail/edit/delete, optional calendar dates, empty-checklist progress, and course-to-assignment cascade deletion. Checklist tasks, repository-reference writes, and MCP remain later slices.

## Incremental red → green sequence

Each row below describes an observed failure followed by the minimal implementation and a passing rerun. Relevant source changes were followed by the fast verification handler; browser failures were checked separately because the fast suite excludes browser tests.

| Behavior | Observed red | Minimal green change |
| --- | --- | --- |
| Create and list assignments in their course | POST returned 404 instead of 201 | Assignment migration, concrete insert/list SQL, use cases, routes, and empty progress response |
| Missing parent course | GET assignment list returned 200/empty instead of 404 | Require the parent for listing; creation already returned 404 through its atomic parent-checked insert |
| Trim and validate assignment titles | Untrimmed title; invalid titles produced an incorrect response | Pure title rule called by the strict request schema |
| Optional due date, including past dates and leap day | Due-date input returned 422 as an unknown field | Accepted and persisted the optional date |
| Invalid or noncanonical due dates | Invalid dates were accepted with 201 | Calendar validation and exact YYYY-MM-DD representation |
| Read assignment and reopen application | Detail GET returned 404 | Concrete SELECT, use case, and detail route |
| Missing assignment | Detail GET returned 200/null | Assignment exception and normalized 404 |
| Readable missing assignment page | HTML request returned JSON | Shared readable error template with an Assignment heading |
| Edit with omissions and date clearing | PATCH returned 405 | Partial-update schema, single SQL update preserving omissions and clearing explicit null, API route |
| Reject an empty edit | Empty PATCH returned 200 | Require at least one submitted update field |
| Delete while preserving siblings and parent | DELETE returned 405 | Concrete deletion, use case, and 204 route; repeat returns 404 |
| Create in browser and see empty progress | Empty-state text and assignment form were absent | Course assignment list, labelled form, POST script, visible 0 / 0 · 0% and No tasks |
| Set a visible due date | Due-date field was absent | Date input, request value, and list display |
| Open assignment details | Assignment link was absent | Link, HTML route, escaped detail template, and Back to course navigation |
| Edit assignment in browser | Prefilled input was absent | Edit form and PATCH submission, including clearing description/date |
| Confirm assignment deletion | Delete assignment button was absent | Confirmation names the assignment and warns about tasks/irreversibility; cancellation and successful return to course |
| Preserve form input after validation failure | No visible alert after 422; unconditional reload lost values | Read error response, show field feedback, reload only after success |
| Prevent repeated saves and recover from network failure | Submit remained enabled during the pending request | Pending guard, disable form mutations together, network feedback, restore controls/input |
| Recover from failed deletion | Delete remained enabled during the pending request | Shared pending state, network/database-busy feedback, preserve input and re-enable save/delete |

Review coverage for behavior already present passed immediately and is **not** claimed as extra red/green cycles: course cascade with another course preserved across restart; eleven invalid edits rejecting partial changes; missing-assignment PATCH/DELETE; setting a new date without changing other fields; upgrading an existing version-1 database; and escaping assignment text in list/detail/form output. The existing course-confirmation browser test was extended with a child assignment and the resulting readable 404 page.

An early assignment-detail browser assertion matched both displayed description and prefilled textarea. Scoping it to the displayed article resolved the ambiguity without changing the required behavior.

## Verification results

The explicit final handler `python3 scripts/verify_before_finish.py` completed at **2026-10-07T06:54:14.331401+00:00**, returning `StudyFlow final verification passed` and individual exit-0 results:

| Command | Observed result |
| --- | --- |
| `uv run pytest -q` | **80 passed, 21 deselected**, exit 0 |
| `uv run pytest -q -m browser` | **21 passed, 80 deselected**, exit 0; installed Chrome |
| `uv build` | Wheel and source archive built, exit 0 |

This adds **36 routine cases and 11 browser cases** over the course/hook baseline. Assignment HTTP/HTML cases are in `tests/test_assignments.py`; browser flows and recovery cases are in `tests/test_browser.py`.

Installed the built wheel without dependencies into an isolated temporary directory and ran from outside the source tree using the existing dependency environment. Verified that the imported package came from that installation, both migrations were available, assignment create/edit/read and app restart worked, course deletion cascaded, templates loaded, the new JavaScript was served, and missing assignment HTML was readable. The source archive contained no uv cache files. All app checks used temporary databases; student data was untouched.

The existing FastAPI TestClient/Starlette `httpx` deprecation warning remains. It did not fail either suite; dependencies were not changed for this slice.

## Hook results and design changes

The trusted PostToolUse and Stop definitions were unchanged by this slice. This editing session did not produce automatic dispatch feedback or new runtime event metadata. Following AGENTS.md, the fast handler was invoked explicitly after relevant changes: intentional API/HTML failures returned blocking feedback and repairs returned passing summaries. The last source-change result was **80 passed, 21 deselected**. Browser red/green results came from the separate browser runner.

The final handler was also invoked explicitly and passed all three stages. Its recorded `event` is `{}`, identifying it as a manual fallback rather than an automatic Stop invocation. Existing genuine automatic failure → repair demonstrations remain in [fast-hook evidence](hook.md) and [final-hook evidence](final-hook.md). No hook was disabled, retrusted, or weakened.

`spec.md` and `AGENTS.md` now record step 3 completion, current test counts, the incremental migration state, and checklist tasks as the next slice. README and reflection were updated. The planned assignment schema was added as migration 002; repository columns remain deferred to their specified slice. There was no change to settled domain rules or architecture, and no glossary or ADR change was necessary.
