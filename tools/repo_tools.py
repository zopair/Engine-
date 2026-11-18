"""Scoped GitHub REST helpers for Issues, branches and encrypted state commits."""
from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request


class GitHubToolError(RuntimeError):
    pass


class GitHubRepoTools:
    def __init__(self, repository: str, token: str, api_url: str = "https://api.github.com", opener=None):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("repository must be owner/name")
        if not token:
            raise ValueError("GitHub token is required")
        self.repository, self.token = repository, token
        self.api_url, self.opener = api_url.rstrip("/"), opener or urllib.request.urlopen

    def request(self, method: str, path: str, payload=None):
        if not path.startswith("/repos/" + self.repository + "/"):
            raise ValueError("GitHub API path is outside the configured repository")
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(self.api_url + path, data=data, method=method,
            headers={"Accept": "application/vnd.github+json", "Authorization": "Bearer " + self.token,
                     "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json",
                     "User-Agent": "ENGINE-repo-tools/1.0"})
        try:
            with self.opener(request, timeout=20) as response:
                raw = response.read(1_000_001)
                return json.loads(raw.decode("utf-8")) if raw else {}
        except (OSError, ValueError, urllib.error.URLError) as exc:
            status = getattr(exc, "code", "network")
            raise GitHubToolError(f"GitHub API request failed ({status})") from exc

    def get_issue(self, number: int):
        return self.request("GET", f"/repos/{self.repository}/issues/{int(number)}")

    def comment_issue(self, number: int, body: str):
        if not body.strip():
            raise ValueError("comment body must not be empty")
        return self.request("POST", f"/repos/{self.repository}/issues/{int(number)}/comments",
                            {"body": body[:60000]})

    def close_issue(self, number: int):
        return self.request("PATCH", f"/repos/{self.repository}/issues/{int(number)}", {"state": "closed"})

    def create_branch(self, name: str, base: str = "main"):
        if not re.fullmatch(r"[A-Za-z0-9._/-]{1,200}", name) or ".." in name:
            raise ValueError("invalid branch name")
        ref = self.request("GET", f"/repos/{self.repository}/git/ref/heads/{urllib.parse.quote(base, safe='')}")
        return self.request("POST", f"/repos/{self.repository}/git/refs",
                            {"ref": "refs/heads/" + name, "sha": ref["object"]["sha"]})

    def upload_memory(self, path: str, content: bytes, message: str, branch: str = "engine-state"):
        if path.startswith("/") or ".." in path.split("/") or not path:
            raise ValueError("invalid repository path")
        endpoint = f"/repos/{self.repository}/contents/{urllib.parse.quote(path, safe='/')}"
        existing = None
        try:
            existing = self.request("GET", endpoint + "?ref=" + urllib.parse.quote(branch, safe=""))
        except GitHubToolError as exc:
            if "(404)" not in str(exc):
                raise
        payload = {"message": message, "content": base64.b64encode(content).decode("ascii"), "branch": branch}
        if existing:
            payload["sha"] = existing["sha"]
        return self.request("PUT", endpoint, payload)
