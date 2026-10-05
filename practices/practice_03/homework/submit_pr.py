"""Inspect GitHub access or create the requested PR using existing credentials.

Credentials stay in memory and are never written or printed.
"""
import argparse
import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPOSITORY = "god-friend-leibniz/ITMOv2"


def token():
    value = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if value:
        return value
    result = subprocess.run(["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n", text=True, capture_output=True,
        env=dict(os.environ, GIT_TERMINAL_PROMPT="0"), timeout=20)
    if result.returncode:
        return None
    values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    return values.get("password")


def request(path, credential, data=None):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "ITMO-Practice-3",
               "X-GitHub-Api-Version": "2022-11-28"}
    if credential:
        headers["Authorization"] = "Bearer " + credential
    req = urllib.request.Request("https://api.github.com" + path,
        headers=headers, data=None if data is None else json.dumps(data).encode())
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("inspect", "create"))
    parser.add_argument("--body-file", type=Path)
    parser.add_argument("--base", default="main")
    parser.add_argument("--head", default="practice_03")
    args = parser.parse_args()
    credential = token()
    if args.action == "inspect":
        repo = request("/repos/" + REPOSITORY, credential)
        branches = request("/repos/" + REPOSITORY + "/branches", credential)
        pulls = request("/repos/" + REPOSITORY + "/pulls?state=open", credential)
        print(json.dumps({"credential_available": bool(credential),
            "default_branch": repo["default_branch"],
            "branches": [{"name": item["name"], "sha": item["commit"]["sha"]} for item in branches],
            "open_pulls": [{"number": item["number"], "url": item["html_url"],
                "head": item["head"]["ref"], "base": item["base"]["ref"]} for item in pulls]}, indent=2))
        if credential:
            user = request("/user", credential)
            print("Authenticated as:", user["login"])
        return
    if not credential:
        raise SystemExit("No existing GitHub API credential; PR cannot be created automatically")
    query = urllib.parse.urlencode({"state": "open", "head": "god-friend-leibniz:" + args.head})
    existing = request("/repos/" + REPOSITORY + "/pulls?" + query, credential)
    if existing:
        if existing[0]["base"]["ref"] != args.base:
            raise SystemExit("Existing PR targets a different base; review its base before submission")
        print("Existing PR:", existing[0]["html_url"])
        return
    if not args.body_file:
        parser.error("--body-file is required for create")
    pr = request("/repos/" + REPOSITORY + "/pulls", credential, {
        "title": "Practice 3: local Qwen evaluation and homework A/B",
        "head": args.head, "base": args.base,
        "body": args.body_file.read_text(), "draft": True})
    print("Created draft PR:", pr["html_url"])


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"GitHub API returned HTTP {exc.code}")
