# Repository references: observed TDD and verification

Completed on 2026-10-07 using the installed `tdd` skill at the previously authorized public HTTP/HTML and browser boundaries. Tests use real temporary SQLite files; browser tests use a temporary loopback Uvicorn server and installed Chrome. No domain or persistence internals are mocked.

Only implementation step 5 was added: save, attach, replace, or remove one optional repository reference; validate and lowercase its owner/name; show its HTTPS link on assignment detail. Ordinary coursework CRUD remains offline. The custom MCP server and summary loading belong to step 6 and are not implemented here.

## Incremental red → green sequence

| Behavior | Observed red | Minimal green change |
| --- | --- | --- |
| Create an assignment with a reference and retrieve it after restart | POST returned 422 because repository was unknown | Nested request schema, migration 004, concrete insert/read SQL, and normalized assignment response |
| Normalize identifiers and enforce the specified syntax | Mixed case remained unchanged; invalid identifiers returned 201 (19 failing cases) | Pure owner/name validators used by the request schema; reject whitespace, slashes, URLs, invalid hyphens, lengths, and dot-only special names |
| Attach/replace a reference and preserve it during unrelated edits | PATCH returned a null reference despite returning 200 | Update both nullable columns atomically, distinguish omission from explicit null, and reread assignment/progress in the existing transaction |
| Show the saved repository link | Browser could not find the link | Conditional assignment-detail HTTPS link using saved normalized identifiers |
| Create with a reference through the browser | GitHub owner input was absent | Labelled optional fields in the existing create/edit forms and reference-or-null JSON submission; trim browser inputs |

Each implementation followed its observed failure and a passing rerun. Fast-handler feedback covered routine tests; browser failures and repairs were checked with the separate browser runner.

Review checks passed using the existing implementation: explicit-null removal and repeated removal, references shared across assignments, omitted-field preservation, strict nested types/missing/extra fields, invalid partial edits leaving the entire assignment unchanged, accepted 39/100-character limits, and preservation of `.git`. A CRUD test disables outbound socket connections while creating, reading, replacing, and clearing references; syntactic validity does not depend on availability. A version-3 database fixture upgrades with coursework and completed tasks intact, accepts a saved reference, survives restart, and retains cascade deletion.

Browser review covers initially absent/present references, attach/replace/clear, unrelated assignment edits preserving the prefilled reference, reload persistence, unchanged checklist progress, invalid owner/incomplete-pair feedback on both create and edit, pending save/delete controls, and network/database-busy recovery with successful retry. Failed saves retain the old link and entered values.

The first two-case browser edit review used an incorrect “Save assignment” selector and failed after 62.24 seconds. The existing button is “Save changes”; correcting the selector and explicitly waiting for save navigation made both cases pass in 2.01 seconds without application changes. This was a test correction, not a claimed application red/green cycle. The remaining review checks are regression coverage, not additional claimed failing implementation cycles.

## Final verification

The explicit `python3 scripts/verify_before_finish.py` run completed at **2026-10-07T09:47:33.308082+00:00** and returned `StudyFlow final verification passed`:

| Command | Result |
| --- | --- |
| `uv run pytest -q` | **149 passed, 45 deselected**, exit 0, 11.46 seconds |
| `uv run pytest -q -m browser` | **45 passed, 149 deselected**, exit 0, 21.35 seconds, installed Chrome |
| `uv build` | Wheel and source archive built, exit 0 |

This slice adds **35 routine cases and 10 browser cases**, in `tests/test_repository_references.py` and `tests/test_browser.py`.

Installed the wheel without dependencies into a temporary directory and ran from outside the checkout with the existing dependency environment. Verified that imports came from the installation, migration 004 was packaged, an existing version-3 database upgraded, reference create/edit/clear/restart worked, existing metadata/progress remained intact, parent deletion cascaded, and templates/JavaScript/CSS were available. The source archive contained no uv cache files despite uv's local-cache warning. All checks used temporary databases; student data was untouched. The existing TestClient/Starlette `httpx` deprecation warning remains; no dependencies changed.

## Hook results and documentation

Hook definitions and trusted approvals were unchanged. Automatic dispatch was not observed in this editing session. The documented explicit fast-handler fallback reported blocking feedback for the deliberate API failures, then passing feedback after repair; its final source-change check reported **149 passed, 45 deselected**. Browser checks ran separately because the fast hook intentionally excludes them.

The final handler was invoked explicitly and all three stages passed. Recorded event metadata is `{}`, so this is manual verification rather than evidence of an automatic Stop invocation. Earlier genuine automatic pass/failure/repair evidence remains in [hook.md](hook.md) and [final-hook.md](final-hook.md). No hook was disabled or weakened.

`spec.md` and `AGENTS.md` record step 5 completion, schema version 4, current reference behavior/test counts, and MCP as the next slice. README and reflection were updated. Migration 004 adds only the planned pair of nullable reference columns and its complete-pair CHECK. No settled rule or architectural decision changed; `GLOSSARY.md` and ADRs remain unchanged.
