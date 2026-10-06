# Working on StudyFlow

StudyFlow is a small local coursework CRUD application. Read [spec.md](spec.md) and [GLOSSARY.md](GLOSSARY.md) before changing behavior. Implement the existing specification; avoid redesigning settled decisions without a concrete requirement. Keep architecture, domain rules, APIs, and scope changes reflected in `spec.md` in the same change.

## Current state and structure

The first vertical slice is implemented: course create/list API, SQLite, course-list page and creation form, validation/error feedback, and the verification hook. Later slices remain specified work. Work from the StudyFlow directory; its Git root currently belongs to the larger ITMOv2 repository. Keep files incremental and update these instructions when commands change.

- `studyflow/web.py`: FastAPI HTML and JSON routes, app factory, error mapping.
- `studyflow/domain.py`: pure validation/progress rules; `studyflow/coursework.py`: use cases and transactions.
- `studyflow/db.py` and `studyflow/migrations/`: concrete SQLite operations and packaged numbered migrations.
- `studyflow/templates/` and `studyflow/static/`: server-rendered pages, CSS, small JavaScript modules.
- `studyflow/github_mcp_client.py`: planned application MCP boundary, not implemented yet.
- `studyflow_mcp/`: planned stdio tool server and the only production GitHub HTTP client.
- `tests/`: current public course HTTP/HTML, hook-command, and browser tests; add MCP tests during that slice.
- `scripts/verify_after_change.py` and `.codex/hooks.json`: automatic test feedback.
- `docs/adr/`: consequential decision records; `docs/evidence/` and `reflection.md`: actual first-slice TDD/hook results, extended as work occurs.

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

`uv build` produces the Python package with templates, static assets, and migrations; include the MCP package when it exists. There is no frontend compilation. The app applies pending forward migrations on startup as well as through the explicit CLI. The default database is `data/studyflow.sqlite3`; use `STUDYFLOW_DB_PATH` to select another file. Never reset user data as part of verification.

In this workspace uv is installed at `.tools/bin/uv`. Replace `uv` with that path if it is not on PATH, with `UV_CACHE_DIR="$PWD/.uv-cache"` and `UV_PYTHON_INSTALL_DIR="$PWD/.python"` for project-local tooling. These generated directories are ignored.

When the MCP slice is implemented, start it with `uv run python -m studyflow_mcp.server`; it uses stdio. Configure its agent launch using the project virtualenv interpreter. An optional `GITHUB_TOKEN` belongs only in the server environment; never commit it or include it in browser responses/evidence.

## Verification workflow

```sh
uv run pytest -q
uv run playwright install chromium
uv run pytest -q -m browser
uv build
```

The default test suite excludes browser and live-network tests. It currently contains 18 tests; three course-form browser tests run explicitly. Installed Chrome can be used with `uv run pytest -q -m browser --browser-channel chrome` instead of installing Chromium. Use real temporary SQLite databases; mock external boundaries, not domain/persistence internals. Run the browser suite after UI changes and before the final demo. Perform opt-in live MCP demonstrations separately and record actual outcomes.

The implemented synchronous `PostToolUse` hook detects relevant file changes and runs the offline suite automatically. Launch Codex from StudyFlow and review/trust this exact definition in `/hooks`; trust is machine-local. Fresh runtimes demonstrated actual pass → failure → repair feedback in [docs/evidence/hook.md](docs/evidence/hook.md). An existing session may need to restart before it adopts a newly created hook; check actual event records instead of inferring activation from registration.

Read hook feedback before unrelated work. A deliberate TDD failure is the signal to implement that behavior; unexpected failures require repair. Do not disable the hook or weaken tests to proceed. Run edits sequentially rather than hiding edits and follow-up work in one compound tool call. Missing dependencies, timeouts, or no collected tests are failed verification, not success. If the hook cannot run, report that limitation and run the same check explicitly; manual checks do not establish that the required automatic demonstration works.

After repairing the test environment, `python3 scripts/verify_after_change.py --force` reruns verification and updates the hook's saved result even if source files did not change.

## Design constraints and completion

Keep a single local web application, SQLite, and the small required MCP subprocess. Use ordinary functions and concrete SQL; avoid generic repositories, service hierarchies, event buses, CQRS, extra infrastructure, and speculative features. Preserve these rules:

- Course → assignments → tasks ownership; atomic cascading deletes.
- Checklist-derived progress, including `0%` for an empty checklist; no independent assignment status.
- At most one repository reference per assignment; GitHub activity never changes coursework progress.
- Persist references only; fetch summaries explicitly through MCP; ordinary CRUD works without GitHub.

Before calling implementation complete, verify the requested slice, keep `spec.md` consistent, and state what passed and what remains unverified. For final coursework completion, retain actual MCP success/error and hook failure/repair evidence, demonstrate skill use, and write `reflection.md` from observed results. Do not fabricate evidence or label proposed commands as tested.
