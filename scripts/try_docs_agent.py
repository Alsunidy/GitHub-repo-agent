"""Manual smoke test for docs_agent() — not part of the automated test
suite. Runs it against two real repos: sl-rwl/test_1 (12-char README,
incomplete) and sl-rwl/test_clean (full README, should come back complete).
Run from the repo root:

    python scripts/try_docs_agent.py
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

from backend.graph.agents import docs_agent  # noqa: E402
from backend.state import initial_state  # noqa: E402
from backend.tools.github_tools import fetch_repo_data, parse_repo_url  # noqa: E402

REPOS = [
    ("incomplete README", "https://github.com/sl-rwl/test_1"),
    ("complete README", "https://github.com/sl-rwl/test_clean"),
]


def main():
    for label, repo_url in REPOS:
        owner, repo = parse_repo_url(repo_url)
        repo_data = fetch_repo_data(owner, repo)
        print(f"\n{'#' * 72}\n{label} — {owner}/{repo} — readme: {len(repo_data['readme'])} chars")

        for language in ("en", "ar"):
            state = initial_state(repo_url, language)
            state["owner"], state["repo"] = owner, repo
            state["repo_data"] = repo_data

            result = docs_agent(state)

            print(f"\n{'=' * 72}\nlanguage={language!r}")
            print(f"agents_done: {result['agents_done']}")
            print(f"findings: {len(result['findings'])}")
            for item in result["findings"]:
                print(f"  - [{item['severity']}] {item['title']}")
                print(f"    detail: {item['detail']}")
                print(f"    evidence: {item['evidence']}")


if __name__ == "__main__":
    main()
