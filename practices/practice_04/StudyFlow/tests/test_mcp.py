import asyncio
from datetime import datetime, timezone
import json
import time

import httpx
import jsonschema
from mcp import Client
from mcp.shared.exceptions import MCPError
import pytest


METADATA = {
    "owner": {"login": "Octocat"}, "name": "Hello-World", "private": False,
    "description": "Coursework examples", "default_branch": "main", "pushed_at": "2026-01-02T03:04:05Z",
}


def test_tool_discovery_and_successful_summary_use_only_repository_and_languages_endpoints():
    from studyflow_mcp.server import create_server

    requests = []

    def github(request):
        requests.append(request)
        if request.url.path.endswith("/languages"):
            return httpx.Response(200, json={"JavaScript": 300, "Python": 600, "C": 300, "Ruby": 100})
        return httpx.Response(200, json=METADATA)

    async def scenario():
        async with Client(create_server(transport=httpx.MockTransport(github))) as client:
            listing = await client.list_tools()
            assert [tool.name for tool in listing.tools] == ["get_repository_summary"]
            tool = listing.tools[0]
            assert set(tool.input_schema["required"]) == {"owner", "repo"}
            assert tool.input_schema["additionalProperties"] is False
            assert tool.output_schema is not None
            before = datetime.now(timezone.utc)
            result = await client.call_tool(tool.name, {"owner": "OCTOCAT", "repo": "Hello-World"})
            assert result.is_error is False
            payload = result.structured_content
            jsonschema.validate(payload, tool.output_schema)
            assert json.loads(result.content[0].text) == payload
            assert payload == {"ok": True, "error": None, "summary": {
                "owner": "Octocat", "name": "Hello-World", "url": "https://github.com/Octocat/Hello-World",
                "description": "Coursework examples", "default_branch": "main",
                "primary_languages": ["Python", "C", "JavaScript"], "last_push_at": "2026-01-02T03:04:05Z",
                "fetched_at": payload["summary"]["fetched_at"],
            }}
            assert before <= datetime.fromisoformat(payload["summary"]["fetched_at"]) <= datetime.now(timezone.utc)

    asyncio.run(scenario())
    assert [str(request.url) for request in requests] == [
        "https://api.github.com/repos/octocat/hello-world",
        "https://api.github.com/repos/octocat/hello-world/languages",
    ]
    assert all(request.method == "GET" for request in requests)
    assert all(request.headers["X-GitHub-Api-Version"] == "2026-03-10" for request in requests)


def test_unadvertised_tool_is_rejected_before_github_access():
    from studyflow_mcp.server import create_server

    requests = []

    def github(request):
        requests.append(request)
        return httpx.Response(200, json={} if request.url.path.endswith("/languages") else METADATA)

    async def scenario():
        async with Client(create_server(transport=httpx.MockTransport(github))) as client:
            with pytest.raises(MCPError) as error:
                await client.call_tool("delete_repository", {"owner": "octocat", "repo": "hello-world"})
            assert error.value.code == -32602
            assert error.value.message == "Unknown tool."

    asyncio.run(scenario())
    assert requests == []


@pytest.mark.parametrize("arguments", [
    {"owner": "bad/owner", "repo": "example"},
    {"owner": "octocat", "repo": ".."},
    {"owner": " octocat", "repo": "example"},
    {"owner": "octocat\n", "repo": "example"},
    {"owner": "octocat"},
    {"owner": True, "repo": "example"},
    {"owner": "octocat", "repo": ["example"]},
    {"owner": "octocat", "repo": "example", "url": "https://example.com"},
])
def test_invalid_tool_arguments_return_readable_error_without_github_access(arguments):
    from studyflow_mcp.server import create_server

    def forbidden(request):
        pytest.fail("Invalid arguments must not reach GitHub.")

    async def scenario():
        async with Client(create_server(transport=httpx.MockTransport(forbidden))) as client:
            tool = (await client.list_tools()).tools[0]
            result = await client.call_tool(tool.name, arguments)
            assert result.is_error is True
            assert result.content[0].text
            if result.structured_content is not None:
                jsonschema.validate(result.structured_content, tool.output_schema)
                assert result.structured_content["error"]["code"] == "INVALID_INPUT"
                assert result.structured_content["summary"] is None

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["missing", "private", "languages_missing"])
def test_missing_or_private_repository_returns_safe_error_without_partial_summary(failure):
    from studyflow_mcp.server import create_server

    requests = []

    def github(request):
        requests.append(request)
        if failure == "missing" or request.url.path.endswith("/languages"):
            return httpx.Response(404, json={"message": "upstream details must not be exposed"})
        return httpx.Response(200, json={**METADATA, "private": failure == "private"})

    async def scenario():
        async with Client(create_server(transport=httpx.MockTransport(github))) as client:
            tool = (await client.list_tools()).tools[0]
            result = await client.call_tool(tool.name, {"owner": "octocat", "repo": "hello-world"})
            assert result.is_error is True
            payload = result.structured_content
            jsonschema.validate(payload, tool.output_schema)
            assert payload == {"ok": False, "summary": None, "error": {
                "code": "REPOSITORY_NOT_FOUND", "message": "Repository not found or unavailable.", "retry_after_seconds": None,
            }}
            assert json.loads(result.content[0].text) == payload

    asyncio.run(scenario())
    assert len(requests) == (2 if failure == "languages_missing" else 1)


@pytest.mark.parametrize("status, headers, code, retry", [
    (301, {"Location": "https://other.example/repo"}, "REPOSITORY_MOVED", None),
    (302, {"Location": "https://other.example/repo"}, "REPOSITORY_MOVED", None),
    (307, {"Location": "https://other.example/repo"}, "REPOSITORY_MOVED", None),
    (308, {"Location": "https://other.example/repo"}, "REPOSITORY_MOVED", None),
    (429, {"Retry-After": "8"}, "RATE_LIMITED", 8),
    (403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "0"}, "RATE_LIMITED", 0),
    (403, {"Retry-After": "5"}, "RATE_LIMITED", 5),
    (401, {}, "GITHUB_AUTH_ERROR", None),
    (403, {}, "GITHUB_AUTH_ERROR", None),
    (500, {}, "GITHUB_UNAVAILABLE", None),
    (418, {}, "GITHUB_UNAVAILABLE", None),
])
def test_upstream_statuses_return_safe_tool_errors_without_retry_or_redirect(status, headers, code, retry):
    from studyflow_mcp.server import create_server

    requests = []

    def github(request):
        requests.append(request)
        return httpx.Response(status, headers=headers, json={"message": "Do not leak this upstream message"})

    async def scenario():
        async with Client(create_server(transport=httpx.MockTransport(github))) as client:
            tool = (await client.list_tools()).tools[0]
            result = await client.call_tool(tool.name, {"owner": "octocat", "repo": "hello-world"})
            assert result.is_error is True
            payload = result.structured_content
            jsonschema.validate(payload, tool.output_schema)
            assert payload["summary"] is None
            assert payload["error"]["code"] == code
            assert payload["error"]["retry_after_seconds"] == retry
            assert "Do not leak" not in result.content[0].text

    asyncio.run(scenario())
    assert len(requests) == 1


@pytest.mark.parametrize("failure", [
    "timeout", "connection", "invalid_json", "metadata_array", "missing_owner", "private_wrong_type",
    "unsafe_owner", "empty_name", "bad_timestamp", "languages_array", "negative_bytes", "boolean_bytes", "empty_language",
])
def test_transport_and_malformed_upstream_data_return_unavailable_without_partial_summary(failure):
    from studyflow_mcp.server import create_server

    def github(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("Do not expose exception details", request=request)
        if failure == "connection":
            raise httpx.ConnectError("Do not expose exception details", request=request)
        if failure == "invalid_json":
            return httpx.Response(200, text="not JSON")
        if request.url.path.endswith("/languages"):
            languages = {
                "languages_array": [], "negative_bytes": {"Python": -1},
                "boolean_bytes": {"Python": True}, "empty_language": {"": 100},
            }.get(failure, {"Python": 100})
            return httpx.Response(200, json=languages)
        metadata = {
            "metadata_array": [], "missing_owner": {"private": False},
            "private_wrong_type": {**METADATA, "private": "false"},
            "unsafe_owner": {**METADATA, "owner": {"login": "bad/owner"}},
            "empty_name": {**METADATA, "name": ""},
            "bad_timestamp": {**METADATA, "pushed_at": "2026-02-30T12:00:00Z"},
        }.get(failure, METADATA)
        return httpx.Response(200, json=metadata)

    async def scenario():
        async with Client(create_server(transport=httpx.MockTransport(github))) as client:
            result = await client.call_tool("get_repository_summary", {"owner": "octocat", "repo": "hello-world"})
            assert result.is_error is True
            assert result.structured_content == {"ok": False, "summary": None, "error": {
                "code": "GITHUB_UNAVAILABLE", "message": "GitHub is unavailable. Please try again.", "retry_after_seconds": None,
            }}

    asyncio.run(scenario())


@pytest.mark.parametrize("private", [False, True])
def test_optional_token_is_used_only_for_github_requests_and_does_not_enable_private_repositories(monkeypatch, private):
    from studyflow_mcp.server import create_server

    monkeypatch.setenv("GITHUB_TOKEN", "fixture-token")

    def github(request):
        assert request.headers["Authorization"] == "Bearer fixture-token"
        if request.url.path.endswith("/languages"):
            return httpx.Response(200, json={})
        return httpx.Response(200, json={**METADATA, "private": private, "description": None, "default_branch": None, "pushed_at": None})

    async def scenario():
        async with Client(create_server(transport=httpx.MockTransport(github))) as client:
            result = await client.call_tool("get_repository_summary", {"owner": "octocat", "repo": "hello-world"})
            assert result.is_error is private
            assert "fixture-token" not in result.content[0].text
            if private:
                assert result.structured_content["error"]["code"] == "REPOSITORY_NOT_FOUND"
            else:
                summary = result.structured_content["summary"]
                assert summary["description"] is None
                assert summary["default_branch"] is None
                assert summary["last_push_at"] is None
                assert summary["primary_languages"] == []

    asyncio.run(scenario())


def test_unexpected_server_exception_returns_safe_internal_error():
    from studyflow_mcp.server import create_server

    def github(request):
        raise RuntimeError("Sensitive internal exception details")

    async def scenario():
        async with Client(create_server(transport=httpx.MockTransport(github))) as client:
            result = await client.call_tool("get_repository_summary", {"owner": "octocat", "repo": "hello-world"})
            assert result.is_error is True
            assert result.structured_content["error"]["code"] == "INTERNAL_ERROR"
            assert result.structured_content["summary"] is None
            assert "Sensitive" not in result.content[0].text

    asyncio.run(scenario())


@pytest.mark.parametrize("status, headers, body, retry", [
    (403, {}, {"message": "You have exceeded a secondary rate limit."}, None),
    (429, {"Retry-After": "Thu, 01 Jan 1970 00:16:49 GMT"}, {}, 9),
    (403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1007"}, {}, 7),
    (429, {"Retry-After": "invalid"}, {}, None),
])
def test_rate_limits_recognize_secondary_limits_and_normalize_retry_headers(monkeypatch, status, headers, body, retry):
    from studyflow_mcp.server import create_server

    monkeypatch.setattr(time, "time", lambda: 1000)

    async def scenario():
        transport = httpx.MockTransport(lambda request: httpx.Response(status, headers=headers, json=body))
        async with Client(create_server(transport=transport)) as client:
            result = await client.call_tool("get_repository_summary", {"owner": "octocat", "repo": "hello-world"})
            assert result.is_error is True
            assert result.structured_content["error"]["code"] == "RATE_LIMITED"
            assert result.structured_content["error"]["retry_after_seconds"] == retry

    asyncio.run(scenario())
