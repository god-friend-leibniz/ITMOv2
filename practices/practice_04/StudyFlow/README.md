# StudyFlow

A local coursework organizer. The first implemented slice creates and lists courses through a browser form and JSON API, with SQLite persistence. The rest of the MVP is described in [spec.md](spec.md).

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

The default tests are offline. If Chrome is already installed, use `uv run pytest -q -m browser --browser-channel chrome` instead of downloading Chromium. Packaging includes the templates, JavaScript/CSS, and SQL migrations.

For automatic agent verification, launch Codex from this directory and trust the “Verifying StudyFlow” hook in `/hooks`. The hook runs the offline suite after relevant changes and returns failures to the agent. See [the actual demonstration](docs/evidence/hook.md) and [TDD evidence](docs/evidence/first-slice.md).
