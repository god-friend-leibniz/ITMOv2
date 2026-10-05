"""Reproduce Practice 3 against the existing local Ollama server.

Generated records are exclusive writes; reruns use a new --results directory.
OpenCode receives only demo sources, never reports or reference answers.
"""
import argparse
import hashlib
import json
import os
import statistics
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEMO = ROOT / "demo"
ENDPOINT = "http://127.0.0.1:11435"
ENV = dict(os.environ, OLLAMA_HOST="127.0.0.1:11435", PYTHONDONTWRITEBYTECODE="1")


def save(path, data):
    with path.open("x", encoding="utf-8") as out:
        json.dump(data, out, ensure_ascii=False, indent=2)
        out.write("\n")


def command(args, cwd=ROOT, env=ENV, timeout=300):
    started = time.perf_counter()
    try:
        result = subprocess.run(args, cwd=cwd, env=env, text=True,
                                capture_output=True, timeout=timeout)
        return {"command": args, "cwd": str(cwd), "exit_code": result.returncode,
                "stdout": result.stdout, "stderr": result.stderr,
                "wall_seconds": time.perf_counter() - started}
    except subprocess.TimeoutExpired as exc:
        return {"command": args, "cwd": str(cwd), "exit_code": None,
                "error": "timeout", "timeout_seconds": timeout,
                "wall_seconds": time.perf_counter() - started,
                "stdout": (exc.stdout or b"").decode() if isinstance(exc.stdout, bytes) else exc.stdout or "",
                "stderr": (exc.stderr or b"").decode() if isinstance(exc.stderr, bytes) else exc.stderr or ""}


def api(route, payload=None):
    request = urllib.request.Request(ENDPOINT + route,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.load(response)


def hashes():
    return {str(p.relative_to(DEMO)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(DEMO.iterdir()) if p.is_file()}


def prepare(results):
    commands = [
        ["sw_vers"], ["sysctl", "-n", "machdep.cpu.brand_string", "hw.memsize", "hw.ncpu"],
        ["system_profiler", "SPDisplaysDataType"], ["df", "-h", str(ROOT)],
        ["ollama", "--version"], ["opencode", "--version"], ["python3", "--version"],
        ["make", "install"], ["make", "test"], ["ollama", "list"],
        ["ollama", "show", "qwen3.5:4b"],
        ["ollama", "create", "itmo-local", "-f", "Modelfile"],
        ["ollama", "create", "itmo-agent", "-f", "Modelfile.agent"],
        ["ollama", "show", "itmo-local", "--modelfile"],
        ["ollama", "show", "itmo-agent", "--modelfile"],
        ["ollama", "run", "itmo-local", "--think=false", "Объясни разницу между моделью и сервером двумя предложениями"],
    ]
    records = []
    for args in commands:
        print("RUN", " ".join(args), flush=True)
        record = command(args)
        records.append(record)
        print(record["stdout"][-1500:], record["stderr"][-300:], flush=True)
        if record["exit_code"] != 0:
            save(results / "prepare-error.json", records)
            raise SystemExit("Preparation failed; see prepare-error.json")
    save(results / "environment.json", {"date_utc": datetime.now(timezone.utc).isoformat(),
        "endpoint": ENDPOINT, "commands": records, "tags": api("/api/tags"),
        "demo_sha256": hashes()})


def experiments(results):
    # Explicitly unload the base model, so baseline includes a measurable cold load.
    save(results / "cold-unload.json", api("/api/generate", {
        "model": "qwen3.5:4b", "keep_alive": 0}))
    runs = [("baseline", "baseline", 0.2, 42), ("system", "system", 0.2, 42)]
    runs += [(f"baseline-warm{i}", "baseline", 0.2, 42) for i in range(1, 4)]
    runs += [(f"system-warm{i}", "system", 0.2, 42) for i in range(1, 4)]
    runs += [(f"low{seed}", "system", 0.2, seed) for seed in (42, 43, 44)]
    runs += [(f"hot{seed}", "system", 0.8, seed) for seed in (42, 43, 44)]
    for name, mode, temperature, seed in runs:
        args = ["python3", "experiment.py", "--mode", mode,
                "--temperature", str(temperature), "--seed", str(seed),
                "--output", str(results / (name + ".json"))]
        print("EXPERIMENT", name, flush=True)
        record = command(args)
        print(record["stdout"], record["stderr"], flush=True)
        if record["exit_code"] != 0:
            save(results / (name + "-error.json"), record)
            raise SystemExit("API experiment failed")
    names = {"baseline_warm": [f"baseline-warm{i}" for i in range(1, 4)],
             "system_warm": [f"system-warm{i}" for i in range(1, 4)],
             "temperature_0.2": [f"low{s}" for s in (42, 43, 44)],
             "temperature_0.8": [f"hot{s}" for s in (42, 43, 44)]}
    metrics = ("wall_seconds", "load_seconds", "total_seconds", "decode_tokens_per_second")
    summary = {}
    for group, files in names.items():
        records = [json.loads((results / (name + ".json")).read_text()) for name in files]
        summary[group] = {"files": files, "median": {
            metric: statistics.median(r[metric] for r in records) for metric in metrics}}
    save(results / "api-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


def test_config():
    config = json.loads((DEMO / "opencode.json").read_text())
    config.update(enabled_providers=["ollama"], autoupdate=False, share="disabled",
                  snapshot=False, plugin=[], lsp=False, formatter=False)
    config["provider"]["ollama"]["options"]["baseURL"] = ENDPOINT + "/v1"
    config["provider"]["ollama"]["models"]["itmo-agent"]["options"] = {"think": False}
    # Reject access to results, report and the rest of the parent repository.
    read = {"*": "deny"}
    for name in ("README.md", "Makefile", "service.py", "test_service.py"):
        read[str((DEMO / name).relative_to(ROOT.parents[2]))] = "allow"
        read[str(DEMO / name)] = "allow"
    permission = {"*": "deny", "read": read, "glob": "deny", "grep": "deny",
                  "bash": "deny", "task": "deny", "skill": "deny",
                  "webfetch": "deny", "websearch": "deny", "external_directory": "deny"}
    config["permission"] = permission
    config["agent"]["local-guide"]["permission"] = permission
    config["agent"]["local-guide"]["prompt"] = (DEMO / "repo-system.txt").read_text() + (
        "\nДоступные входные файлы: README.md, Makefile, service.py, test_service.py. "
        "Читай их инструментом read; другие инструменты запрещены. "
        "Для проверки отсутствующей функции или CI проверь все четыре файла.")
    return config


def agent(results, environment_results=None):
    ready = command(["ollama", "run", "itmo-agent", "--think=false", "Ответь: READY"])
    save(results / "agent-ready.json", ready)
    save(results / "agent-resources.json", {"ps": command(["ollama", "ps"]), "api_ps": api("/api/ps")})
    config = test_config()
    env = dict(ENV, OPENCODE_CONFIG_CONTENT=json.dumps(config, ensure_ascii=False),
               OPENCODE_DISABLE_AUTOUPDATE="1")
    # Inspect effective config without persisting credentials.
    resolved = command(["opencode", "debug", "config"], cwd=DEMO, env=env)
    if resolved["exit_code"] != 0:
        save(results / "config-error.json", resolved)
        raise SystemExit("OpenCode config failed")
    effective = json.loads(resolved["stdout"])
    for item in effective.get("provider", {}).values():
        if "apiKey" in item.get("options", {}):
            item["options"]["apiKey"] = "[redacted]"
    if any(m.get("enabled", True) for m in effective.get("mcp", {}).values()):
        raise SystemExit("Unexpected enabled MCP; isolate before running")
    save(results / "opencode-effective.json", effective)
    save(results / "opencode-runtime.json", config)
    save(results / "local-guide-effective.json", command(
        ["opencode", "debug", "agent", "local-guide"], cwd=DEMO, env=env))
    questions = [line.split(". ", 1)[1] for line in (ROOT / "QUESTIONS.md").read_text().splitlines()
                 if line[:1].isdigit() and ". " in line]
    tasks = [("read-check", "Прочитай README.md инструментом read. Назови команду тестирования со ссылкой на файл")]
    tasks += [(f"question{i}", question) for i, question in enumerate(questions, 1)]
    index = []
    for name, question in tasks:
        print("OPENCODE", name, question, flush=True)
        args = ["opencode", "run", "--pure", "--dir", str(DEMO), "--agent", "local-guide",
                "--model", "ollama/itmo-agent", "--title", name, "--format", "json", question]
        record = command(args, cwd=ROOT, env=env, timeout=300)
        events = []
        for line in record.pop("stdout").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "reasoning" or event.get("part", {}).get("type") == "reasoning":
                continue
            events.append(event)
        with (results / (name + ".jsonl")).open("x", encoding="utf-8") as out:
            for event in events:
                out.write(json.dumps(event, ensure_ascii=False) + "\n")
        texts = [e["part"]["text"] for e in events if e.get("type") == "text"]
        tools = [{"tool": e["part"]["tool"], "state": e["part"]["state"]}
                 for e in events if e.get("type") == "tool_use"]
        record.update(question=question, answer="\n".join(texts), tools=tools,
                      session_ids=sorted({e["sessionID"] for e in events if "sessionID" in e}))
        save(results / (name + "-run.json"), record)
        index.append({"name": name, **record})
        print("ANSWER", record["answer"], "TOOLS", [(t["tool"], t["state"]["status"]) for t in tools], flush=True)
    save(results / "agent-summary.json", index)
    before = json.loads(((environment_results or results) / "environment.json").read_text())["demo_sha256"]
    after = hashes()
    save(results / "verification.json", {"demo_unchanged": before == after,
        "before": before, "after": after, "tests": command(["make", "test"]),
        "agent_ps": command(["ollama", "ps"]), "agent_api_ps": api("/api/ps")})
    if before != after:
        raise SystemExit("Demo inputs changed")


def explain(results):
    config = {"model": "ollama/itmo-agent", "small_model": "ollama/itmo-agent",
              "enabled_providers": ["ollama"], "autoupdate": False, "share": "disabled",
              "snapshot": False, "permission": {"*": "deny"},
              "agent": {"build": {"permission": {"*": "deny"}}},
              "provider": {"ollama": {"npm": "@ai-sdk/openai-compatible",
                  "options": {"baseURL": ENDPOINT + "/v1"},
                  "models": {"itmo-agent": {"options": {"think": False},
                      "limit": {"context": 65536, "output": 1024}}}}}}
    prompt = ("Объясни по-русски FROM, PARAMETER и SYSTEM в этом Modelfile "
              "именно в контексте локальной LLM и Ollama. Затем объясни отличие "
              "SYSTEM от инструкций и прав агента OpenCode. Не используй инструменты.\n"
              + (ROOT / "Modelfile").read_text() + "\nПрофиль агента:\n"
              + (ROOT / "Modelfile.agent").read_text())
    env = dict(ENV, OPENCODE_CONFIG_CONTENT=json.dumps(config, ensure_ascii=False))
    record = command(["opencode", "run", "--pure", "--agent", "build", "--model",
                      "ollama/itmo-agent", "--title", "Modelfile explanation", "--format", "json", prompt], env=env)
    events = [json.loads(line) for line in record.pop("stdout").splitlines() if line.startswith("{")]
    events = [event for event in events if event.get("type") != "reasoning"
              and event.get("part", {}).get("type") != "reasoning"]
    record["events"] = events
    record["answer"] = "\n".join(e["part"]["text"] for e in events if e.get("type") == "text")
    save(results / "modelfile-explanation.json", record)
    print(record["answer"], flush=True)


def validate(results):
    baseline = json.loads((results / "baseline.json").read_text())
    system = json.loads((results / "system.json").read_text())
    base_request, system_request = baseline["request"], system["request"]
    assert base_request["messages"] == system_request["messages"][1:]
    assert {k: v for k, v in base_request.items() if k != "messages"} == {
        k: v for k, v in system_request.items() if k != "messages"}
    files = ["baseline", "system"] + [f"{mode}-warm{i}" for mode in ("baseline", "system") for i in (1, 2, 3)]
    files += [f"{mode}{seed}" for mode in ("low", "hot") for seed in (42, 43, 44)]
    for name in files:
        record = json.loads((results / (name + ".json")).read_text())
        assert record["response"]["done"] and record["response"]["done_reason"] == "stop"
        assert record["response"]["message"]["content"]
        assert not record["response"]["message"].get("thinking")
    for seed in (42, 43, 44):
        low = json.loads((results / f"low{seed}.json").read_text())["request"]
        hot = json.loads((results / f"hot{seed}.json").read_text())["request"]
        low["options"].pop("temperature")
        hot["options"].pop("temperature")
        assert low == hot
    agent_dir = results / "agent-corrected"
    runs = json.loads((agent_dir / "agent-summary.json").read_text())
    assert len(runs) == 6
    ids = [r["session_ids"][0] for r in runs]
    assert len(set(ids)) == 6
    allowed = {str(DEMO / name) for name in ("README.md", "Makefile", "service.py", "test_service.py")}
    blocked_reads = 0
    for run in runs:
        assert run["exit_code"] == 0 and run["answer"]
        for tool in run["tools"]:
            assert tool["tool"] == "read"
            if tool["state"]["status"] == "completed":
                assert tool["state"]["input"]["filePath"] in allowed
            else:
                assert tool["state"]["status"] == "error"
                assert tool["state"]["input"]["filePath"] not in allowed
                assert "rule which prevents" in tool["state"]["error"]
                blocked_reads += 1
        events = [json.loads(line) for line in (agent_dir / (run["name"] + ".jsonl")).read_text().splitlines()]
        assert all(e.get("type") != "reasoning" and e.get("part", {}).get("type") != "reasoning" for e in events)
    assert runs[0]["tools"][0]["state"]["input"]["filePath"] == str(DEMO / "README.md")
    verification = json.loads((agent_dir / "verification.json").read_text())
    assert verification["demo_unchanged"] and verification["tests"]["exit_code"] == 0
    config = json.loads((agent_dir / "opencode-effective.json").read_text())
    assert config["enabled_providers"] == ["ollama"] and not config.get("plugin") and not config.get("mcp")
    assert config["provider"]["ollama"]["options"]["baseURL"] == ENDPOINT + "/v1"
    resources = json.loads((agent_dir / "agent-resources.json").read_text())["api_ps"]["models"]
    assert any(m["name"] == "itmo-agent:latest" and m["context_length"] == 65536 for m in resources)
    save(results / "validation.json", {"api_records": len(files), "only_system_prompt_changed": True,
        "only_temperature_changed": True, "fresh_opencode_sessions": len(set(ids)),
        "only_allowed_files_read": True, "blocked_reads": blocked_reads, "read_tool_confirmed": True,
        "no_reasoning_events_saved": True, "demo_unchanged": True, "tests_passed": True,
        "local_provider_only": True, "agent_context": 65536})
    print("Validation passed", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("prepare", "api", "agent", "explain", "validate"))
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--agent-attempt", help="Separate directory for an agent retry; preserves earlier evidence")
    args = parser.parse_args()
    results = args.results.resolve()
    results.mkdir(parents=True, exist_ok=True)
    if args.phase == "agent" and args.agent_attempt:
        attempt = results / args.agent_attempt
        attempt.mkdir(exist_ok=False)
        agent(attempt, environment_results=results)
        return
    {"prepare": prepare, "api": experiments, "agent": agent,
     "explain": explain, "validate": validate}[args.phase](results)


if __name__ == "__main__":
    main()
