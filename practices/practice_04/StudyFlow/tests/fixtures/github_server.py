"""Test-only stdio server with GitHub's HTTP boundary replaced by fixed responses."""
import asyncio
from pathlib import Path
import sys

import httpx
from mcp.server.stdio import stdio_server

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from studyflow_mcp.server import create_server


def github(request):
    assert request.url.host == "api.github.com"
    if sys.argv[1:] == ["token"] and request.headers.get("Authorization") != "Bearer fixture-token":
        return httpx.Response(401, json={"message": "Token not forwarded"})
    if "/missing" in request.url.path:
        return httpx.Response(404, json={"message": "Not Found"})
    if request.url.path.endswith("/languages"):
        return httpx.Response(200, json={"Python": 100})
    return httpx.Response(200, json={
        "owner": {"login": "octocat"}, "name": "Hello-World", "private": False,
        "description": "Coursework examples", "default_branch": "main", "pushed_at": "2026-01-02T03:04:05Z",
    })


async def main():
    server = create_server(transport=httpx.MockTransport(github))
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
