# StudyFlow MCP evidence

Recorded on **2026-10-07** with Python 3.12.15, official MCP Python SDK **2.3.0**, Codex CLI **0.160.1**, and pinned GitHub API **2026-03-10**. **Slice 6 is complete**, including actual agent discovery, live success, invalid-input rejection, and a verified missing-repository error. The earlier unauthenticated rate-limit attempts are preserved below. Fixtures are not presented as live success/404 evidence.

## Registration and actual discovery

[.codex/config.toml](../../.codex/config.toml) registers the single read-only tool:

```toml
[mcp_servers.studyflow_github]
command = ".venv/bin/python"
args = ["-m", "studyflow_mcp.server"]
env_vars = ["GITHUB_TOKEN"]
startup_timeout_sec = 10
tool_timeout_sec = 15
enabled_tools = ["get_repository_summary"]
```

Run `uv sync --frozen`, then launch Codex from StudyFlow. `codex mcp get studyflow_github --json` returned enabled=true, stdio transport, the exact command/arguments, no literal environment secrets, and the two timeouts. The standalone server command is `uv run python -m studyflow_mcp.server`. Project configuration and stdio environment forwarding follow [official Codex MCP documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

A fresh real Codex runtime discovered namespace `mcp__studyflow_github` with only `get_repository_summary`, its `owner`/`repo` inputs, and no additional arguments. Codex's model-visible schema simplifies some constraints; the server's full advertised schemas and runtime validation are tested through `tools/list`/`tools/call`. The two packages are also present and callable after isolated wheel installation.

To exercise actual dispatch without a model API, a temporary local deterministic Responses fixture emitted fixed calls with that discovered namespace/name. The real Codex dispatcher, real registered stdio process, real GitHub HTTP client, and trusted Stop hook ran. No development agent was delegated work and no GitHub responses were stubbed. The initial run had no token; the authenticated rerun loaded the user's token from ignored `.env` into process environment only. Its exact value was checked absent from the saved evidence. The probe first assumed a flat tool catalogue/call name; inspecting nested namespaces corrected the harness without changing StudyFlow. Its unsupported model-catalog endpoint caused metadata warnings but did not prevent tool execution.

## Successful authenticated demonstration

After the user supplied a local token, the existing tool and registration worked without application/configuration changes. Sanitized original events, agent-received outputs, timestamps, and automatic Stop results are in [mcp-authenticated-runtime.json](mcp-authenticated-runtime.json). The probe exited 0 after checking the actual structured results and final verification; no result was inferred from a fixture.

| UTC fixture request before dispatch | Arguments | Actual result |
| --- | --- | --- |
| 11:38:41.823575 | `{"owner":"octocat","repo":"Hello-World"}` | Successful summary; Codex status `completed` |
| 11:38:43.344177 | `{"owner":"bad/owner","repo":"example"}` | `INVALID_INPUT`; Codex status `failed` |
| 11:38:43.353736 | `{"owner":"octocat","repo":"studyflow-missing-33cce9c543224d3a9623d3bc0a68bc8f"}` | `REPOSITORY_NOT_FOUND` from live GitHub; Codex status `failed` |

The success and missing-repository calls used live GitHub. The invalid input was rejected before HTTP, as independently enforced by the automated no-network test. The actual normalized success payload was:

```json
{
  "ok": true,
  "summary": {
    "owner": "octocat",
    "name": "Hello-World",
    "url": "https://github.com/octocat/Hello-World",
    "description": "My first repository on GitHub!",
    "default_branch": "master",
    "primary_languages": [],
    "last_push_at": "2024-08-20T23:54:42Z",
    "fetched_at": "2026-10-07T11:38:43.326239Z"
  },
  "error": null
}
```

This is observed mutable metadata, not a hardcoded automated-test expectation. The actual missing-repository payload was:

```json
{"ok":false,"summary":null,"error":{"code":"REPOSITORY_NOT_FOUND","message":"Repository not found or unavailable.","retry_after_seconds":null}}
```

The existing environment-only token boundary was retained. `uv run --offline --frozen --env-file .env python ...` was separately checked to load a nonempty `GITHUB_TOKEN` without printing it. To launch an authenticated agent from StudyFlow, use `uv run --frozen --env-file .env codex`; for the web app, use the corresponding `uvicorn` launch in README. Neither process automatically loads `.env` itself. The file is ignored by Git and excluded from the generated distributions.

The same fresh runtime automatically invoked Stop at `2026-10-07T11:39:39.289119+00:00`: offline **216 passed** (21.92 seconds), browser **53 passed** (32.17 seconds), build success; all three exits were 0. Genuine Stop event metadata is captured in the authenticated record. Codex emitted `turn.completed` only after that gate passed. Hook definitions/trust and application tests were unchanged; no new red/green cycle was needed for this environment-only retry.

## Initial unauthenticated attempts

Sanitized original dispatch events, tool outputs received by the agent, timestamps, and the automatic final-hook record are in [mcp-runtime.json](mcp-runtime.json).

| UTC fixture request before dispatch | Arguments | Actual result |
| --- | --- | --- |
| 11:20:15.680066 | `{"owner":"octocat","repo":"Hello-World"}` | `RATE_LIMITED`, retry_after_seconds=1661; no summary |
| 11:20:16.587863 | `{"owner":"bad/owner","repo":"example"}` | `INVALID_INPUT`; no summary |
| 11:20:16.604767 | `{"owner":"octocat","repo":"studyflow-missing-617a57d510144250861a74d65731e8ee"}` | `RATE_LIMITED`, retry_after_seconds=1658; absence not verified |

The first and third calls used **live GitHub**. The invalid-input call was rejected before HTTP; automated boundary tests additionally enforce this with an HTTP transport that fails on any request. Codex records these tool results with status `failed` and the structured error payload; tests verify MCP `isError=true` and matching JSON text.

Example actual rate-limit payload:

```json
{"ok":false,"summary":null,"error":{"code":"RATE_LIMITED","message":"GitHub rate limit reached. Please retry later.","retry_after_seconds":1661}}
```

Example actual validation payload:

```json
{"ok":false,"summary":null,"error":{"code":"INVALID_INPUT","message":"Provide a valid GitHub owner and repository name.","retry_after_seconds":null}}
```

The initial evidence probe's success/404 assertions failed rather than accepting these as the required results. The authenticated rerun above then passed both assertions with actual live responses. The first attempted missing name remains unverified; the newly generated name in the successful rerun is the verified missing reference. This preserves rate-limit history without relabeling it as success.

## Deterministic integration evidence

[test_mcp.py](../../tests/test_mcp.py) exercises actual MCP discovery/calls with controlled GitHub HTTP responses: normalized canonical names, description/default branch, top-three language ordering, push/fetch timestamps, null metadata/no languages, strict validation, no HTTP for invalid input, missing/private/moved repositories, rate limits, auth, timeouts, malformed data, and safe internal errors.

[test_repository_summary.py](../../tests/test_repository_summary.py) starts actual stdio servers. Its success/failure fixtures replace only GitHub HTTP, while protocol initialization, tool calls, result validation, cleanup, web error mapping, token forwarding, and SQLite remain real. Additional broken-protocol fixtures verify safe errors and deadline cleanup. These successes prove the integration works under controlled conditions; they do not replace live GitHub evidence. [Slice evidence](sixth-slice.md) records TDD and browser checks.

The current automatic Stop gate passed **216 offline tests, 53 browser tests, and the build**. The live demo is opt-in and stays outside both verification hooks. SDK contract choices follow the [official Python SDK](https://github.com/modelcontextprotocol/python-sdk) and [MCP tools specification](https://modelcontextprotocol.io/specification/2025-11-25/server/tools); the API pin follows [GitHub version guidance](https://docs.github.com/en/rest/about-the-rest-api/api-versions).
