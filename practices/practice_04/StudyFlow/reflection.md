# StudyFlow reflection

## First vertical slice, 2026-10-06

The domain-modeling design kept this slice focused: a Course has identity, a name, and a description. The implementation uses ordinary functions, concrete SQLite queries, and the existing FastAPI/template boundary. Assignment, task, and GitHub behavior remains for later slices.

TDD exposed real observable gaps: absent API/page routes, invalid coursework accepted or reported incorrectly, a browser form that did not save, and missing request-failure feedback. Each behavior was exercised through HTTP, the browser, or the hook command before its implementation. [The observed sequence](docs/evidence/first-slice.md) records red and green outcomes.

The automatic hook required more care than creating a configuration file. Its trust state was still untrusted after the initial UI step, and the running editing session did not adopt the new hook. Persisting the user's exact approval and testing fresh runtimes established actual synchronous execution, including a deliberate HTTP-status regression and repair. [Hook evidence](docs/evidence/hook.md) distinguishes these runtime events from manual handler calls. This is the main lesson from the environment work: registration, trust, and actual invocation must each be checked.

SQL migrations were placed inside the Python package so wheel installation includes them alongside templates and static assets. An installed-wheel smoke check outside the source directory verified these resources. This changes a file location, without changing the architecture or domain decisions.

Limitations at the end of the first slice: only course creation/listing was implemented; automatic hook activation must be reviewed in each new workspace; browser tests run explicitly rather than on every edit. MCP success/error demonstrations and the remaining CRUD/progress features belonged to later steps.

## Course management slice, 2026-10-06

The installed TDD skill guided incremental HTTP/HTML and browser behavior tests for detail, edit, and delete. Each new implementation followed an observed failure: missing routes, a JSON error where HTML was needed, an accepted empty patch, missing browser controls, and absent request-failure handling. The final review also added coverage for behavior already supplied by shared validation; those tests passed immediately and are not claimed as red/green cycles. [The sequence and results](docs/evidence/second-slice.md) distinguish them.

Reusing the creation form script and validation kept the change small. Parameterized SQL updates preserve omitted fields in a single statement. Course edits and deletions survived creating a new app against the same database. No architecture, schema, glossary, or ADR change was necessary. Assignment cascade stays in the next slice, where its child tables will exist.

The full browser run exposed one test maintenance issue: the saved description also appears in the new edit textarea, making a text-only selector ambiguous. Scoping the assertion to the displayed article resolved it without weakening the behavior check. All 35 routine tests and 10 browser tests then passed; the built wheel also passed CRUD/restart and resource checks outside the source tree. A pre-existing TestClient dependency deprecation warning remains.

The trusted hook still did not dispatch automatically in this editing session. The documented fallback ran its handler explicitly after relevant edits, returning blocking feedback for deliberate API failures and green summaries after repair. Its final result was 35 passed, with 10 browser cases excluded by design. This does not establish a new automatic invocation; the earlier fresh-runtime demonstration remains the automatic evidence. Browser failures were observed through the explicit browser runner.

## Final verification gate, 2026-10-06

Fast edit feedback alone could miss a browser failure. The new synchronous Stop hook runs offline pytest, browser pytest, and packaging whenever an agent tries to finish. Inspection of Codex 0.160.1's installed event/output schemas established the correct lifecycle and JSON contract. Stop needs a blocking reason to continue the agent; it does not accept PostToolUse's context shape or retract an already emitted message.

TDD at the public hook-command boundary exposed missing failure decisions, absent tooling feedback, unbounded checks, and infrastructure exceptions. The resulting handler blocks all of these, cleans up timed-out subprocesses, and rechecks even after a Stop continuation. It keeps final evidence separate from the fast fingerprint cache. No app architecture or domain change was necessary.

After persisting the user's exact hook approval, a fresh runtime added a browser-only failing test. The fast hook passed; Stop found the failure and returned a continuation prompt. The deterministic fixture received that reason, removed the probe, and tried to finish again. The second Stop check passed all 44 routine tests, 10 browser tests, and the build, after which Codex emitted turn completion and exited 0. [Captured evidence](docs/evidence/final-hook.md) distinguishes this actual automatic sequence from manual verification and records the trust/runtime limitations.

## Assignment slice, 2026-10-07

The TDD skill guided the next vertical slice through the existing public HTTP/HTML and browser boundaries. Missing endpoints and forms, accepted invalid dates, an accepted empty patch, and absent validation/network/deletion feedback each produced an observed failure before their implementation. [Assignment evidence](docs/evidence/third-slice.md) records these cycles and distinguishes review tests that passed immediately.

The planned second migration added assignments without disturbing existing courses. Parent-checked creation and SQLite cascade deletion keep ownership explicit without a repository layer or extra services. API edits preserve omitted values and distinguish a cleared date from an omitted one. Browser forms preserve input after errors and block repeated mutations while pending. All assignments currently have empty checklists and null repository references; their later slices will supply tasks, derived progress, and GitHub integration. No settled domain or architecture decision changed, so glossary and ADRs stayed unchanged.

Final verification passed 80 routine tests, 21 browser tests, and packaging. A wheel installed outside the source tree also passed assignment persistence, cascade, template, JavaScript, and migration checks. Coverage includes upgrade from a version-1 course database and escaped student text. The existing TestClient deprecation warning remains.

Automatic hook dispatch was still absent in this editing session. Explicit fast-handler calls returned red/green feedback, and the explicit final handler returned three successful command results. Empty event metadata makes these manual checks distinguishable from the earlier genuine automatic demonstrations. Hook definitions and trust were preserved. Coursework completion still needs the checklist/reference/MCP slices and actual MCP success/error evidence.

## Checklist slice, 2026-10-07

The TDD skill guided task CRUD and checklist progress through the existing HTTP/HTML and browser interfaces. Missing routes and controls, invalid title handling, an empty patch accepted as an edit, and absent browser failure recovery each failed before implementation. The task migration and ordinary SQL/functions kept ownership and cascade deletion explicit. Progress comes from current counts, including floor percentages and the empty-checklist rule; no derived value is stored. [Checklist evidence](docs/evidence/fourth-slice.md) records the observed sequence and separates immediately passing regression checks.

A useful integration test found an assignment-edit response still reporting zero progress. Reading the updated assignment and task counts in the same transaction repaired that behavior within the existing design. Task completion uses an explicit strict boolean, so repeats are harmless and reopening preserves the title. Browser controls support keyboard input, confirmation, validation messages, restored checkbox state after failed saves, and retry without discarding entered titles.

One red browser run revealed a test-harness problem: pending-control assertions failed before intercepted requests were released, and the runner stalled after reporting six failures. Interrupting that runner and adding `finally` cleanup made the same red case exit normally. All six cases then passed after the behavior was implemented. Failure tests need reliable cleanup so the final gate can report a regression instead of waiting on an artificial unfinished request.

Final verification passed 114 routine tests, 35 browser tests, and packaging. The installed wheel also passed version-2 upgrade, task CRUD, derived progress, restart, cascade, and packaged-resource checks outside the source tree. The existing TestClient warning remains. Hook definitions/trust were unchanged; explicit fast/final handlers provided verification, while automatic dispatch was not observed in this session. Earlier automatic evidence remains distinct from these manual calls.

No settled domain or architecture decision changed, so glossary and ADRs stayed unchanged. Repository-reference management is next, followed by MCP integration and actual successful/erroneous tool-call evidence.

## Repository-reference slice, 2026-10-07

The TDD skill guided step 5 through the existing HTTP/HTML and browser boundaries. A repository field rejected as unknown, accepted invalid identifiers, an update that returned no reference, and missing browser link/fields each failed before their minimal implementations. [Repository-reference evidence](docs/evidence/fifth-slice.md) separates these observed cycles from review checks that already passed.

The reference stays embedded in the assignment. Migration 004 adds only two nullable columns with a complete-pair CHECK; syntax validation and lowercase normalization use ordinary domain functions. Atomic edits preserve omitted references and distinguish explicit removal. Shared references do not imply shared ownership, and GitHub activity cannot affect checklist progress. No settled design or glossary/ADR change was needed.

Review verified strict validation, unchanged state after invalid writes, maximum accepted identifier lengths, offline CRUD with outbound socket connections disabled, upgrade from an existing checklist database, and browser input preservation/retry. The initial browser editing test used the wrong existing button label; fixing that selector and waiting for save navigation repaired the test without changing application behavior.

Final verification passed 149 routine tests, 45 browser tests, and the build. The installed wheel also passed upgrade, reference persistence, progress, cascade, and packaged-resource checks outside the checkout. Existing dependencies stayed unchanged; the TestClient deprecation warning remains.

Automatic hook dispatch was not observed in this editing session. Explicit fast-handler calls returned blocking failure and passing repair feedback; the explicit final handler passed all three commands with empty event metadata. The trusted hook definitions and prior automatic evidence were preserved. The next slice remains the narrow MCP tool, application summary integration, and actual successful/erroneous MCP demonstrations.

## Useful MCP slice, 2026-10-07

The installed TDD skill guided work at the confirmed MCP tool, actual stdio/web, and browser boundaries. Observed failures exposed missing modules, invalid upstream data accepted or thrown as exceptions, unsafe integration results, absent panel feedback, unbounded subprocess calls, missing token forwarding, and stale browser responses. [Slice evidence](docs/evidence/sixth-slice.md) records the repairs and distinguishes review checks that passed immediately. The resulting implementation keeps the planned boundary: only the MCP server calls GitHub, and metadata never becomes coursework state or progress.

The official SDK is locked to 2.3.0. Using its stdio session and cancellation cleanup avoided a separate process manager; deadline tests verify both startup/call stalls return safe errors and reap children. A strict model alone still accepted integer values for a boolean literal discriminator, so the client additionally checks the raw boolean and consistency between text, structured content, and the error flag. Validation at the external boundary found a concrete problem without changing the domain or architecture.

All 216 routine tests and 53 browser tests passed, and the built wheel passed isolated installation, resource/coursework checks, and packaged MCP discovery/invalid-input calls. An initial offline wheel install lacked cache metadata; using lockfile constraints and fetching the missing dependency fixed the environment without changing dependencies again. Routine/browser tests still require no GitHub access. The existing local uv-cache build warning remains nonfatal.

Project-relative registration was recognized by Codex 0.160.1. A fresh runtime discovered the tool, dispatched real stdio calls, and automatically ran the trusted Stop hook, which passed offline tests, browser tests, and packaging. The temporary deterministic Responses fixture first assumed flat tool names; inspecting Codex's nested namespaces repaired the evidence harness. It did not replace GitHub responses or delegate implementation. Current editing-session fast feedback remained manual fallback; prior genuine automatic failure/repair evidence is preserved.

Initial live GitHub calls hit an unauthenticated rate limit, including the attempt intended to verify a missing repository. The actual invalid-input call worked, but rate limits do not establish success or absence. The demonstration was therefore left pending instead of relabeling controlled HTTP fixtures as live success. After the user supplied a token in local `.env`, the same implementation and registration returned a real `octocat/Hello-World` summary, `INVALID_INPUT`, and a verified `REPOSITORY_NOT_FOUND` for a generated name. [MCP evidence](docs/evidence/mcp.md) preserves both runs. No application changes or new TDD cycles were necessary for this retry.

The token was loaded only into process environment and checked absent from saved evidence. `.env` remains ignored by Git and excluded from both distributions. The installed uv supports explicit `--env-file .env` launches, avoiding an application-specific dotenv loader or committed credential configuration. The authenticated fresh Codex runtime also automatically ran Stop: 216 offline tests, 53 browser tests, and the build passed with exits 0. Step 6 is now complete; step 7's final coursework review remains separate. No glossary or ADR change was needed.
