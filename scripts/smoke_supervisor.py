"""Check the supervisor's logic alone -- eligibility, and correction of bad LLM answers.

    python scripts/smoke_supervisor.py

Needs no LLM key: we inject fake decisions in place of _ask_llm to verify that
the code never lets a model output route unchecked.
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.graph import supervisor as sup  # noqa: E402
from backend.state import initial_state  # noqa: E402

RICH = {
    "meta": {"full_name": "o/r", "language": "Python", "stars": 5, "pushed_at": "2026-07-01"},
    "readme": "# R\n## Install\n",
    "open_issues": [{"title": "bug"}],
    "dependency_files": {"requirements.txt": "flask==0.12.2"},
    "code_files": {"a.py": "x = 1"},
}
NO_DEPS_NO_CODE = {**RICH, "dependency_files": {}, "code_files": {}}
NO_ISSUES = {**RICH, "open_issues": []}


def _state(repo_data: dict, done: list[str], log: list[str] | None = None) -> dict:
    state = initial_state("https://github.com/o/r", "en")
    state["repo_data"] = repo_data
    state["agents_done"] = done
    state["supervisor_log"] = log or []
    return state


def _run(repo_data, done, fake=None, log=None) -> str:
    """Run the supervisor with a fake LLM decision (or with no LLM when fake is None)."""
    original = sup._ask_llm
    sup._ask_llm = fake or original
    try:
        return sup.supervisor_node(_state(repo_data, done, log))["next_agent"]
    finally:
        sup._ask_llm = original


CASES = [
    # (description, expected, actual)
    (
        "eligibility: no dependencies and no code => security not eligible",
        ["issues", "docs"],
        sup._eligible_agents(sup._signals(NO_DEPS_NO_CODE), []),
    ),
    (
        "eligibility: no open issues => issues agent not eligible",
        ["security", "docs"],
        sup._eligible_agents(sup._signals(NO_ISSUES), []),
    ),
    (
        "eligibility: an agent that already ran is never offered again",
        ["docs"],
        sup._eligible_agents(sup._signals(RICH), ["security", "issues"]),
    ),
    (
        "no LLM => deterministic fallback, most severe first",
        "security",
        _run(RICH, []),
    ),
    (
        "a valid LLM choice is honoured",
        "docs",
        _run(RICH, [], fake=lambda *a: ("docs", "readme is empty")),
    ),
    (
        "LLM picks an agent that already ran => corrected",
        "issues",
        _run(RICH, ["security"], fake=lambda *a: ("security", "loop me")),
    ),
    (
        "LLM picks an ineligible agent => corrected",
        "issues",
        _run(NO_DEPS_NO_CODE, [], fake=lambda *a: ("security", "nothing to scan")),
    ),
    (
        "LLM stops before any agent ran => refused, empty reports are not allowed",
        "security",
        _run(RICH, [], fake=lambda *a: ("done", "looks fine")),
    ),
    (
        "LLM stops after an agent ran => honoured",
        "done",
        _run(RICH, ["security"], fake=lambda *a: ("done", "enough for this repo")),
    ),
    (
        "all agents finished => done",
        "done",
        _run(RICH, ["security", "issues", "docs"]),
    ),
    (
        "safety belt: too many rounds => forced stop",
        "done",
        _run(RICH, [], log=["supervisor: x"] * sup._MAX_ROUNDS),
    ),
]


def main() -> int:
    failed = 0
    for label, expected, actual in CASES:
        ok = expected == actual
        failed += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
        if not ok:
            print(f"      expected: {expected!r}\n      actual  : {actual!r}")

    print(f"\n{len(CASES) - failed}/{len(CASES)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
