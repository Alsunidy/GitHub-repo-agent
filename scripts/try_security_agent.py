"""Manual smoke test for security_agent() — not part of the automated test
suite. Fetches real repo_data from sl-rwl/test_1, runs security_agent, and
prints the resulting findings. Run from the repo root:

    python scripts/try_security_agent.py
"""
import os
import sys

# Windows writes stdout in the system codepage (cp1252) when not attached to
# a real console (e.g. piped to a file) — Arabic findings would come out as
# mojibake without forcing UTF-8 first. Same fix as scripts/smoke_graph.py.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()

from backend.graph.agents import security_agent  # noqa: E402
from backend.state import initial_state  # noqa: E402
from backend.tools.github_tools import fetch_repo_data, parse_repo_url  # noqa: E402

REPO_URL = "https://github.com/sl-rwl/test_1"


def main():
    owner, repo = parse_repo_url(REPO_URL)
    repo_data = fetch_repo_data(owner, repo)

    for language in ("en", "ar"):
        state = initial_state(REPO_URL, language)
        state["owner"], state["repo"] = owner, repo
        state["repo_data"] = repo_data

        result = security_agent(state)

        print(f"\n{'=' * 72}\nlanguage={language!r}")
        print(f"agents_done: {result['agents_done']}")
        print(f"findings: {len(result['findings'])}")
        for item in result["findings"]:
            print(f"  - [{item['severity']}] {item['title']}")
            print(f"    detail: {item['detail']}")
            print(f"    evidence: {item['evidence']}")


if __name__ == "__main__":
    main()
