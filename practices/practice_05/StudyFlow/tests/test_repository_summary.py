from functools import partial
import os
from pathlib import Path
import sys
import time

from fastapi.testclient import TestClient
from mcp.client.stdio import StdioServerParameters
import pytest

from studyflow.web import create_app


def test_web_summary_uses_real_stdio_mcp_without_changing_saved_coursework(tmp_path):
    from studyflow.github_mcp_client import get_repository_summary

    reader = partial(get_repository_summary, server_parameters=StdioServerParameters(
        command=sys.executable, args=[str(Path(__file__).parent / "fixtures/github_server.py")],
    ))
    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3", summary_reader=reader)) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        assignment = client.post(f"/api/courses/{course['id']}/assignments", json={
            "title": "Problem set", "repository": {"owner": "octocat", "repo": "hello-world"},
        }).json()
        url = f"/api/assignments/{assignment['id']}"
        task = client.post(url + "/tasks", json={"title": "Read chapter"}).json()
        client.patch(f"/api/tasks/{task['id']}", json={"is_completed": True})
        client.post(url + "/tasks", json={"title": "Write solution"})
        assignment = client.get(url).json()
        tasks = client.get(url + "/tasks").json()
        assert assignment["progress"] == {"completed": 1, "total": 2, "percent": 50}
        response = client.get(url + "/repository-summary")
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store"
        summary = response.json()
        assert summary == {
            "owner": "octocat", "name": "Hello-World", "url": "https://github.com/octocat/Hello-World",
            "description": "Coursework examples", "default_branch": "main", "primary_languages": ["Python"],
            "last_push_at": "2026-01-02T03:04:05Z", "fetched_at": summary["fetched_at"],
        }
        assert client.get(url).json() == assignment
        assert client.get(url + "/tasks").json() == tasks


def test_missing_repository_through_real_stdio_returns_recoverable_web_error(tmp_path):
    from studyflow.github_mcp_client import get_repository_summary

    reader = partial(get_repository_summary, server_parameters=StdioServerParameters(
        command=sys.executable, args=[str(Path(__file__).parent / "fixtures/github_server.py")],
    ))
    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3", summary_reader=reader), raise_server_exceptions=False) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        assignment = client.post(f"/api/courses/{course['id']}/assignments", json={
            "title": "Problem set", "repository": {"owner": "octocat", "repo": "missing"},
        }).json()
        url = f"/api/assignments/{assignment['id']}"
        response = client.get(url + "/repository-summary")
        assert response.status_code == 404
        assert response.json() == {"error": {"code": "REPOSITORY_NOT_FOUND", "message": "Repository not found or unavailable.", "fields": {}}}
        assert response.headers["Cache-Control"] == "no-store"
        assert client.get(url).json() == assignment
        assert client.patch(url, json={"title": "Still editable"}).status_code == 200


def test_summary_without_reference_returns_conflict_without_starting_integration(tmp_path):
    async def forbidden(owner, repo):
        raise AssertionError("Unlinked coursework must not start MCP.")

    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3", summary_reader=forbidden), raise_server_exceptions=False) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        assignment = client.post(f"/api/courses/{course['id']}/assignments", json={"title": "Problem set"}).json()
        response = client.get(f"/api/assignments/{assignment['id']}/repository-summary")
        assert response.status_code == 409
        assert response.json() == {"error": {"code": "REPOSITORY_NOT_LINKED", "message": "Link a repository before loading its summary.", "fields": {}}}
        assert response.headers["Cache-Control"] == "no-store"


def test_missing_assignment_summary_is_not_cached_and_does_not_start_integration(tmp_path):
    async def forbidden(owner, repo):
        raise AssertionError("Missing coursework must not start MCP.")

    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3", summary_reader=forbidden)) as client:
        response = client.get("/api/assignments/123/repository-summary")
        assert response.status_code == 404
        assert response.json() == {"error": {"code": "NOT_FOUND", "message": "Assignment not found.", "fields": {}}}
        assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("mode, status, code", [
    ("startup", 502, "INTEGRATION_UNAVAILABLE"), ("protocol", 502, "INTEGRATION_UNAVAILABLE"),
    ("malformed", 502, "INTEGRATION_UNAVAILABLE"), ("unsafe_url", 502, "INTEGRATION_UNAVAILABLE"),
    ("flag_mismatch", 502, "INTEGRATION_UNAVAILABLE"), ("text_error", 422, "INVALID_INPUT"),
    ("integer_ok", 502, "INTEGRATION_UNAVAILABLE"), ("duplicate_languages", 502, "INTEGRATION_UNAVAILABLE"),
    ("extra_summary_field", 502, "INTEGRATION_UNAVAILABLE"), ("mismatched_text", 502, "INTEGRATION_UNAVAILABLE"),
])
def test_mcp_startup_protocol_and_invalid_results_become_safe_web_errors(tmp_path, mode, status, code):
    from studyflow.github_mcp_client import get_repository_summary

    reader = partial(get_repository_summary, server_parameters=StdioServerParameters(
        command=sys.executable, args=[str(Path(__file__).parent / "fixtures/broken_mcp.py"), mode],
    ))
    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3", summary_reader=reader), raise_server_exceptions=False) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        assignment = client.post(f"/api/courses/{course['id']}/assignments", json={
            "title": "Problem set", "repository": {"owner": "octocat", "repo": "hello-world"},
        }).json()
        url = f"/api/assignments/{assignment['id']}"
        response = client.get(url + "/repository-summary")
        assert response.status_code == status
        assert response.json()["error"]["code"] == code
        assert response.json()["error"]["fields"] == {}
        assert "Do not expose" not in response.text
        assert response.headers["Cache-Control"] == "no-store"
        assert client.get(url).json() == assignment


@pytest.mark.parametrize("mode", ["startup_timeout", "call_timeout"])
def test_total_mcp_deadline_returns_timeout_and_reaps_child_process(tmp_path, mode):
    from studyflow.github_mcp_client import get_repository_summary

    pid_file = tmp_path / "child.pid"
    reader = partial(get_repository_summary, timeout_seconds=0.5, server_parameters=StdioServerParameters(
        command=sys.executable, args=[str(Path(__file__).parent / "fixtures/broken_mcp.py"), mode, str(pid_file)],
    ))
    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3", summary_reader=reader), raise_server_exceptions=False) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        assignment = client.post(f"/api/courses/{course['id']}/assignments", json={
            "title": "Problem set", "repository": {"owner": "octocat", "repo": "hello-world"},
        }).json()
        started = time.monotonic()
        response = client.get(f"/api/assignments/{assignment['id']}/repository-summary")
        assert response.status_code == 504
        assert response.json()["error"]["code"] == "INTEGRATION_TIMEOUT"
        assert time.monotonic() - started < 4
        with pytest.raises(ProcessLookupError):
            os.kill(int(pid_file.read_text()), 0)
        assert client.get(f"/api/assignments/{assignment['id']}").json() == assignment


@pytest.mark.parametrize("code, status", [
    ("INVALID_INPUT", 422), ("REPOSITORY_NOT_FOUND", 404), ("REPOSITORY_MOVED", 409), ("RATE_LIMITED", 503),
    ("GITHUB_AUTH_ERROR", 502), ("GITHUB_UNAVAILABLE", 502), ("INTERNAL_ERROR", 502),
])
def test_each_tool_error_maps_to_web_status_and_retry_header_and_reaps_process(tmp_path, code, status):
    from studyflow.github_mcp_client import get_repository_summary

    pid_file = tmp_path / "child.pid"
    reader = partial(get_repository_summary, server_parameters=StdioServerParameters(
        command=sys.executable, args=[str(Path(__file__).parent / "fixtures/broken_mcp.py"), "error:" + code, str(pid_file)],
    ))
    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3", summary_reader=reader)) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        assignment = client.post(f"/api/courses/{course['id']}/assignments", json={
            "title": "Problem set", "repository": {"owner": "octocat", "repo": "hello-world"},
        }).json()
        response = client.get(f"/api/assignments/{assignment['id']}/repository-summary")
        assert response.status_code == status
        assert response.json() == {"error": {"code": code, "message": "Safe fixture error.", "fields": {}}}
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers.get("Retry-After") == ("8" if code == "RATE_LIMITED" else None)
        with pytest.raises(ProcessLookupError):
            os.kill(int(pid_file.read_text()), 0)


def test_app_forwards_optional_token_to_stdio_server_without_returning_it(tmp_path, monkeypatch):
    from studyflow.github_mcp_client import get_repository_summary

    monkeypatch.setenv("GITHUB_TOKEN", "fixture-token")
    reader = partial(get_repository_summary, server_parameters=StdioServerParameters(
        command=sys.executable, args=[str(Path(__file__).parent / "fixtures/github_server.py"), "token"],
    ))
    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3", summary_reader=reader)) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        assignment = client.post(f"/api/courses/{course['id']}/assignments", json={
            "title": "Problem set", "repository": {"owner": "octocat", "repo": "hello-world"},
        }).json()
        response = client.get(f"/api/assignments/{assignment['id']}/repository-summary")
        assert response.status_code == 200
        assert "fixture-token" not in response.text
