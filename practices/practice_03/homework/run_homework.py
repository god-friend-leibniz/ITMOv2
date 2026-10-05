"""Read-only OpenCode A/B on the student's Practice 1-2 project.

Only the agent prompt differs. All generated artifacts use exclusive writes.
The report is never modified here; its original prefix is checked separately.
"""
import argparse
import copy
import hashlib
import json
import os
import statistics
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
REPORT = HERE.parent / "REPORT.md"
ENDPOINT = "http://127.0.0.1:11435"
INPUTS = ["Makefile", "practices/practice_01/Makefile", "practices/practice_02/Makefile",
          "practices/practice_01/TRAINING_PR.diff", "practices/practice_01/context.md",
          "practices/practice_01/adr.md"]
ENV = dict(os.environ, OLLAMA_HOST="127.0.0.1:11435", PYTHONDONTWRITEBYTECODE="1",
           OPENCODE_DISABLE_AUTOUPDATE="1")


def save(path, value):
    with path.open("x", encoding="utf-8") as out:
        json.dump(value, out, ensure_ascii=False, indent=2)
        out.write("\n")


def command(args, env=ENV, timeout=180):
    started = time.perf_counter()
    try:
        proc = subprocess.run(args, cwd=REPO, env=env, capture_output=True,
                              text=True, timeout=timeout)
        return {"command": args, "exit_code": proc.returncode,
                "stdout": proc.stdout, "stderr": proc.stderr,
                "wall_seconds": time.perf_counter() - started}
    except subprocess.TimeoutExpired as exc:
        def text(value):
            return value.decode() if isinstance(value, bytes) else value or ""
        return {"command": args, "exit_code": None, "error": "timeout",
                "stdout": text(exc.stdout), "stderr": text(exc.stderr),
                "wall_seconds": time.perf_counter() - started}


def api(route, payload=None):
    req = urllib.request.Request(ENDPOINT + route,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as response:
        return json.load(response)


def hashes():
    return {name: hashlib.sha256((REPO / name).read_bytes()).hexdigest() for name in INPUTS}


def config(variant):
    permission = {"*": "deny", "read": {"*": "deny", **{name: "allow" for name in INPUTS}},
                  "glob": "deny", "grep": "deny", "bash": "deny", "task": "deny",
                  "skill": "deny", "webfetch": "deny", "websearch": "deny",
                  "edit": "deny", "external_directory": "deny"}
    return {"$schema": "https://opencode.ai/config.json", "model": "ollama/itmo-agent",
            "small_model": "ollama/itmo-agent", "default_agent": "homework",
            "enabled_providers": ["ollama"], "autoupdate": False, "share": "disabled",
            "snapshot": False, "plugin": [], "lsp": False, "formatter": False,
            "permission": permission,
            "provider": {"ollama": {"npm": "@ai-sdk/openai-compatible", "name": "Ollama local",
                "options": {"baseURL": ENDPOINT + "/v1"},
                "models": {"itmo-agent": {"tool_call": True, "options": {"think": False, "seed": 42},
                    "limit": {"context": 65536, "output": 2048}}}}},
            "agent": {"homework": {"description": "Read-only homework A/B repository assistant",
                "mode": "primary", "steps": 8, "temperature": 0.2,
                "permission": permission, "prompt": (HERE / f"system-{variant.lower()}.txt").read_text()}}}


def warm():
    started = time.perf_counter()
    result = api("/api/chat", {"model": "itmo-agent", "stream": False, "think": False,
        "messages": [{"role": "user", "content": "Ответь ровно: READY"}],
        "options": {"num_ctx": 65536, "temperature": 0.2, "seed": 42, "num_predict": 16}})
    return {"response": result, "wall_seconds": time.perf_counter() - started}


def prepare(results):
    report = REPORT.read_bytes()
    a, b = config("A"), config("B")
    left, right = copy.deepcopy(a), copy.deepcopy(b)
    assert left["agent"]["homework"].pop("prompt") != right["agent"]["homework"].pop("prompt")
    assert left == right
    save(results / "config-a.json", a)
    save(results / "config-b.json", b)
    records = [command(args) for args in (["sw_vers"], ["sysctl", "-n", "machdep.cpu.brand_string", "hw.memsize", "hw.ncpu"],
        ["df", "-h", "."], ["ollama", "--version"], ["opencode", "--version"],
        ["python3", "--version"], ["ollama", "show", "itmo-agent"], ["make", "test"])]
    assert all(r["exit_code"] == 0 for r in records), records
    save(results / "environment.json", {"date_utc": datetime.now(timezone.utc).isoformat(),
        "endpoint": ENDPOINT, "commands": records, "tags": api("/api/tags"),
        "inputs_sha256": hashes(), "report_original_bytes": len(report),
        "report_original_sha256": hashlib.sha256(report).hexdigest(), "only_prompt_changed": True})
    for variant in ("A", "B"):
        env = dict(ENV, OPENCODE_CONFIG_CONTENT=json.dumps(config(variant), ensure_ascii=False))
        resolved = command(["opencode", "debug", "config"], env=env)
        assert resolved["exit_code"] == 0
        effective = json.loads(resolved["stdout"])
        for provider in effective.get("provider", {}).values():
            if "apiKey" in provider.get("options", {}):
                provider["options"]["apiKey"] = "[redacted]"
        assert effective["enabled_providers"] == ["ollama"]
        assert not effective.get("mcp") and not effective.get("plugin")
        save(results / f"effective-{variant.lower()}.json", effective)
        guide = command(["opencode", "debug", "agent", "homework"], env=env)
        assert guide["exit_code"] == 0
        info = json.loads(guide["stdout"])
        assert {key for key, value in info["tools"].items() if value} == {"read"}
        save(results / f"agent-{variant.lower()}.json", info)
    print("Prepared; only the prompt differs; read is the only tool", flush=True)


def session(results, variant, question, name, frozen_config=None, retry_of=None):
    env = dict(ENV, OPENCODE_CONFIG_CONTENT=json.dumps(
        config(variant) if frozen_config is None else frozen_config, ensure_ascii=False))
    args = ["opencode", "run", "--pure", "--agent", "homework", "--model", "ollama/itmo-agent",
            "--title", name, "--format", "json", question]
    record = command(args, env=env)
    events, diagnostics = [], []
    excluded_reasoning_events = 0
    for line in record.pop("stdout").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            diagnostics.append(line)
            continue
        if event.get("type") == "reasoning" or event.get("part", {}).get("type") == "reasoning":
            excluded_reasoning_events += 1
        else:
            events.append(event)
    with (results / f"{name}.jsonl").open("x", encoding="utf-8") as out:
        for event in events:
            out.write(json.dumps(event, ensure_ascii=False) + "\n")
    answer = "\n".join(e["part"]["text"] for e in events if e.get("type") == "text")
    tools = [{"tool": e["part"]["tool"], "state": e["part"]["state"]}
             for e in events if e.get("type") == "tool_use"]
    record.update(name=name, variant=variant, question=question, answer=answer, tools=tools,
        excluded_reasoning_events=excluded_reasoning_events,
        session_ids=sorted({e["sessionID"] for e in events if "sessionID" in e}), diagnostics=diagnostics,
        output_tokens=sum(e["part"].get("tokens", {}).get("output", 0) for e in events if e.get("type") == "step_finish"))
    if retry_of:
        record["retry_of"] = retry_of
        record["included_in_original_ab"] = False
    save(results / f"{name}.json", record)
    print(name, "exit", record["exit_code"], "wall", round(record["wall_seconds"], 3), flush=True)
    print("ANSWER", answer, flush=True)
    print("TOOLS", [(t["tool"], t["state"]["status"], t["state"]["input"].get("filePath")) for t in tools], flush=True)
    return record


def run(results):
    questions = json.loads((HERE / "questions.json").read_text())
    save(results / "warmup.json", warm())
    save(results / "resources.json", {"ps": command(["ollama", "ps"]), "api_ps": api("/api/ps")})
    records = []
    for item in questions:
        for variant in ("A", "B"):
            records.append(session(results, variant, item["question"], f"{variant.lower()}-{item['id']}"))
    save(results / "answers.json", records)
    speeds = {"A": [], "B": []}
    for repeat in range(1, 4):
        for variant in ("A", "B"):
            save(results / f"warmup-{variant.lower()}-{repeat}.json", warm())
            speeds[variant].append(session(results, variant, questions[0]["question"], f"speed-{variant.lower()}-{repeat}"))
    save(results / "speed.json", {variant: {"runs": [r["name"] for r in runs],
        "wall_seconds": [r["wall_seconds"] for r in runs],
        "median_wall_seconds": statistics.median(r["wall_seconds"] for r in runs),
        "output_tokens": [r["output_tokens"] for r in runs],
        "method": "Three fresh warmed OpenCode sessions answering the same q1; wall includes CLI, inference and read tools",
        "ttft_measured": False} for variant, runs in speeds.items()})
    print("All 10 A/B answers and 6 warmed timing repeats saved", flush=True)


def retry(results, variant, question_id, attempt):
    """Retry an empty/failed primary result without altering the original A/B."""
    original_name = f"{variant.lower()}-{question_id}"
    original = json.loads((results / f"{original_name}.json").read_text())
    assert original["exit_code"] != 0 or not original["answer"].strip(), "Only failed/empty runs may be retried"
    manifest = json.loads((results / "environment.json").read_text())
    assert manifest["inputs_sha256"] == hashes(), "Input files changed"
    frozen = json.loads((results / f"config-{variant.lower()}.json").read_text())
    assert frozen == config(variant), "The original configuration must be preserved"
    old_model = next(m for m in manifest["tags"]["models"] if m["name"] == "itmo-agent:latest")
    current_model = next(m for m in api("/api/tags")["models"] if m["name"] == "itmo-agent:latest")
    assert old_model["digest"] == current_model["digest"], "Model changed"
    name = f"retry-{original_name}-{attempt}"
    assert not (results / f"{name}.json").exists() and not (results / f"{name}.jsonl").exists()
    save(results / f"warmup-{name}.json", warm())
    session(results, variant, original["question"], name, frozen_config=frozen,
            retry_of=original_name)


def validate(results, validation_name="validation.json"):
    manifest = json.loads((results / "environment.json").read_text())
    assert manifest["inputs_sha256"] == hashes(), "Input files changed"
    prefix = REPORT.read_bytes()[:manifest["report_original_bytes"]]
    assert hashlib.sha256(prefix).hexdigest() == manifest["report_original_sha256"], "Original report prefix changed"
    a = json.loads((results / "config-a.json").read_text())
    b = json.loads((results / "config-b.json").read_text())
    a["agent"]["homework"].pop("prompt")
    b["agent"]["homework"].pop("prompt")
    assert a == b
    records = json.loads((results / "answers.json").read_text())
    records += [json.loads((results / f"speed-{v}-{n}.json").read_text()) for n in (1, 2, 3) for v in ("a", "b")]
    retry_records = [json.loads(path.read_text()) for path in sorted(results.glob("retry-*-q[1-5]-*.json"))]
    records += retry_records
    ids = []
    allowed = {str(REPO / name) for name in INPUTS}
    denied = 0
    successful_reads = 0
    errors = []
    for record in records:
        if record["exit_code"] != 0 or not record["answer"]:
            errors.append(record["name"])
        assert len(record["session_ids"]) == 1
        ids += record["session_ids"]
        for tool in record["tools"]:
            assert tool["tool"] == "read"
            state = tool["state"]
            path = Path(state["input"]["filePath"])
            absolute = str(path if path.is_absolute() else REPO / path)
            if state["status"] == "completed":
                assert absolute in allowed, "Read escaped the allowed sources"
                successful_reads += 1
            else:
                denied += 1
        events = [json.loads(line) for line in (results / f"{record['name']}.jsonl").read_text().splitlines()]
        assert all(e.get("type") != "reasoning" and e.get("part", {}).get("type") != "reasoning" for e in events)
    assert len(set(ids)) == len(records) == 16 + len(retry_records)
    assert successful_reads > 0
    tests = command(["make", "test"])
    assert tests["exit_code"] == 0
    resources = json.loads((results / "resources.json").read_text())["api_ps"]["models"]
    assert any(m["name"] == "itmo-agent:latest" and m["context_length"] == 65536 for m in resources)
    save(results / validation_name, {"only_system_prompt_changed": True, "inputs_unchanged": True,
        "report_original_prefix_preserved": True, "fresh_sessions": len(set(ids)),
        "original_ab_and_speed_sessions": 16, "extra_retry_sessions": len(retry_records),
        "successful_reads": successful_reads, "failed_reads": denied,
        "only_allowed_sources_read": True, "reasoning_events_excluded": True,
        "failed_or_empty_runs": errors, "tests": tests, "resources_after": api("/api/ps")})
    print("Validated; failed or empty runs:", errors, flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("prepare", "run", "retry", "validate"))
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--variant", choices=("A", "B"), default="B")
    parser.add_argument("--question-id", choices=("q1", "q2", "q3", "q4", "q5"), default="q3")
    parser.add_argument("--attempt", type=int, choices=(1, 2), default=1)
    parser.add_argument("--validation-name", default="validation.json")
    args = parser.parse_args()
    if Path(args.validation_name).name != args.validation_name:
        parser.error("--validation-name must be a filename, not a path")
    results = args.results.resolve()
    results.mkdir(parents=True, exist_ok=True)
    if args.phase == "retry":
        retry(results, args.variant, args.question_id, args.attempt)
    elif args.phase == "validate":
        validate(results, args.validation_name)
    else:
        {"prepare": prepare, "run": run}[args.phase](results)


if __name__ == "__main__":
    main()
