from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import math
import os
import time
from typing import Annotated

import httpx
from pydantic import Field, TypeAdapter

from studyflow_mcp.models import RepositorySummary, ToolError


LANGUAGES = TypeAdapter(dict[Annotated[str, Field(min_length=1)], Annotated[int, Field(ge=0)]])


class GitHubError(Exception):
    def __init__(self, code, message, retry_after_seconds=None):
        self.error = ToolError(code=code, message=message, retry_after_seconds=retry_after_seconds)
        super().__init__(message)


def github_json(response):
    status = response.status_code
    if 300 <= status < 400:
        raise GitHubError("REPOSITORY_MOVED", "Repository moved. Update the saved reference.")
    secondary_limit = False
    if status == 403:
        try:
            body = response.json()
            message = body.get("message", "") if isinstance(body, dict) else ""
            secondary_limit = isinstance(message, str) and "rate limit" in message.lower()
        except ValueError:
            pass
    if status == 429 or (status == 403 and (
        response.headers.get("X-RateLimit-Remaining") == "0" or "Retry-After" in response.headers or secondary_limit
    )):
        retry = None
        try:
            if "Retry-After" in response.headers:
                try:
                    retry = max(0, int(response.headers["Retry-After"]))
                except ValueError:
                    retry = max(0, math.ceil(parsedate_to_datetime(response.headers["Retry-After"]).timestamp() - time.time()))
            elif "X-RateLimit-Reset" in response.headers:
                retry = max(0, math.ceil(int(response.headers["X-RateLimit-Reset"]) - time.time()))
        except (TypeError, ValueError, OverflowError):
            pass
        raise GitHubError("RATE_LIMITED", "GitHub rate limit reached. Please retry later.", retry)
    if status in (401, 403):
        raise GitHubError("GITHUB_AUTH_ERROR", "GitHub authentication failed. Check the server token.")
    if response.status_code == 404:
        raise GitHubError("REPOSITORY_NOT_FOUND", "Repository not found or unavailable.")
    if status != 200:
        raise GitHubError("GITHUB_UNAVAILABLE", "GitHub is unavailable. Please try again.")
    return response.json()


async def fetch_summary(owner, repo, *, transport=None):
    url = f"https://api.github.com/repos/{owner}/{repo}"
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2026-03-10"}
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    try:
        async with httpx.AsyncClient(transport=transport, timeout=5, follow_redirects=False, headers=headers) as client:
            metadata = github_json(await client.get(url))
            if type(metadata["private"]) is not bool:
                raise ValueError("Invalid repository visibility.")
            if metadata["private"]:
                raise GitHubError("REPOSITORY_NOT_FOUND", "Repository not found or unavailable.")
            languages = LANGUAGES.validate_python(github_json(await client.get(url + "/languages")), strict=True)
        canonical_owner = metadata["owner"]["login"]
        name = metadata["name"]
        return RepositorySummary(
            owner=canonical_owner, name=name, url=f"https://github.com/{canonical_owner}/{name}",
            description=metadata["description"], default_branch=metadata["default_branch"],
            primary_languages=sorted(languages, key=lambda language: (-languages[language], language))[:3],
            last_push_at=metadata["pushed_at"], fetched_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        raise GitHubError("GITHUB_UNAVAILABLE", "GitHub is unavailable. Please try again.") from None
