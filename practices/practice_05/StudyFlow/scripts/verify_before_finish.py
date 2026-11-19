"""Synchronous Codex Stop verification; stdout is hook JSON only."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
COMMANDS = (("run", "pytest", "-q"), ("run", "pytest", "-q", "-m", "browser"), ("build",))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=60, help="Per-command timeout, at most 60 seconds")
    options = parser.parse_args()
    event = json.loads(("" if sys.stdin.isatty() else sys.stdin.read()) or "{}")
    uv = ROOT / ".tools/bin/uv"
    executable = str(uv) if uv.is_file() else shutil.which("uv") or "uv"
    environment = os.environ.copy()
    environment.setdefault("UV_CACHE_DIR", str(ROOT / ".uv-cache"))
    environment.setdefault("UV_PYTHON_INSTALL_DIR", str(ROOT / ".python"))
    environment["UV_OFFLINE"] = "1"
    environment["UV_FROZEN"] = "1"
    channel = environment.get("STUDYFLOW_BROWSER_CHANNEL")
    if channel is None and Path("/Applications/Google Chrome.app").is_dir():
        channel = "chrome"
    results = []
    for arguments in COMMANDS:
        command_environment = environment.copy()
        if arguments == COMMANDS[1] and channel:
            additions = shlex.split(command_environment.get("PYTEST_ADDOPTS", ""))
            command_environment["PYTEST_ADDOPTS"] = shlex.join([*additions, "--browser-channel", channel])
        try:
            process = subprocess.Popen(
                [executable, *arguments], cwd=ROOT, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True, env=command_environment,
            )
            try:
                output, _ = process.communicate(timeout=min(60, max(0.01, options.timeout)))
                exit_code = process.returncode
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                output, _ = process.communicate()
                exit_code, output = 124, output + "\nVerification timed out."
        except OSError as error:
            exit_code, output = 127, f"Cannot start verification: {error}"
        results.append({"command": "uv " + " ".join(arguments), "exit_code": exit_code, "output": output})
    summary = "\n".join(f"{result['command']}: exit {result['exit_code']}" for result in results)
    feedback = {"systemMessage": "StudyFlow final verification passed.\n" + summary}
    failures = [result for result in results if result["exit_code"]]
    if failures:
        diagnostics = "\n".join(f"{result['command']}\n{result['output'][-2000:]}" for result in failures)
        reason = ("StudyFlow final verification failed. Do not claim completion. Repair the failures, "
                  "then rerun all final checks.\n" + summary + "\n" + diagnostics)
        feedback = {"decision": "block", "reason": reason, "systemMessage": "StudyFlow final verification failed.\n" + summary}
    directory = ROOT / "data/verification"
    directory.mkdir(parents=True, exist_ok=True)
    state = {"timestamp": datetime.now(timezone.utc).isoformat(), "browser_channel": channel, "results": results, "feedback": feedback,
             "event": {key: event[key] for key in ("session_id", "turn_id", "hook_event_name", "stop_hook_active") if key in event}}
    (directory / "final-last.json").write_text(json.dumps(state, indent=2))
    with (directory / "final-runs.jsonl").open("a") as history:
        history.write(json.dumps(state) + "\n")
    print(json.dumps(feedback))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, TypeError) as error:
        print(json.dumps({
            "decision": "block",
            "reason": f"StudyFlow final verification infrastructure failed. Do not claim completion. Repair it and rerun verification.\n{error}",
            "systemMessage": "StudyFlow final verification infrastructure failed.",
        }))
