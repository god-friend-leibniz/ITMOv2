# Course management: observed TDD and verification

Implemented on 2026-10-06 using the installed `tdd` skill at the already authorized public HTTP/HTML and browser boundaries. HTTP tests use temporary SQLite files; browser tests use a real loopback Uvicorn server and installed Chrome. Network-failure tests intercept browser HTTP requests, without mocking application or persistence functions.

## Incremental red → green sequence

Each row was run and observed red before its implementation. The relevant test then passed, with the routine suite checked through the verification handler after each source change.

| Behavior | Observed red | Minimal green change |
| --- | --- | --- |
| Read course by ID | GET returned 404 instead of 200 | Concrete SELECT, coursework function, API route |
| Missing course | GET returned 200/null instead of 404 | Application exception and specified API error mapping |
| Open course details | Browser could not find a course link | List link, detail route, escaped detail template |
| Missing detail page | 404 response was JSON instead of HTML | Readable error page with an All courses link |
| Edit and restart | PATCH returned 405 instead of 200 | Partial update schema, atomic SQL update, route; preserve omitted description and trim name |
| Empty edit | Empty PATCH returned 200 instead of 422 | Reject a patch with no submitted fields |
| Edit in browser | Course name input was absent | Prefilled edit form and shared script submitting PATCH; description clearing and reload |
| Delete and restart | DELETE returned 405 instead of 204 | Atomic SQL deletion and route; repeated deletion returns 404, other course survives |
| Confirm browser deletion | Delete course button was absent | Confirmation names the course, warns about assignments/tasks and irreversibility, supports cancellation, returns to list after success |
| Recover from deletion failure | Delete remained enabled during a pending request | Disable save/delete together; show network or database-busy error, preserve input, restore controls |
| Prevent delete while saving | Delete remained enabled during PATCH | Disable deletion during save, restore after failure |

Final review coverage for already implemented behavior passed immediately: nine invalid-patch cases, missing-course PATCH, description-only clearing without changing the name, and browser edit validation/input preservation. These are regression checks, not additional claimed red/green cycles.

The first full browser run found an ambiguous detail assertion: the description appeared in both the displayed article and the edit textarea. The assertion was scoped to the article. The subsequent full run passed.

## Final verification

- `python3 scripts/verify_after_change.py`: **35 passed, 10 deselected**, pytest exit 0. This is 17 additional routine cases over the first slice.
- `.venv/bin/python -m pytest -q -m browser --browser-channel chrome`: **10 passed, 35 deselected**, exit 0. This is seven additional browser cases. Headless Chrome and its temporary loopback server ran with sandbox escalation.
- `UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.python .tools/bin/uv build --offline`: built wheel and source archive successfully. The local-cache warning was checked: the source archive contains no `.uv-cache` contents.
- Installed the wheel without dependencies into an isolated temporary directory, then ran from outside the source tree using the existing dependency environment. Verified the imported package came from that installation, migrations ran, create/detail/edit/delete worked, changes survived app restart, both new templates loaded, and static JavaScript was available.
- Existing warning: FastAPI's TestClient import emits Starlette's `httpx` deprecation warning. It did not fail verification; dependencies were not changed for this slice.

All verification used temporary databases and left student data intact.

## Hook results and scope

The hook definition and trusted approval were unchanged. This editing runtime did not produce automatic hook feedback or new runtime event metadata. The handler was invoked explicitly after relevant changes, following AGENTS.md's fallback rule. It returned `decision: block` for intentional failing API/HTML behavior tests and exit-0 feedback after implementation; its final summary was **35 passed, 10 deselected**. These manual calls have empty event metadata and are not a new automatic demonstration. Browser tests run explicitly because the hook intentionally selects the routine suite only.

The earlier actual automatic pass → regression → repair evidence remains in [hook.md](hook.md) and [hook-runtime.json](hook-runtime.json). No hook setting was disabled or weakened.

Only implementation step 2 was added. The specification and agent instructions were updated for completion status, current test counts, and the next slice. README and reflection were updated. No domain rule, architecture decision, database schema, glossary, or ADR changed. Assignments and the course-to-assignment cascade remain step 3.
