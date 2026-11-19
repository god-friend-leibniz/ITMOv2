"""Synchronous Codex PostToolUse verification; stdout is hook JSON only."""

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
WATCHED = ("studyflow", "studyflow_mcp", "migrations", "tests", "scripts", "pyproject.toml", "uv.lock", ".codex/hooks.json")


def fingerprint():
    digest = hashlib.sha256()
    for name in WATCHED:
        path = ROOT / name
        paths = sorted(path.rglob("*")) if path.is_dir() else [path]
        for file in paths:
            if not file.is_file() or "__pycache__" in file.parts or file.suffix in {".pyc", ".md"}:
                continue
            digest.update(str(file.relative_to(ROOT)).encode() + b"\0")
            digest.update(file.read_bytes() + b"\0")
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--timeout", type=float, default=60)
    arguments = parser.parse_args()
    event = json.loads(("" if sys.stdin.isatty() else sys.stdin.read()) or "{}")
    event = {key: event[key] for key in (
        "session_id", "turn_id", "hook_event_name", "tool_name", "tool_use_id"
    ) if key in event}
    directory = ROOT / "data/verification"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        verify(event, directory, arguments)


def verify(event, directory, arguments):
    snapshot = fingerprint()
    state_path = directory / "last.json"
    previous = json.loads(state_path.read_text()) if state_path.exists() and not arguments.force else {}
    if previous.get("fingerprint") == snapshot and not arguments.force:
        print(json.dumps(previous["feedback"] if previous["exit_code"] else {}))
        return

    try:
        result = subprocess.run(
            [str(ROOT / ".venv/bin/python"), "-m", "pytest", "-q"],
            cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=min(60, max(0.01, arguments.timeout)),
        )
        exit_code, output = result.returncode, result.stdout
    except subprocess.TimeoutExpired as error:
        exit_code = 124
        output = (error.stdout or b"").decode(errors="replace") + "\nVerification timed out."
    except OSError as error:
        exit_code, output = 127, f"Cannot start verification: {error}"
    feedback = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": f"StudyFlow tests: exit {exit_code}\n{output[-8000:]}",
        }
    }
    if exit_code:
        feedback.update(decision="block", reason="StudyFlow verification failed. Repair failing tests before unrelated work.")
    stamp = datetime.now(timezone.utc).isoformat()
    (directory / "pytest.log").write_text(output)
    state = {
        "timestamp": stamp, "fingerprint": snapshot, "exit_code": exit_code,
        "feedback": feedback, "event": event,
    }
    state_path.write_text(json.dumps(state, indent=2))
    with (directory / "runs.jsonl").open("a") as history:
        history.write(json.dumps(state) + "\n")
    print(json.dumps(feedback))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        print(json.dumps({
            "decision": "block",
            "reason": "StudyFlow verification infrastructure failed. Repair it before unrelated work.",
            "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": str(error)},
        }))
