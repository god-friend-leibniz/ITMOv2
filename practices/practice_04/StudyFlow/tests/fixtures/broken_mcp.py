"""Untrusted MCP responses for testing the application's integration boundary."""
import asyncio
import os
from pathlib import Path
import sys
import time

mode = sys.argv[1]
if len(sys.argv) > 2:
    Path(sys.argv[2]).write_text(str(os.getpid()))
if mode == "startup":
    raise SystemExit(1)
if mode == "startup_timeout":
    time.sleep(30)

from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server


async def listing(context, params):
    return types.ListToolsResult(tools=[types.Tool(name="get_repository_summary", inputSchema={"type": "object"})])


async def call(context, params):
    if mode == "call_timeout":
        await asyncio.sleep(30)
    if mode == "protocol":
        raise RuntimeError("Do not expose protocol details")
    summary = {
        "owner": "octocat", "name": "Hello-World", "url": "https://github.com/octocat/Hello-World",
        "description": None, "default_branch": None, "primary_languages": [],
        "last_push_at": None, "fetched_at": "2026-01-02T03:04:05Z",
    }
    payload = {"ok": True, "summary": summary, "error": None}
    if mode == "malformed":
        payload = {"ok": True}
    if mode == "unsafe_url":
        summary["url"] = "javascript:alert(1)"
    if mode == "text_error":
        payload = None
    if mode == "integer_ok":
        payload["ok"] = 1
    if mode == "duplicate_languages":
        summary["primary_languages"] = ["Python", "Python"]
    if mode == "extra_summary_field":
        summary["token"] = "Do not expose raw MCP details"
    if mode.startswith("error:"):
        code = mode.split(":", 1)[1]
        payload = {"ok": False, "summary": None, "error": {"code": code, "message": "Safe fixture error.", "retry_after_seconds": 8 if code == "RATE_LIMITED" else None}}
    import json
    text = json.dumps(payload) if mode != "mismatched_text" else "Do not expose raw MCP details"
    return types.CallToolResult(content=[types.TextContent(type="text", text=text)],
                                structuredContent=payload, isError=mode in ("flag_mismatch", "text_error") or mode.startswith("error:"))


async def main():
    server = Server("Broken fixture", on_list_tools=listing, on_call_tool=call,
                    get_tool_input_schema=lambda name: {"type": "object"})
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


asyncio.run(main())
