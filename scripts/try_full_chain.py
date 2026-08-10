"""Manual smoke test for the full analysis chain — not part of the
automated test suite. Runs security_agent -> issues_agent -> docs_agent ->
report_node directly (no graph/supervisor involved) against two real repos
in both languages: sl-rwl/test_1 (expected unhealthy) and sl-rwl/test_clean
(expected healthy). Run from the repo root:

    python scripts/try_full_chain.py
"""
import os
import sys

# Windows writes stdout in the system codepage (cp1252) when not attached to
# a real console — Arabic findings would come out as mojibake without
# forcing UTF-8 first. Same fix as scripts/smoke_graph.py.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()

from backend.graph.agents import docs_agent, issues_agent, security_agent  # noqa: E402
from backend.graph.report import report_node  # noqa: E402
from backend.state import initial_state  # noqa: E402
from backend.tools.github_tools import fetch_repo_data, parse_repo_url  # noqa: E402

REPOS = [
    ("sl-rwl/test_1 (expected: unhealthy)", "https://github.com/sl-rwl/test_1"),
    ("sl-rwl/test_clean (expected: healthy)", "https://github.com/sl-rwl/test_clean"),
]


def _accumulate(state: dict, result: dict) -> None:
    """Mimics the graph's Annotated[..., operator.add] accumulation for the
    two fields agents actually return."""
    state["findings"] = state["findings"] + result.get("findings", [])
    state["agents_done"] = state["agents_done"] + result.get("agents_done", [])


def main():
    for label, repo_url in REPOS:
        owner, repo = parse_repo_url(repo_url)
        repo_data = fetch_repo_data(owner, repo)

        for language in ("en", "ar"):
            state = initial_state(repo_url, language)
            state["owner"], state["repo"] = owner, repo
            state["repo_data"] = repo_data

            _accumulate(state, security_agent(state))
            _accumulate(state, issues_agent(state))
            _accumulate(state, docs_agent(state))

            result = report_node(state)

            print(f"\n{'#' * 72}\n{label} — language={language!r}")
            print(f"agents_done: {state['agents_done']}")
            print(f"total findings: {len(state['findings'])}")
            print(f"\nissue_title: {result['issue_title']}")
            print(f"\n--- report / issue_body ---\n{result['report']}")


if __name__ == "__main__":
    main()
