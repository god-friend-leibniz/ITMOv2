import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


@pytest.fixture
def hook_project(tmp_path):
    root = Path(__file__).resolve().parents[1]
    (tmp_path / "scripts").mkdir()
    shutil.copy(root / "scripts/verify_after_change.py", tmp_path / "scripts")
    (tmp_path / ".venv").symlink_to(root / ".venv", target_is_directory=True)
    (tmp_path / "tests").mkdir()
    return tmp_path


def invoke_hook(project, *arguments):
    result = subprocess.run(
        [sys.executable, str(project / "scripts/verify_after_change.py"), *arguments],
        input=json.dumps({"hook_event_name": "PostToolUse", "tool_name": "apply_patch"}),
        text=True, capture_output=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_hook_reports_failing_tests_to_agent(hook_project):
    (hook_project / "tests/test_example.py").write_text(
        "def test_course_behavior():\n    assert False, 'course missing'\n"
    )
    feedback = invoke_hook(hook_project)
    assert feedback["decision"] == "block"
    assert "test_course_behavior" in feedback["hookSpecificOutput"]["additionalContext"]
    assert "1 failed" in feedback["hookSpecificOutput"]["additionalContext"]


def test_hook_checks_file_changes_and_skips_documentation_only_edits(hook_project):
    (hook_project / "tests/test_example.py").write_text("def test_example():\n    assert True\n")
    assert "1 passed" in invoke_hook(hook_project)["hookSpecificOutput"]["additionalContext"]
    (hook_project / "README.md").write_text("Documentation only\n")
    assert invoke_hook(hook_project) == {}

    extra = hook_project / "tests/test_new.py"
    extra.write_text("def test_new():\n    assert False\n")
    assert invoke_hook(hook_project)["decision"] == "block"
    assert invoke_hook(hook_project)["decision"] == "block"
    extra.unlink()
    assert "1 passed" in invoke_hook(hook_project)["hookSpecificOutput"]["additionalContext"]


@pytest.mark.parametrize("failure", ["missing_environment", "timeout", "no_tests", "corrupt_state"])
def test_hook_returns_feedback_for_verification_infrastructure_failures(hook_project, failure):
    arguments = []
    if failure == "missing_environment":
        (hook_project / ".venv").unlink()
    elif failure == "timeout":
        (hook_project / "tests/test_example.py").write_text(
            "import time\ndef test_slow():\n    time.sleep(10)\n"
        )
        arguments = ["--timeout", "0.1"]
    elif failure == "corrupt_state":
        directory = hook_project / "data/verification"
        directory.mkdir(parents=True)
        (directory / "last.json").write_text("not valid json")

    feedback = invoke_hook(hook_project, *arguments)
    assert feedback["decision"] == "block"
    assert feedback["hookSpecificOutput"]["additionalContext"]


def test_concurrent_hook_events_share_one_verification_result(hook_project):
    (hook_project / "tests/test_example.py").write_text(
        "import time\ndef test_example():\n    time.sleep(0.2)\n"
    )
    processes = [subprocess.Popen(
        [sys.executable, str(hook_project / "scripts/verify_after_change.py")],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    ) for _ in range(2)]
    for process in processes:
        process.stdin.write("{}")
        process.stdin.close()
        process.stdin = None
    results = [process.communicate(timeout=10) for process in processes]
    assert all(process.returncode == 0 for process in processes), results
    feedback = [json.loads(stdout) for stdout, _ in results]
    assert sum(bool(result) for result in feedback) == 1
    assert "1 passed" in next(result for result in feedback if result)["hookSpecificOutput"]["additionalContext"]
