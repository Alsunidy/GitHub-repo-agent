"""Exercise the running backend over HTTP -- the end-to-end counterpart to
`pytest tests/`, which mocks the network away.

Start the backend first, then:

    uvicorn backend.api:app --port 8000
    python scripts/check_api.py [https://github.com/owner/repo]

Nothing here writes to GitHub: the approval step always declines, which is
itself the point being proved -- the graph pauses, and no issue is opened
until a human says yes. To watch the yes path, use the UI or
`python scripts/smoke_graph.py <url> --approve` against a repo you own.
"""

import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv()

BACKEND = os.getenv("FAHES_BACKEND", "http://localhost:8000")
DEFAULT_REPO = "https://github.com/sl-rwl/test_1"

_checks: list[tuple[str, bool]] = []


def check(label: str, passed: bool) -> None:
    _checks.append((label, passed))
    print(f"   {'PASS' if passed else 'FAIL'}  {label}")


def section(title: str) -> None:
    print(f"\n{'=' * 72}\n> {title}\n{'-' * 72}")


def main() -> int:
    repo_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_REPO
    print(f"backend : {BACKEND}\nrepo    : {repo_url}")

    section("GET /health")
    health = requests.get(f"{BACKEND}/health", timeout=10)
    print(f"   {health.status_code} {health.json()}")
    check("health returns ok", health.json().get("status") == "ok")

    section("POST /analyze -- refused: the URL is not a repository")
    refused = requests.post(
        f"{BACKEND}/analyze",
        json={"repo_url": "https://github.com/settings/profile", "language": "ar"},
        timeout=60,
    ).json()
    print(f"   status      : {refused['status']}")
    print(f"   agents_done : {refused['agents_done']}")
    print(f"   report      : {refused['report'][:100]}")
    check("a non-repository URL is refused", refused["status"] == "rejected")
    check("no agent ran on a refused request", refused["agents_done"] == [])

    section("POST /approve -- a refused thread has nothing to approve")
    conflict = requests.post(
        f"{BACKEND}/approve",
        json={"thread_id": refused["thread_id"], "approved": True},
        timeout=30,
    )
    print(f"   {conflict.status_code} {conflict.json()}")
    check("approving a refused thread is a 409", conflict.status_code == 409)

    unknown = requests.post(
        f"{BACKEND}/approve",
        json={"thread_id": "no-such-thread", "approved": True},
        timeout=30,
    )
    print(f"   {unknown.status_code} {unknown.json()}")
    check("an unknown thread_id is a 404", unknown.status_code == 404)

    section(f"POST /analyze -- full review of {repo_url}")
    analysis = requests.post(
        f"{BACKEND}/analyze",
        json={"repo_url": repo_url, "language": "en"},
        timeout=600,
    ).json()
    print(f"   status      : {analysis['status']}")
    print(f"   agents_done : {analysis['agents_done']}")
    print(f"   thread_id   : {analysis['thread_id']}")
    print(f"\n{analysis['report']}")
    check("the run pauses for approval", analysis["status"] == "awaiting_approval")
    check("at least one agent ran", len(analysis["agents_done"]) >= 1)
    check("a report came back", len(analysis["report"]) > 200)

    section("POST /approve -- declined: nothing is written")
    declined = requests.post(
        f"{BACKEND}/approve",
        json={"thread_id": analysis["thread_id"], "approved": False},
        timeout=120,
    ).json()
    print(f"   {declined}")
    check("declining cancels", declined["status"] == "cancelled")
    check("declining opens no issue", declined["issue_url"] is None)

    print(f"\n{'=' * 72}\nSummary")
    for label, passed in _checks:
        print(f"  {'PASS' if passed else 'FAIL'}  {label}")
    failed = [label for label, passed in _checks if not passed]
    print(f"\n{len(_checks) - len(failed)}/{len(_checks)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
