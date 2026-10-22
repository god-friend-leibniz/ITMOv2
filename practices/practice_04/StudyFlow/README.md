# StudyFlow

A local coursework organizer. Manage courses and assignments through browser forms and a JSON API, with SQLite persistence. Add assignment checklist tasks, rename them, complete or reopen them, and track progress on assignment and course pages. Save, replace, or remove an optional GitHub owner/repository pair; saving works offline. On assignment detail, explicitly load/refresh the public repository's description, default branch, languages, and last push time through the custom MCP server. Repository errors leave coursework usable; summaries do not change progress or persist across page reloads. Deleting coursework removes its children after confirmation. See [spec.md](spec.md).

Requires Python 3.12 and uv. From this directory:

```sh
uv sync --frozen
uv run python -m studyflow.db migrate
uv run uvicorn studyflow.web:create_app --factory --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. The app also applies pending forward migrations on startup. `STUDYFLOW_DB_PATH` overrides `data/studyflow.sqlite3`.

In the current workspace, uv was installed locally at `.tools/bin/uv` and Python at `.python/`. When using that installation, replace `uv` above with `.tools/bin/uv`, and set `UV_CACHE_DIR="$PWD/.uv-cache"` and `UV_PYTHON_INSTALL_DIR="$PWD/.python"` to keep tooling files local.

```sh
uv run pytest -q
uv run playwright install chromium
uv run pytest -q -m browser
uv build
```

The default tests are offline (218 tests); 53 browser tests run separately. If Chrome is already installed, use `uv run pytest -q -m browser --browser-channel chrome` instead of downloading Chromium. Packaging includes both application and MCP packages, templates, JavaScript/CSS, and SQL migrations. All seven planned implementation steps are complete; [final-review evidence](docs/evidence/seventh-slice.md) records tests, the isolated installed-wheel check, and actual automatic hook failure/repair.

The application starts `studyflow_mcp.server` over stdio for summary requests. To use its single read-only `get_repository_summary(owner, repo)` tool in Codex, launch Codex from this directory after `uv sync --frozen`; [.codex/config.toml](.codex/config.toml) supplies the project-relative command. Check registration with `codex mcp get studyflow_github --json`; a running session may need to restart to discover the new tool. The standalone command is `uv run python -m studyflow_mcp.server` and expects MCP protocol input on stdin.

An optional `GITHUB_TOKEN` in the launching process environment raises GitHub's API allowance; both application and agent forward it only to the server. Keep it out of source/configuration committed to Git and evidence. Private repositories are not supported. Actual agent discovery, live successful summaries, invalid-input rejection, missing-repository errors, and earlier rate limits are recorded in [MCP evidence](docs/evidence/mcp.md), separately from deterministic integration tests.

For a token stored in the ignored local `.env`, load it explicitly at launch:

```sh
uv run --frozen --env-file .env uvicorn studyflow.web:create_app --factory --host 127.0.0.1 --port 8000
uv run --frozen --env-file .env codex
```

Existing processes must be restarted with that environment; the app and MCP server do not automatically read `.env`.

For automatic agent verification, launch Codex from this directory and trust both “Verifying StudyFlow” and “Final verification of StudyFlow” in `/hooks`. The fast hook runs offline tests after relevant edits; the final Stop hook runs offline tests, browser tests, and the build before allowing completion. Failures request agent continuation and repair. Prepare dependencies and a Playwright browser first; installed macOS Chrome is selected automatically for final verification. See [fast-hook evidence](docs/evidence/hook.md), [final-hook evidence](docs/evidence/final-hook.md), [course-management verification](docs/evidence/second-slice.md), [assignment verification](docs/evidence/third-slice.md), [checklist verification](docs/evidence/fourth-slice.md), and [repository-reference verification](docs/evidence/fifth-slice.md). For an explicit final check, run `python3 scripts/verify_before_finish.py` and inspect its JSON feedback.
