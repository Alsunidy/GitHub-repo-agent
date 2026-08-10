"""Manual smoke test for issues_agent() — not part of the automated test
suite. Fetches real repo_data from sl-rwl/test_1, runs issues_agent, and
prints the resulting findings. Run from the repo root:

    python scripts/try_issues_agent.py
"""
import os
import sys
from datetime import datetime, timedelta, timezone

# Windows writes stdout in the system codepage (cp1252) when not attached to
# a real console — Arabic findings would come out as mojibake without
# forcing UTF-8 first. Same fix as scripts/smoke_graph.py.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()

from backend.graph.agents import issues_agent  # noqa: E402
from backend.state import initial_state  # noqa: E402
from backend.tools.github_tools import fetch_repo_data, parse_repo_url  # noqa: E402

REPO_URL = "https://github.com/sl-rwl/test_1"


def _run(label: str, repo_url: str, owner: str, repo: str, repo_data: dict):
    for language in ("en", "ar"):
        state = initial_state(repo_url, language)
        state["owner"], state["repo"] = owner, repo
        state["repo_data"] = repo_data

        result = issues_agent(state)

        print(f"\n{'=' * 72}\n{label} — language={language!r}")
        print(f"agents_done: {result['agents_done']}")
        print(f"findings: {len(result['findings'])}")
        for item in result["findings"]:
            print(f"  - [{item['severity']}] {item['title']}")
            print(f"    detail: {item['detail']}")
            print(f"    evidence: {item['evidence']}")


def _synthetic_open_issues() -> list[dict]:
    """sl-rwl/test_1 only has one real open issue — not enough to exercise
    duplicate detection or staleness. This fabricated set proves those two
    mechanisms actually work: a same-bug EN/AR pair, one issue old enough
    with zero comments to be flagged stale, and a mix of severities for
    priority ranking."""
    now = datetime.now(timezone.utc)

    def iso(days_ago: int) -> str:
        return (now - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")

    return [
        {
            "number": 101,
            "title": "App crashes on empty input",
            "body": "Sending an empty string to /submit crashes the server with a 500.",
            "created_at": iso(5),
            "comments": 2,
            "labels": ["bug"],
        },
        {
            "number": 102,
            "title": "يتعطل التطبيق عند إدخال فارغ",
            "body": "عند إرسال نص فارغ إلى /submit يتعطل الخادم برمز 500.",
            "created_at": iso(3),
            "comments": 0,
            "labels": [],
        },
        {
            "number": 103,
            "title": "Typo in docs",
            "body": "The word 'recieve' should be 'receive' in the README.",
            "created_at": iso(200),
            "comments": 0,
            "labels": ["docs"],
        },
        {
            "number": 104,
            "title": "Authentication can be bypassed with an empty token header",
            "body": "Sending a request with an empty Authorization header grants admin access.",
            "created_at": iso(4),
            "comments": 5,
            "labels": ["security"],
        },
        {
            "number": 105,
            "title": "Minor color contrast issue in dark mode",
            "body": "The submit button text is hard to read in dark mode.",
            "created_at": iso(2),
            "comments": 1,
            "labels": ["ui"],
        },
    ]


def main():
    owner, repo = parse_repo_url(REPO_URL)
    repo_data = fetch_repo_data(owner, repo)

    print(f"open_issues fetched: {len(repo_data['open_issues'])}")
    for issue in repo_data["open_issues"]:
        print(f"  #{issue['number']} {issue['title']!r} comments={issue['comments']} created_at={issue['created_at']}")

    _run("real sl-rwl/test_1 data", REPO_URL, owner, repo, repo_data)

    synthetic_data = dict(repo_data, open_issues=_synthetic_open_issues())
    _run("synthetic data (duplicates + stale + priority)", REPO_URL, owner, repo, synthetic_data)


if __name__ == "__main__":
    main()
