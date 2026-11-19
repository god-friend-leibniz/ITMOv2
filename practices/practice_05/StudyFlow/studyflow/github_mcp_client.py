import json
import os
import sys

import anyio
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from studyflow_mcp.models import SUMMARY_RESULT


class IntegrationError(Exception):
    def __init__(self, code, message, status_code, retry_after_seconds=None):
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code
        self.retry_after_seconds = retry_after_seconds


async def get_repository_summary(owner, repo, *, server_parameters=None, timeout_seconds=15):
    parameters = server_parameters or StdioServerParameters(command=sys.executable, args=["-m", "studyflow_mcp.server"])
    if token := os.environ.get("GITHUB_TOKEN"):
        parameters = parameters.model_copy(update={"env": {**(parameters.env or {}), "GITHUB_TOKEN": token}})
    try:
        with anyio.fail_after(timeout_seconds):
            async with Client(parameters) as client:
                result = await client.call_tool("get_repository_summary", {"owner": owner, "repo": repo})
    except TimeoutError:
        raise IntegrationError("INTEGRATION_TIMEOUT", "Repository integration timed out. Please try again.", 504) from None
    except Exception:
        raise IntegrationError("INTEGRATION_UNAVAILABLE", "Repository integration is unavailable. Please try again.", 502) from None
    if result.is_error and result.structured_content is None:
        raise IntegrationError("INVALID_INPUT", "Provide a valid GitHub owner and repository name.", 422)
    try:
        if not isinstance(result.structured_content, dict) or type(result.structured_content.get("ok")) is not bool:
            raise ValueError("Tool result must have a boolean discriminator.")
        if len(result.content) != 1 or result.content[0].type != "text" or json.loads(result.content[0].text) != result.structured_content:
            raise ValueError("Tool text must match its structured result.")
        payload = SUMMARY_RESULT.validate_python(result.structured_content)
        if result.is_error != (not payload.ok):
            raise ValueError("Inconsistent tool error flag.")
    except ValueError:
        raise IntegrationError("INTEGRATION_UNAVAILABLE", "Repository integration is unavailable. Please try again.", 502) from None
    if not payload.ok:
        statuses = {"INVALID_INPUT": 422, "REPOSITORY_NOT_FOUND": 404, "REPOSITORY_MOVED": 409, "RATE_LIMITED": 503}
        raise IntegrationError(payload.error.code, payload.error.message, statuses.get(payload.error.code, 502), payload.error.retry_after_seconds)
    return payload.summary.model_dump()
