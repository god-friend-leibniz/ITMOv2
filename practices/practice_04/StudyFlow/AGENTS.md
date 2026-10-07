# Working on StudyFlow

StudyFlow is a small local coursework CRUD application. Read [spec.md](spec.md) and [GLOSSARY.md](GLOSSARY.md) before changing behavior. Implement the existing specification; avoid redesigning settled decisions without a concrete requirement. Keep architecture, domain rules, APIs, and scope changes reflected in `spec.md` in the same change.

## Current state and structure

The first six vertical slices are complete: course/assignment/task CRUD, derived progress, offline repository-reference management, explicit repository-summary load/refresh with recoverable errors, SQLite persistence, cascade deletion, and both verification hooks. Step 6 includes actual agent discovery and live successful/invalid-input/missing-repository MCP calls; see [MCP evidence](docs/evidence/mcp.md). Step 7's final demonstration and review is next. Assignment responses include a null repository or a normalized `{owner, repo}` pair and progress calculated from task counts; summaries and progress are never persisted. Reference CRUD validates syntax offline and stores only the pair through migration 004. Work from the StudyFlow directory; its Git root currently belongs to the larger ITMOv2 repository. Keep files incremental and update these instructions when commands change.

- `studyflow/web.py`: FastAPI HTML and JSON routes, app factory, error mapping.
- `studyflow/domain.py`: pure validation/progress rules; `studyflow/coursework.py`: use cases and transactions.
- `studyflow/db.py` and `studyflow/migrations/`: concrete SQLite operations and packaged numbered migrations.
- `studyflow/templates/` and `studyflow/static/`: server-rendered pages, CSS, small JavaScript modules.
- `studyflow/github_mcp_client.py`: application stdio MCP boundary, result validation, deadline and process cleanup, error translation.
- `studyflow_mcp/`: schemas, one read-only stdio tool, and the only production GitHub HTTP client.
- `studyflow/static/repository.js`: explicit load/refresh and recoverable panel errors; discard responses after reference edits.
- `tests/`: public HTTP/HTML, MCP tools, real stdio integration, hook-command, and browser tests. `tests/fixtures/` contains test-only MCP servers with controlled GitHub responses or transport failures; no live network in routine tests.
- `scripts/verify_after_change.py`: fast feedback after edits; `scripts/verify_before_finish.py`: final offline/browser/build gate; `.codex/hooks.json`: both synchronous hooks.
- `docs/adr/`: consequential decision records; `docs/evidence/` and `reflection.md`: actual TDD/hook results, including [course management](docs/evidence/second-slice.md), [assignments](docs/evidence/third-slice.md), [checklists](docs/evidence/fourth-slice.md), and [repository references](docs/evidence/fifth-slice.md), extended as work occurs.

## Skills

Use [.agents/skills/domain-modeling/SKILL.md](.agents/skills/domain-modeling/SKILL.md) when introducing/changing domain terminology, ownership, relationships, invariants, or architectural decisions. Keep the glossary free of implementation details and add ADRs only under that skill's criteria.

Use [.agents/skills/tdd/SKILL.md](.agents/skills/tdd/SKILL.md) when implementing features, fixing behavior, or adding integration tests. The proposed public test boundaries are in `spec.md`; follow the skill's confirmation rule where they have not already been confirmed in the session. Read its testing/mocking guidance and work one failing behavior test → minimal implementation at a time. Do not create every layer or every test before delivering a working slice. Do not install extra skills without a concrete need.

## Setup, build, and run

Use Python 3.12 with uv and the existing `pyproject.toml`/`uv.lock`. Run these commands from StudyFlow:

```sh
uv sync --frozen
uv run python -m studyflow.db migrate
uv run uvicorn studyflow.web:create_app --factory --host 127.0.0.1 --port 8000
```

`uv build` packages both `studyflow` and `studyflow_mcp`, including templates, static assets, and migrations. There is no frontend compilation. The app applies pending forward migrations on startup as well as through the explicit CLI. The default database is `data/studyflow.sqlite3`; use `STUDYFLOW_DB_PATH` to select another file. Never reset user data as part of verification.

In this workspace uv is installed at `.tools/bin/uv`. Replace `uv` with that path if it is not on PATH, with `UV_CACHE_DIR="$PWD/.uv-cache"` and `UV_PYTHON_INSTALL_DIR="$PWD/.python"` for project-local tooling. These generated directories are ignored.

Start the MCP server with `uv run python -m studyflow_mcp.server`; it uses stdio, not an HTTP listener. The app launches that module with its own Python interpreter for each summary request. `.codex/config.toml` registers `studyflow_github` using `.venv/bin/python`; launch Codex from StudyFlow after `uv sync --frozen`. `codex mcp get studyflow_github --json` checks registration; actual discovery/calls require a fresh runtime if the existing session has not adopted configuration. The SDK is locked to 2.3.0. An optional `GITHUB_TOKEN` belongs only in the process environment; the app and Codex forward it to the server. Never commit it or include it in browser responses/evidence. Private repositories remain outside scope even with a token.

A local `.env` is ignored by Git. Load it explicitly when launching, for example `uv run --frozen --env-file .env codex` or `uv run --frozen --env-file .env uvicorn studyflow.web:create_app --factory --host 127.0.0.1 --port 8000`. Merely creating `.env` does not inject it into an existing process. Do not read or print its contents in tool output; do not load real credentials for routine offline tests.

## Verification workflow

```sh
uv run pytest -q
uv run playwright install chromium
uv run pytest -q -m browser
uv build
```

The default test suite excludes browser and live-network tests. It currently contains 216 tests; 53 browser tests run separately and in final verification. Installed Chrome can be used with `uv run pytest -q -m browser --browser-channel chrome` instead of installing Chromium. Use real temporary SQLite databases; mock external boundaries, not domain/persistence internals. Run the browser suite after UI changes and before the final demo. Perform opt-in live MCP demonstrations separately and record actual outcomes; rate-limit errors do not establish a successful summary or a verified 404.

The implemented synchronous `PostToolUse` hook detects relevant file changes and runs the offline suite automatically. Launch Codex from StudyFlow and review/trust this exact definition in `/hooks`; trust is machine-local. Fresh runtimes demonstrated actual pass → failure → repair feedback in [docs/evidence/hook.md](docs/evidence/hook.md). An existing session may need to restart before it adopts a newly created hook; check actual event records instead of inferring activation from registration.

The synchronous `Stop` hook runs `python3 scripts/verify_before_finish.py` whenever the agent tries to finish a turn. Codex CLI 0.160.1's installed schema identifies this event and supports `decision: "block"` plus `reason` as an automatic continuation prompt. The handler runs, in order, `uv run pytest -q`, `uv run pytest -q -m browser`, and `uv build`. All three run even if an earlier check fails. Any nonzero exit, missing tooling, timeout, malformed input, or evidence-writing error returns blocking feedback. Do not claim completion until all three pass. Read the returned failure output, repair it, and let the next Stop attempt reverify; `stop_hook_active` never skips verification or permits a known failure.

The final handler resolves this project from its script path, prefers `.tools/bin/uv` when available, uses the frozen lockfile and offline uv mode, and defaults tooling caches to this workspace. Prepare dependencies with `uv sync --frozen` and a browser before development; final verification does not fetch missing dependencies or browsers. On macOS with installed Google Chrome it selects Chrome through browser-only `PYTEST_ADDOPTS`. Set `STUDYFLOW_BROWSER_CHANNEL` to another installed Playwright channel, or to an empty string to require bundled Chromium. Each command has a 60-second limit; timed-out process groups are killed. The registered 200-second hook timeout leaves time to return feedback.

Final results and bounded feedback use supported Stop JSON, with full command output in ignored `data/verification/final-last.json` and `final-runs.jsonl`. Final verification always reruns and never reuses the fast hook's fingerprint or cached pass. Run `python3 scripts/verify_before_finish.py` explicitly if automatic dispatch is unavailable; this performs the same checks but does not prove automatic invocation. The script exits 0 to deliver valid hook JSON even for failures: inspect `decision` and each recorded command exit, not only the script process status. New Stop definitions need their own exact trust review in `/hooks`; the existing PostToolUse definition and trust remain unchanged. See [final-hook evidence](docs/evidence/final-hook.md).

Read hook feedback before unrelated work. A deliberate TDD failure is the signal to implement that behavior; unexpected failures require repair. Do not disable the hook or weaken tests to proceed. Run edits sequentially rather than hiding edits and follow-up work in one compound tool call. Missing dependencies, timeouts, or no collected tests are failed verification, not success. If the hook cannot run, report that limitation and run the same check explicitly; manual checks do not establish that the required automatic demonstration works.

After repairing the test environment, `python3 scripts/verify_after_change.py --force` reruns verification and updates the hook's saved result even if source files did not change.

## Design constraints and completion

Keep a single local web application, SQLite, and the small required MCP subprocess. Use ordinary functions and concrete SQL; avoid generic repositories, service hierarchies, event buses, CQRS, extra infrastructure, and speculative features. Preserve these rules:

- Course → assignments → tasks ownership; atomic cascading deletes.
- Checklist-derived progress, including `0%` for an empty checklist; no independent assignment status.
- At most one repository reference per assignment; GitHub activity never changes coursework progress.
- Persist references only; fetch summaries explicitly through MCP; ordinary CRUD works without GitHub.

Before calling implementation complete, verify the requested slice, keep `spec.md` consistent, and state what passed and what remains unverified. For final coursework completion, retain actual MCP success/error and hook failure/repair evidence, demonstrate skill use, and write `reflection.md` from observed results. Do not fabricate evidence or label proposed commands as tested.
