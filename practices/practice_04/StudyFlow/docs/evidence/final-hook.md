# Final verification hook

Implemented and demonstrated on 2026-10-06 with Codex CLI **0.160.1**. The existing PostToolUse definition remains unchanged, including its command, matcher, 75-second timeout, and trusted hash. Final verification is a separate synchronous **Stop** hook in [.codex/hooks.json](../../.codex/hooks.json), running [verify_before_finish.py](../../scripts/verify_before_finish.py).

## Installed lifecycle contract

Inspected `codex --version`, generated the experimental app-server schema with `codex app-server generate-json-schema --experimental`, and extracted the embedded `stop.command.input` / `stop.command.output` schemas from the installed binary. [The captured schemas](final-hook-schema.json) identify Stop, its `stop_hook_active` input, and supported output fields. The output allows `decision: "block"` with `reason`, and has no PostToolUse-style `hookSpecificOutput`. This agrees with the [official Stop documentation](https://learn.chatgpt.com/docs/hooks#stop).

A blocking reason becomes a continuation prompt. Stop does not retract text the assistant already emitted; AGENTS.md therefore instructs agents to defer completion claims until verification passes. The handler never returns `continue: false` or skips an active Stop check. Its nonempty reason includes failed commands and bounded output so the continued agent can repair them. Successful output reports each command's exit status through `systemMessage`.

## Handler and TDD

Every finish attempt runs these commands in order, including remaining checks after an earlier failure:

1. `uv run pytest -q`
2. `uv run pytest -q -m browser`
3. `uv build`

The standard-library handler locates StudyFlow from its file, uses local uv when present, enforces offline/frozen operation, and keeps default tooling caches local. For this macOS environment, browser-only `PYTEST_ADDOPTS` selects installed Chrome while leaving the requested command unchanged. `STUDYFLOW_BROWSER_CHANNEL` overrides the selection; an empty value requires bundled Chromium. Dependencies and a browser must be prepared beforehand. Each command has a 60-second limit inside the 200-second hook budget; timed-out process groups are killed.

The public hook command boundary was exercised through subprocess tests with an isolated uv executable fixture; application/domain functions were not mocked. The installed TDD skill guided these observed red → green steps:

| Behavior | Observed red | Green implementation |
| --- | --- | --- |
| Ordered final checks and success feedback | Handler file absent | Run the three commands and return valid Stop JSON |
| Any failed check requests continuation | Offline, browser, and build failures lacked `decision` | Return `decision: block`, actionable reason, and command diagnostics |
| Missing uv blocks completion | Handler raised TypeError / exited without feedback | Capture startup failures as exit 127 and block |
| Timeout and subprocess cleanup | Timeout option ignored; checks reported success | Enforce deadline, kill process group, report exit 124 |
| Infrastructure errors block completion | Malformed input and invalid evidence directory raised | Return blocking JSON instead of an unhandled exception |

An additional retry test passed immediately: failure remains blocked with `stop_hook_active: true`, repair permits completion, and another finish attempt reruns verification. It is regression coverage, not a claimed extra red/green cycle. Nine new routine test cases bring the routine suite to **44**; the browser suite remains **10**.

Full stage output and event metadata are saved separately from the fast cache in ignored `data/verification/final-last.json` and `final-runs.jsonl`. Hook JSON is delivered with process exit 0 even for a failed check; callers must inspect `decision` and the recorded command exits. A manual handler invocation passed all three real commands before runtime registration.

## Trust and actual runtime demonstration

`hooks/list` recognized the new Stop entry with no configuration errors. Its hash is `sha256:d85b56b29845aa1288efb56b40c627650d6cece744c725e20dc3814d7efd7081`. The existing PostToolUse hash remains `sha256:11a11971cdc9b12d1a03cf1249c23a1abed52255bebe0be83b3f301239ea20d0` and remained trusted. After the user's explicit “Final hook trusted” reply, the CLI initially still reported untrusted. Persisting that exact approval through Codex's configuration API made both entries enabled/trusted. Machine-local approval is not committed in this repository.

A fresh real Codex runtime used a local deterministic Responses fixture to replay a temporary browser-marked failing test, a finish attempt, removal of that test after continuation, and a second finish attempt. No model/API request, delegated development, or hook-trust bypass was used. Codex's real tool dispatcher and hook engine executed the edits and verification commands. The fixture confirmed the blocking reason reached the next model-input request. Its unsupported model-catalog endpoint caused metadata warnings but did not affect hook execution.

| UTC time | Actual automatic event | Outcome |
| --- | --- | --- |
| 18:32:05 | Stop, `stop_hook_active: false` | Offline: 44 passed; browser: 1 deliberate failure / 10 passed; build: success. Returned block and continuation reason. |
| 18:32:32 | Stop after repair, `stop_hook_active: true` | Offline: 44 passed; browser: 10 passed; build: success. No block. |

Both intervening PostToolUse events passed the fast suite. The browser-only failure therefore demonstrated why the separate final gate is needed. The fresh runtime made four fixture requests, received the automatic continuation, emitted `turn.completed` only after repair and the green Stop check, and exited 0. Sanitized original handler records are in [final-hook-runtime.json](final-hook-runtime.json). The temporary failing test was removed.

The all-green final run produced the wheel and source archive. A pre-existing TestClient deprecation warning and the known local uv-cache build warning did not fail checks. No application behavior, domain rules, glossary, or ADR changed. AGENTS.md, spec.md, README, reflection, and hook evidence were updated. Existing first/second-slice evidence remains historical.

## MCP slice update, 2026-10-07

A fresh Codex 0.160.1 runtime discovered and called the registered StudyFlow MCP, then automatically invoked the unchanged trusted Stop hook. [mcp-runtime.json](mcp-runtime.json) captures genuine Stop event metadata and exit 0 for 216 offline tests, 53 browser tests, and the build. Codex emitted turn completion only after these checks passed. The separate initial live MCP evidence probe rejected the rate-limited success/404 attempts and left that demonstration pending at that point. Final pytest/build success does not imply live GitHub availability. The original failure → automatic continuation → repair demonstration remains unchanged above.

After the user provided a token in ignored `.env`, another fresh runtime passed the actual live summary, invalid-input, and missing-repository checks. Its automatic Stop result at `2026-10-07T11:39:39.289119+00:00` again passed 216 offline tests, 53 browser tests, and the build, each exit 0. [mcp-authenticated-runtime.json](mcp-authenticated-runtime.json) captures the event and sanitized results; [mcp.md](mcp.md) records completed live evidence. Definitions, trust, and application tests were unchanged.
