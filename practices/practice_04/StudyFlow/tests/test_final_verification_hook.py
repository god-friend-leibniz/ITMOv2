import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest


@pytest.fixture
def final_hook_project(tmp_path):
    root = Path(__file__).resolve().parents[1]
    (tmp_path / "scripts").mkdir()
    script = root / "scripts/verify_before_finish.py"
    if script.exists():
        shutil.copy(script, tmp_path / "scripts")
    (tmp_path / ".tools/bin").mkdir(parents=True)
    uv = tmp_path / ".tools/bin/uv"
    uv.write_text(
        f"#!{sys.executable}\n"
        "import json, pathlib, sys\n"
        "root = pathlib.Path.cwd()\n"
        "with (root / 'commands.jsonl').open('a') as history:\n"
        "    history.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "outcomes = root / 'outcomes.json'\n"
        "code = json.loads(outcomes.read_text()).get(' '.join(sys.argv[1:]), 0) if outcomes.exists() else 0\n"
        "print('browser behavior failed' if code else 'verification command passed')\n"
        "sys.exit(code)\n"
    )
    uv.chmod(0o755)
    return tmp_path


def invoke_final_hook(project, *arguments, active=False):
    result = subprocess.run(
        [sys.executable, str(project / "scripts/verify_before_finish.py"), *arguments],
        input=json.dumps({"hook_event_name": "Stop", "stop_hook_active": active}),
        text=True, capture_output=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_final_hook_runs_all_three_checks_before_allowing_completion(final_hook_project):
    feedback = invoke_final_hook(final_hook_project)
    commands = [json.loads(line) for line in (final_hook_project / "commands.jsonl").read_text().splitlines()]
    assert commands == [["run", "pytest", "-q"], ["run", "pytest", "-q", "-m", "browser"], ["build"]]
    assert "decision" not in feedback
    assert "final verification passed" in feedback["systemMessage"]
    assert "uv run pytest -q -m browser: exit 0" in feedback["systemMessage"]
    assert "uv build: exit 0" in feedback["systemMessage"]


@pytest.mark.parametrize("command", ["run pytest -q", "run pytest -q -m browser", "build"])
def test_final_hook_returns_continuation_reason_for_any_failed_check(final_hook_project, command):
    (final_hook_project / "outcomes.json").write_text(json.dumps({command: 1}))
    feedback = invoke_final_hook(final_hook_project)
    assert feedback["decision"] == "block"
    assert "Do not claim completion" in feedback["reason"]
    assert f"uv {command}: exit 1" in feedback["reason"]
    assert "browser behavior failed" in feedback["reason"]
    assert feedback.get("continue") is not False
    assert "hookSpecificOutput" not in feedback


def test_missing_uv_blocks_completion_with_actionable_feedback(final_hook_project, monkeypatch):
    (final_hook_project / ".tools/bin/uv").unlink()
    monkeypatch.setenv("PATH", str(final_hook_project / "no-tools"))
    feedback = invoke_final_hook(final_hook_project)
    assert feedback["decision"] == "block"
    assert "uv" in feedback["reason"]
    assert "Cannot start verification" in feedback["reason"]


def test_final_hook_blocks_timeouts_and_cleans_up_child_processes(final_hook_project):
    child = "import time; from pathlib import Path; time.sleep(0.4); Path('orphan.txt').write_text('still running')"
    (final_hook_project / ".tools/bin/uv").write_text(
        f"#!{sys.executable}\n"
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, '-c', {child!r}])\n"
        "time.sleep(1)\n"
    )
    feedback = invoke_final_hook(final_hook_project, "--timeout", "0.1")
    assert feedback["decision"] == "block"
    assert "exit 124" in feedback["reason"]
    assert "Verification timed out" in feedback["reason"]
    time.sleep(0.5)
    assert not (final_hook_project / "orphan.txt").exists()


@pytest.mark.parametrize("failure", ["malformed_input", "unwritable_state"])
def test_final_hook_infrastructure_errors_return_blocking_json(final_hook_project, failure):
    event = "not-json" if failure == "malformed_input" else "{}"
    if failure == "unwritable_state":
        (final_hook_project / "data").write_text("a file prevents creating the verification directory")
    result = subprocess.run(
        [sys.executable, str(final_hook_project / "scripts/verify_before_finish.py")],
        input=event, text=True, capture_output=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    feedback = json.loads(result.stdout)
    assert feedback["decision"] == "block"
    assert "Do not claim completion" in feedback["reason"]
    assert "infrastructure failed" in feedback["reason"]


def test_continued_stop_rechecks_failures_and_allows_completion_only_after_repair(final_hook_project):
    outcomes = final_hook_project / "outcomes.json"
    outcomes.write_text(json.dumps({"run pytest -q -m browser": 1}))
    assert invoke_final_hook(final_hook_project)["decision"] == "block"
    assert invoke_final_hook(final_hook_project, active=True)["decision"] == "block"
    outcomes.write_text("{}")
    assert "final verification passed" in invoke_final_hook(final_hook_project, active=True)["systemMessage"]
    assert "decision" not in invoke_final_hook(final_hook_project)
