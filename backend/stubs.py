"""Temporary fakes of the track 2 pieces -- a development aid only.

╔══════════════════════════════════════════════════════════════════════╗
║  DELETE THIS ENTIRE FILE at the first integration point.             ║
║  The brief forbids any tool that returns canned data in the final    ║
║  build: "No tool may be a stub that returns canned data."            ║
║  Deletion list: this file, plus the try/except ImportError blocks in ║
║  graph/guardrail.py, graph/fetch.py and graph/build.py.              ║
╚══════════════════════════════════════════════════════════════════════╝

Every function here matches its signature in CONTRACTS.md exactly, so the real
code drops in with no change to the graph.
"""

import re

# ---------------------------------------------------------------- github_tools


class RepoNotFound(Exception):
    """The repository does not exist, or is private."""


class MissingToken(Exception):
    """GITHUB_TOKEN is not set."""


_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)


def parse_repo_url(url: str) -> tuple[str, str] | None:
    """Return (owner, repo) for a valid GitHub repository URL, else None."""
    match = _URL_RE.match((url or "").strip())
    return (match.group(1), match.group(2)) if match else None


def fetch_repo_data(owner: str, repo: str) -> dict:
    """Fake data. The repo name picks the scenario, for testing supervisor decisions."""
    if repo == "does-not-exist":
        raise RepoNotFound(f"{owner}/{repo} does not exist or is private")

    if repo == "bare":  # no dependencies, no code, no issues
        return {
            "meta": {
                "full_name": f"{owner}/{repo}",
                "description": None,
                "stars": 3,
                "pushed_at": "2026-08-01T10:00:00Z",
                "language": None,
            },
            "readme": "",
            "open_issues": [],
            "dependency_files": {},
            "code_files": {},
        }

    return {
        "meta": {
            "full_name": f"{owner}/{repo}",
            "description": "A sample project",
            "stars": 128,
            "pushed_at": "2026-07-30T09:15:00Z",
            "language": "Python",
        },
        "readme": "# Sample\n\nA project.\n\n## Install\n\npip install -e .\n",
        "open_issues": [
            {
                "number": 12,
                "title": "Crash on empty input",
                "body": "It crashes when the input is empty.",
                "created_at": "2026-02-11T08:00:00Z",
                "comments": 4,
                "labels": ["bug"],
            },
            {
                "number": 19,
                "title": "يتعطل عند الإدخال الفارغ",
                "body": "نفس المشكلة أعلاه بالعربية.",   # the same bug filed in Arabic
                "created_at": "2026-05-03T08:00:00Z",
                "comments": 0,
                "labels": [],
            },
        ],
        "dependency_files": {"requirements.txt": "requests==2.19.0\nflask==0.12.2\n"},
        "code_files": {"app/config.py": 'TOKEN = "ghp_EXAMPLEEXAMPLEEXAMPLE"\n'},
    }


def open_issue(owner: str, repo: str, title: str, body: str) -> str:
    """Opens nothing -- returns a fake link."""
    return f"https://github.com/{owner}/{repo}/issues/999"


# ------------------------------------------------------------- track 2 nodes


def _finding(agent: str, severity: str, title: str, detail: str, evidence: list[str]) -> dict:
    return {
        "agent": agent,
        "severity": severity,
        "title": title,
        "detail": detail,
        "evidence": evidence,
    }


def security_agent(state: dict) -> dict:
    return {
        "findings": [
            _finding(
                "security",
                "critical",
                "Exposed GitHub token in app/config.py",
                "A hard-coded personal access token was found in the repository.",
                ["app/config.py:1"],
            )
        ],
        "agents_done": ["security"],
    }


def issues_agent(state: dict) -> dict:
    return {
        "findings": [
            _finding(
                "issues",
                "medium",
                "Duplicate issues across languages",
                "Issues #12 and #19 describe the same bug in English and Arabic.",
                ["#12", "#19"],
            )
        ],
        "agents_done": ["issues"],
    }


def docs_agent(state: dict) -> dict:
    return {
        "findings": [
            _finding(
                "docs",
                "low",
                "README missing usage and license sections",
                "The README covers the project and installation only.",
                ["usage", "license"],
            )
        ],
        "agents_done": ["docs"],
    }


def report_node(state: dict) -> dict:
    lines = ["## Executive summary", ""]
    for item in state.get("findings", []):
        lines.append(f"- **[{item['severity']}]** {item['title']} — {item['detail']}")
    report = "\n".join(lines)
    return {
        "report": report,
        "issue_title": "Repo health report",
        "issue_body": report,
    }
