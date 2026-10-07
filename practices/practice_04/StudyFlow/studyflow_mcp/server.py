import asyncio
import logging

from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server
from pydantic import ValidationError

from studyflow_mcp.github import GitHubError, fetch_summary
from studyflow_mcp.models import RepositoryInput, SUMMARY_RESULT, SummaryFailure, SummarySuccess, ToolError


def create_server(*, transport=None):
    output_schema = SUMMARY_RESULT.json_schema()
    output_schema["type"] = "object"
    tool = types.Tool(
        name="get_repository_summary", description="Read a public GitHub repository's metadata and top three languages.",
        inputSchema=RepositoryInput.model_json_schema(), outputSchema=output_schema,
        annotations=types.ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True),
    )

    async def list_tools(context, params):
        return types.ListToolsResult(tools=[tool])

    async def call_tool(context, params):
        try:
            reference = RepositoryInput.model_validate(params.arguments)
        except ValidationError:
            result = SummaryFailure(ok=False, summary=None, error=ToolError(
                code="INVALID_INPUT", message="Provide a valid GitHub owner and repository name.", retry_after_seconds=None,
            ))
        else:
            try:
                summary = await fetch_summary(reference.owner, reference.repo, transport=transport)
            except GitHubError as error:
                result = SummaryFailure(ok=False, summary=None, error=error.error)
            except Exception as error:
                logging.getLogger(__name__).error("Unexpected integration exception: %s", type(error).__name__)
                result = SummaryFailure(ok=False, summary=None, error=ToolError(
                    code="INTERNAL_ERROR", message="Repository information could not be loaded. Please try again.", retry_after_seconds=None,
                ))
            else:
                result = SummarySuccess(ok=True, summary=summary, error=None)
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=result.model_dump_json())],
            structuredContent=result.model_dump(), isError=not result.ok,
        )

    return Server("StudyFlow GitHub", version="0.1.0", on_list_tools=list_tools, on_call_tool=call_tool,
                  get_tool_input_schema=lambda name: tool.input_schema if name == tool.name else None)


async def main():
    server = create_server()
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
