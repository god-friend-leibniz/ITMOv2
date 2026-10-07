# Final demonstration and review, 2026-10-07

Step 7 is complete. The review compared the implementation, specification, glossary, ADR, tests, packaging, and coursework evidence. Two existing error contracts had concrete gaps; each was repaired through the installed TDD skill at an already confirmed public boundary. No domain, architecture, dependency, or persistence decision changed.

## Behavior and observed red → green sequence

Only one failing behavior test was added at a time; its minimal repair passed before the next cycle. No refactoring or additional feature work was needed. [Original fast-handler records](final-review-tdd.json) preserve the observed failures and greens. Empty event metadata identifies these editing-session checks as explicit fallback invocations, rather than automatic dispatch.

| Test and boundary | Observed red | Minimal green repair |
| --- | --- | --- |
| `test_unexpected_database_failure_returns_safe_json_and_preserves_saved_course`, HTTP with real temporary SQLite | A real SQLite trigger rejected an edit. The 500 response was plain text, so JSON decoding failed: 1 failed / 216 passed at 15:41:33 UTC. | Extend the existing exception handler to unexpected exceptions while preserving the SQLite-busy 503 case. The API returns the safe `INTERNAL_ERROR` envelope; the course remains unchanged and a subsequent create works. 217 passed at 15:42:23 UTC. |
| `test_unadvertised_tool_is_rejected_before_github_access`, MCP `tools/call` with controlled GitHub HTTP | Calling `delete_repository` with valid arguments unexpectedly ran the summary callback; the expected protocol error was absent: 1 failed / 217 passed at 15:45:05 UTC. | Check the tool name before argument processing or HTTP access; reject unknown names with `-32602`, “Unknown tool.” 218 passed at 15:45:52 UTC; the test confirms zero HTTP requests. |

The trigger injects a real database failure; assertions observe the response and saved course through HTTP. The MCP test uses the SDK client, not the callback directly. Unknown tools are protocol errors under the [MCP tools contract](https://modelcontextprotocol.io/specification/2025-11-25/server/tools). Known-tool validation and normalized results remain unchanged. These repairs fulfill the existing safe-error and single-tool requirements.

## Actual automatic hooks and final verification

Definitions, timeouts, and existing trust were preserved. A fresh Codex CLI **0.160.1** runtime used its actual tool dispatcher and trusted hook engine. A fixed local Responses fixture replayed a temporary change from course POST status 201 to 200, a neutral finish attempt, exact source restoration after continuation, and another finish attempt. It made no model API or live GitHub calls and did not delegate development. Sanitized original events are in [final-review-runtime.json](final-review-runtime.json).

| UTC time | Genuine event | Observed result |
| --- | --- | --- |
| 15:50:21 | PostToolUse after status regression | 2 failed / 216 passed / 53 deselected, exit 1. Both failures concern the required 201 create status; blocking feedback reached the next fixture request. |
| 15:51:16 | Stop, `stop_hook_active: false` | Offline failed with the same two failures; browser passed 53; build passed. Stop returned `decision: block`; its reason reached the continuation request. |
| 15:51:38 | PostToolUse after exact repair | 218 passed / 53 deselected, exit 0. |
| 15:52:31 | Stop, `stop_hook_active: true` | All three commands passed; `turn.completed` followed this green gate. |

The runtime made four fixture requests, exited 0, and confirmed exact source restoration. The interrupted outer observation resumed to this successful result. The recorded session/turn IDs and event names distinguish automatic runs from manual handler calls. Neither an active Stop continuation nor a previous fast result skipped final verification.

| Final automatic command | Result |
| --- | --- |
| `uv run pytest -q` | **218 passed**, 53 deselected, 19.59 seconds; exit 0 |
| `uv run pytest -q -m browser` | **53 passed**, 218 deselected, 32.14 seconds; exit 0 |
| `uv build` | Wheel and source archive built; exit 0 |

## Installed-package check

The resulting wheel was installed offline in a new temporary virtual environment outside the checkout, constrained by the unchanged lockfile. Both application and MCP module paths were checked to belong to that installation. [The result](final-review-wheel.json) records exit 0 and these passing checks:

- Course → assignment → three tasks → one complete gives literal `1 / 3`, `33%`; normalized reference and optional date survive app restart.
- Packaged migrations, templates, and all static assets work; course deletion removes assignment and task access.
- A failed course edit returns safe JSON, leaves saved data unchanged, and permits later course creation.
- The installed web route uses actual stdio MCP with controlled GitHub HTTP responses for both summary success and missing-repository failure; coursework progress is unchanged.
- The production packaged stdio entry point discovers exactly one tool, returns an invalid-input error, and rejects an unknown tool with `-32602` without requiring GitHub access.
- `.env` is absent from wheel and source archive. Credentials were not loaded for this check and are absent from the new evidence.

This is a manual package smoke check using existing behavior, not another claimed red/green cycle. Live GitHub success/error proof remains separately recorded in [mcp.md](mcp.md); controlled fixtures do not substitute for it.

## Completion review and documentation

| Requirement | Implemented behavior/evidence |
| --- | --- |
| Coursework CRUD and ownership | HTTP/browser suites, [course](second-slice.md), [assignment](third-slice.md), and [checklist](fourth-slice.md) evidence; cascades and restart verified |
| Checklist progress rules | Empty, complete, reopened, added/deleted tasks and floor percentages; no persisted progress or independent status |
| Optional repository reference | [Reference slice](fifth-slice.md), offline validation/CRUD, complete pair, zero or one per assignment |
| Explicit useful GitHub boundary | [MCP slice](sixth-slice.md), real stdio route tests, explicit load/refresh/error UI, no persisted summary; only server production code calls GitHub |
| Custom MCP success and errors in an agent | [Live discovery/call evidence](mcp.md), including authenticated success, invalid input, and verified missing repository |
| `AGENTS.md` and meaningful skills | Maintained instructions; domain-modeling design/glossary/[ADR 0001](../adr/0001-github-through-mcp.md); TDD sequences in each slice |
| Automatic verification feedback | Preserved [fast](hook.md) and [final](final-hook.md) evidence, plus the latest actual failure → continuation → repair record above |
| Reflection and distributable application | Updated [reflection](../../reflection.md), green build and isolated installed-wheel check |

No new entity, background process, generic layer, extra skill, or product feature was added. Domain ownership, empty-checklist behavior, dates, reference lifecycle, transactions, and external-data boundaries remain consistent. Review found no further blocking contradiction or omitted MVP rule. `spec.md` marks all steps complete and clarifies the two repaired contracts; `AGENTS.md` and README record current counts/completion. Reflection and hook evidence include the final results. GLOSSARY.md and ADR 0001 are unchanged.

The delivered scope remains one local student workspace and public GitHub repositories. Real GitHub availability/metadata are variable; routine tests use controlled external responses. Hook trust is machine-local, and a running session may require restart to adopt definitions. The Stop hook requests continuation on failure but cannot retract text already emitted, so agents must defer completion claims until green. These are the existing scope/runtime limits, not unfinished MVP work.
