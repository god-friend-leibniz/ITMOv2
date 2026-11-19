# First vertical slice: observed TDD sequence

Implemented on 2026-10-06 using the installed `tdd` skill. The implementation request authorized the specification's HTTP/HTML, browser, and hook command boundaries. HTTP tests use real temporary SQLite files; hook tests invoke the public script in isolated fixture projects; browser tests use a real loopback Uvicorn server and headless Chrome.

| Cycle | Observed red | Minimal green change |
| --- | --- | --- |
| Create/list a course | `test_created_course_appears_in_course_list`: POST returned 404 instead of 201 | Course table migration, parameterized SQL, coursework functions, two API routes |
| Hook feedback (setup interlude before course implementation) | `test_hook_reports_failing_tests_to_agent`: verification script did not exist | Script runs pytest and returns blocking JSON when it fails |
| Hook change detection | Documentation-only edit still reran pytest | Content fingerprint, saved result, skip unchanged successful snapshots; new/deleted test files rerun verification |
| Hook infrastructure failures | Missing environment raised instead of returning feedback; timeout was unbounded by the test's configured deadline | Safe failure feedback, deadline, no-tests failure handling |
| Course home page | GET `/` returned 404 | Server-rendered course list and labelled form; description is escaped |
| Course input validation | Blank/oversized names and descriptions failed as 500, unknown ID was accepted, and built-in validation lacked the specified envelope | Domain name validation and strict public schema with normalized 422 responses |
| Browser creation | Form performed a GET reload and the new course never appeared | Same-origin JSON submission and reload after successful creation |
| Browser validation feedback | Validation error remained invisible | Show error and preserve submitted values |
| Browser request failure | Save button remained enabled during the pending request | Prevent repeat submissions; display network errors and restore the button |
| Concurrent hook events | Both events ran the same verification | Local verification lock |
| SQLite contention | A locked database returned 500 instead of 503 | Recoverable `DATABASE_BUSY` response, without a partial course |
| Corrupt hook state | Script raised a JSON decoding exception | Blocking infrastructure feedback; `--force` can replace invalid saved state |

Every listed failure was run and observed before the corresponding implementation. The course test remained red during the explicitly required hook setup, then went green. Refactoring/review changes were made after the relevant checks were green.

Final commands and counts are maintained in [hook.md](hook.md) and the repository's agent instructions. The browser runner used the already installed Chrome via `--browser-channel chrome`; no browser download was needed. All checks use temporary databases and do not reset student data.
