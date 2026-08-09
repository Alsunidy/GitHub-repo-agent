"""GitHub tools for the Repo Health Agent.

Each function is independent and can be exercised without the LangGraph
graph — see scripts/try_github_tools.py.
"""
import base64
import os
import re

import requests

GITHUB_API = "https://api.github.com"
REQUEST_TIMEOUT = 10  # seconds, per call
USER_AGENT = "github-repo-health-agent"

MAX_OPEN_ISSUES = 30
MAX_CODE_FILES = 15
MAX_CODE_FILE_SIZE = 100_000  # bytes, skip anything larger to save requests/tokens

DEPENDENCY_FILENAMES = ["requirements.txt"]

# owner/repo, optionally with a leading "https://github.com/" or "github.com/",
# a trailing ".git", a trailing slash, or extra path segments (e.g. /tree/main).
_REPO_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/"
    r"(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)/"
    r"(?P<repo>[A-Za-z0-9._-]+?)"
    r"(?:\.git)?/?(?:[/?#].*)?$"
)


class RepoNotFound(Exception):
    """Raised when the repository does not exist or is private/inaccessible."""


class MissingToken(Exception):
    """Raised when GITHUB_TOKEN is required but not set."""


def _headers() -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def parse_repo_url(url: str) -> tuple[str, str] | None:
    """Return (owner, repo) if url is a valid GitHub repo URL, else None."""
    if not url or not isinstance(url, str):
        return None
    match = _REPO_URL_RE.match(url.strip())
    if not match:
        return None
    return match.group("owner"), match.group("repo")


def _get_meta(owner: str, repo: str) -> dict:
    resp = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}",
        headers=_headers(),
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code == 404:
        raise RepoNotFound(f"{owner}/{repo} not found or private")
    resp.raise_for_status()
    data = resp.json()
    return {
        "meta": {
            "full_name": data["full_name"],
            "description": data.get("description"),
            "stars": data.get("stargazers_count", 0),
            "pushed_at": data.get("pushed_at"),
            "language": data.get("language"),
        },
        "default_branch": data.get("default_branch", "main"),
    }


def _get_readme(owner: str, repo: str) -> str:
    resp = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/readme",
        headers=_headers(),
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code == 404:
        return ""
    resp.raise_for_status()
    content = resp.json().get("content", "")
    return base64.b64decode(content).decode("utf-8", errors="replace")


def _get_open_issues(owner: str, repo: str) -> list[dict]:
    resp = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/issues",
        headers=_headers(),
        params={
            "state": "open",
            "per_page": MAX_OPEN_ISSUES,
            "sort": "created",
            "direction": "desc",
        },
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    issues = []
    for item in resp.json():
        if "pull_request" in item:  # the issues endpoint also returns PRs
            continue
        issues.append(
            {
                "number": item["number"],
                "title": item["title"],
                "body": item.get("body") or "",
                "created_at": item["created_at"],
                "comments": item.get("comments", 0),
                "labels": [label["name"] for label in item.get("labels", [])],
            }
        )
    return issues


def _get_file_content(owner: str, repo: str, path: str) -> str | None:
    resp = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
        headers=_headers(),
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    data = resp.json()
    if data.get("encoding") != "base64":
        return None
    return base64.b64decode(data["content"]).decode("utf-8", errors="replace")


def _get_dependency_files(owner: str, repo: str) -> dict:
    files = {}
    for filename in DEPENDENCY_FILENAMES:
        content = _get_file_content(owner, repo, filename)
        if content is not None:
            files[filename] = content
    return files


def _get_code_files(owner: str, repo: str, default_branch: str) -> dict:
    resp = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/{default_branch}",
        headers=_headers(),
        params={"recursive": "1"},
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code != 200:
        return {}  # e.g. empty repo, no default branch tree yet

    tree = resp.json().get("tree", [])
    py_entries = [
        entry
        for entry in tree
        if entry.get("type") == "blob"
        and entry.get("path", "").endswith(".py")
        and entry.get("size", 0) <= MAX_CODE_FILE_SIZE
    ]
    # Root files are the most likely place to find exposed secrets, so
    # prioritize shallow paths (fewest "/" separators) before capping.
    py_entries.sort(key=lambda entry: entry["path"].count("/"))
    py_entries = py_entries[:MAX_CODE_FILES]

    code_files = {}
    for entry in py_entries:
        content = _get_file_content(owner, repo, entry["path"])
        if content is not None:
            code_files[entry["path"]] = content
    return code_files


def fetch_repo_data(owner: str, repo: str) -> dict:
    """Return a dict matching the repo_data shape in CONTRACTS.md.

    Raises RepoNotFound if the repository does not exist or is private.
    """
    meta_result = _get_meta(owner, repo)  # raises RepoNotFound if missing
    default_branch = meta_result["default_branch"]

    return {
        "meta": meta_result["meta"],
        "readme": _get_readme(owner, repo),
        "open_issues": _get_open_issues(owner, repo),
        "dependency_files": _get_dependency_files(owner, repo),
        "code_files": _get_code_files(owner, repo, default_branch),
    }


def open_issue(owner: str, repo: str, title: str, body: str) -> str:
    """Open a real issue on the repo and return its html_url.

    Raises MissingToken if GITHUB_TOKEN is not set.
    """
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise MissingToken("GITHUB_TOKEN environment variable is not set")

    resp = requests.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/issues",
        headers=_headers(),
        json={"title": title, "body": body},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["html_url"]
