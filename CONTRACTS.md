# Contracts -- GitHub Repo Health Agent

> This document is agreed **before** any code is written. Any later change to it
> means telling the other side immediately.
> The goal: each side builds its piece knowing exactly what the other's piece
> looks like, without waiting.

---

## Contract 1: the State

```python
# backend/state.py
import operator
from typing import Annotated, Optional, TypedDict


class AgentState(TypedDict):
    # --- inputs ---
    repo_url: str                 # the URL exactly as the user typed it
    language: str                 # "en" | "ar" -- language of the report and messages

    # --- filled by the guardrail ---
    owner: str                    # owner name parsed from the URL
    repo: str                     # repository name parsed from the URL
    rejection_reason: Optional[str]   # rejection text, or None when the request is fine

    # --- filled by the fetch tool (written once) ---
    repo_data: dict               # see "repo_data shape" below

    # --- decided by the supervisor on every round ---
    next_agent: str               # "security" | "issues" | "docs" | "done"

    # --- accumulated (Annotated + operator.add) ---
    agents_done: Annotated[list[str], operator.add]      # names of the agents that ran
    findings: Annotated[list[dict], operator.add]        # see "finding shape" below

    # --- final outputs ---
    report: str                   # Markdown report in the user's language
    issue_url: Optional[str]      # issue link once opened, or None

    # --- amendment 1 (track 1) -- additive, breaks no existing field ---
    issue_title: str              # proposed issue title -- written by the report node
    issue_body: str               # proposed issue body -- written by the report node
    approved: Optional[bool]      # None = not asked | True = approved | False = declined
    supervisor_log: Annotated[list[str], operator.add]   # decision trace (accumulates)
```

> **Amendment 1 -- four fields added.** Without `issue_title` and `issue_body`,
> `/approve` has no way to know what to open, and without `approved` the graph
> has no way to know the outcome of the approval. `supervisor_log` covers the
> brief's request to show tracing in the demo.
> No existing field changed. Details in `HANDOFF.md`.

### `repo_data` shape
```python
{
    "meta": {
        "full_name": str,          # "owner/repo"
        "description": str | None,
        "stars": int,
        "pushed_at": str,          # ISO date
        "language": str | None,
    },
    "readme": str,                 # README text ("" when absent)
    "open_issues": [               # the 30 most recent open issues
        {
            "number": int,
            "title": str,
            "body": str,
            "created_at": str,     # ISO date
            "comments": int,
            "labels": list[str],
        }
    ],
    "dependency_files": {          # filename -> contents (may be empty {})
        "requirements.txt": str,
    },
    "code_files": {                # code files, for the exposed-secret scan
        "path/to/file.py": str,
    },
}
```

### `finding` shape (every agent adds at least one)
```python
{
    "agent": str,        # "security" | "issues" | "docs"
    "severity": str,     # "critical" | "high" | "medium" | "low" | "none"
    "title": str,        # short title for the problem
    "detail": str,       # the explanation (text or Markdown)
    "evidence": list[str],   # GHSA/CVE ids, issue numbers, missing section names
}
```

---

## Contract 2: tool signatures

> Every function is **fully standalone** -- testable with a small script,
> without the graph.

```python
# backend/tools/github_tools.py

def parse_repo_url(url: str) -> tuple[str, str] | None:
    """Return (owner, repo) for a valid GitHub repository URL, else None."""


def fetch_repo_data(owner: str, repo: str) -> dict:
    """Return a dict in the repo_data shape above.
    Raises RepoNotFound when the repository is missing or private."""


def open_issue(owner: str, repo: str, title: str, body: str) -> str:
    """Open a real issue and return its link (html_url).
    Raises MissingToken when GITHUB_TOKEN is not set."""


class RepoNotFound(Exception): ...
class MissingToken(Exception): ...
```

```python
# backend/tools/osv_tools.py

def parse_requirements(text: str) -> list[tuple[str, str]]:
    """Extract (package, version) pairs from lines pinned with == only."""


def check_vulnerabilities(requirements_text: str, limit: int = 10) -> list[dict]:
    """Query OSV.dev for each package. Returns a list shaped like:
    {"package": str, "version": str, "vuln_ids": list[str], "total_count": int, "summary": str}
    where vuln_ids is capped at the first 5 ids (to keep what's passed to the
    agents small), total_count is the real total, and summary covers only the
    first vulnerability. On a failed query for a package:
    {"package": str, "version": str, "error": str}
    Never raises -- errors are recorded inside the results."""
```

```python
# backend/tools/secret_tools.py

def scan_secrets(code_files: dict[str, str]) -> list[dict]:
    """Scan file contents for known key patterns (ghp_, sk-, AKIA...).
    Returns: {"file": str, "line": int, "kind": str, "snippet": str}
    (the snippet is partially masked -- never the whole key)."""
```

---

## Contract 3: the API

> The UI talks to the server over HTTP only -- it never imports the graph.

### `POST /analyze`
```jsonc
// request
{ "repo_url": "https://github.com/owner/repo", "language": "en" }

// response -- success (the system is paused at human approval)
{
  "thread_id": "uuid-string",
  "status": "awaiting_approval",
  "report": "## Executive summary\n...",
  "agents_done": ["security", "issues", "docs"]
}

// response -- rejected (invalid URL / repository not found)
{
  "thread_id": "uuid-string",
  "status": "rejected",
  "report": "the polite rejection text",
  "agents_done": []
}
```

### `POST /approve`
```jsonc
// request
{ "thread_id": "uuid-string", "approved": true }

// response -- after approval
{ "status": "done", "issue_url": "https://github.com/owner/repo/issues/12" }

// response -- after declining
{ "status": "cancelled", "issue_url": null }
```

### `GET /health`
```jsonc
{ "status": "ok" }
```

---

## Rules for working in parallel

1. **Separate files:** neither side edits the same file. (The graph/backend to
   one side, the tools/UI to the other.)
2. **Temporary stubs:** whoever is waiting on the other's piece writes a simple
   fake with the same signature and carries on -- **and all of them are deleted
   before submission** (the brief forbids fake tools in the final build).
3. **Any change to this document means telling the other side immediately.**
   Silently changing the shape of a function's output is the number one cause of
   teams breaking each other's work.
4. **Only three meeting points:** (a) agreeing this document, (b) wiring the
   real tools into the graph, (c) pointing the UI at the real server.
