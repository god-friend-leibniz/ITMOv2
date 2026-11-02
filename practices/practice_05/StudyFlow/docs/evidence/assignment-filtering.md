# Course assignment completion filtering

Implemented 2026-10-25 for OpenSpec change `filter-assignments-by-completion`. The change remains active; no sync or archive was performed.

## Scope

Only the HTML course list is filtered. The existing derived counts decide completion; an empty checklist remains incomplete. Unknown and empty `completion` values mean All on both HTML pages. Context survives reloads, checklist changes, the Back to course link, and successful assignment deletion. Successful creation under Completed shows a status and a keyboard-operable All link without resetting the mode. Pending and failed requests show no success; a new attempt clears the previous confirmation.

SQLite operations and migrations, domain progress rules, coursework functions, MCP server, dependency definitions, and lockfile are unchanged. JSON endpoints and response schemas are unchanged. Tests use temporary databases and controlled HTTP failures; no live GitHub calls or user-database resets were needed.

## Observed TDD cycles

Each cycle used an HTTP/HTML or browser boundary, followed by the minimal implementation and a passing rerun. Tests of existing behavior passed without introducing an artificial regression.

| Behavior | Observed red | Observed green |
| --- | --- | --- |
| Completed filter | Returned all four local assignments instead of only the completed one | 1 HTTP test passed |
| Incomplete filter | Still included the completed assignment | 2 HTTP tests passed |
| Keyboard control, reload and shared URL | Missing Assignment completion navigation | 1 browser test passed |
| Return after checklist changes | Assignment URL lost the filter | 2 browser cases passed |
| Return after deletion | Returned to the unfiltered course | New case and existing deletion regressions: 4 passed |
| Hidden creation confirmation and All link | Missing success status | 2 browser cases passed |
| First hidden assignment | Kept No assignments yet after saving | 1 browser test passed |
| New attempt and failure recovery | Previous success stayed visible during a pending request | Network case passed, then network/validation/server cases: 3 passed |

Additional checks cover default/invalid filters, course isolation, unchanged JSON list data, missing pages, checklist addition/reopening/deletion, distinct empty states, course editing with no matches, and normal create/edit reloads. Title markup is rendered as text in the confirmation. The All link is activated with the keyboard and reveals only assignments of the same course.

## Actual verification results

Run from StudyFlow using the prepared Python 3.12 environment and existing frozen lockfile:

- Manual fast-handler fallback: `python3 scripts/verify_after_change.py --force` reported pytest exit 0, **232 passed, 66 deselected in 22.21s**.
- Manual final-handler fallback: `python3 scripts/verify_before_finish.py` returned success feedback. Its recorded commands all exited 0:

| Command | Actual result |
| --- | --- |
| `uv run pytest -q` | **232 passed, 66 deselected in 21.27s** |
| `uv run pytest -q -m browser` | **66 passed, 232 deselected in 37.99s**, installed Chrome |
| `uv build` | Built the sdist and wheel successfully |

The final handler supplies frozen/offline uv settings and project-local tooling caches. Chrome and temporary loopback test servers were run outside the filesystem/process sandbox because its restrictions prevent Chrome startup. Manual handler execution does not demonstrate automatic hook dispatch. Raw outputs are in ignored `data/verification/last.json`, `pytest.log`, and `final-last.json`/`final-runs.jsonl`.

Build emitted the existing warning that the project-local `.uv-cache` is inside the source directory. No packaging configuration or cache policy was changed in this feature.

Desktop (1280px) and mobile (390px) screenshots from a disposable preview database were visually inspected: the filter, current mode, assignment card, creation status, and All link remain readable. Screenshots and the implementation diff are session artifacts under `/private/tmp/studyflow-apply-spffrx40/`, not application data.

The explore baseline before implementation was 218 offline tests, 53 browser tests, and a successful build. This change adds 14 offline cases and 13 browser cases. Earlier slice and hook records were preserved.
