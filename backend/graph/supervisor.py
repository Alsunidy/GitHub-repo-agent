"""Supervisor node -- the decision brain: which agent runs next, or are we done?

Why an agent instead of a fixed sequence (the question the brief asks outright):
repositories are not alike. One with no dependency file and no source files has
nothing for a security agent to do; one with no open issues has nothing for an
issues agent; a 4000-character README is a different problem from no README at
all. Always running all three burns time and tokens on empty checks and produces
a report padded with "no findings".

The split of responsibility here is deliberate:
  * Code computes *who can* work (eligibility) -- a safety guarantee, never wrong.
  * The LLM decides *who should* work now, and when to stop -- judgement, not arithmetic.
  * When the LLM is unavailable the decision falls back to a deterministic order,
    so the system keeps running.
"""

from typing import Literal

from pydantic import BaseModel, Field

from backend.llm import get_llm
from backend.state import AgentState

AGENTS = ("security", "issues", "docs")

# Deterministic fallback order when there is no LLM: most severe first.
_FALLBACK_ORDER = ("security", "issues", "docs")

# Safety belt: the most supervisor rounds allowed before forcing an end.
_MAX_ROUNDS = len(AGENTS) + 2

_SYSTEM = """You are the supervisor of a GitHub repository health review.

Three specialist agents are available:
  • security — scans dependency files for known vulnerabilities (OSV.dev) and \
scans source files for exposed secrets.
  • issues   — reviews open issues for duplicates (including across Arabic and \
English), stale items, and priority.
  • docs     — grades the README against four criteria: what the project is, \
installation, usage, licence.

You are given the repository's signals and the agents that have already run.
Choose the single most valuable agent to run NEXT, or "done" to stop.

Rules:
  • Choose only from the eligible agents listed. Never choose one that already ran.
  • Prefer the agent whose signals suggest the most severe or most actionable \
finding for this specific repository.
  • Choose "done" when the remaining eligible agents would add little value \
for this repository — not merely because some agents have run.
Answer with the agent name and one short sentence of reasoning."""


class SupervisorDecision(BaseModel):
    """The supervisor's decision for a single round."""

    next_agent: Literal["security", "issues", "docs", "done"] = Field(
        description="The agent to run next, or 'done' to stop."
    )
    reason: str = Field(description="One short sentence explaining the choice.")


def supervisor_node(state: AgentState) -> dict:
    """Read the repository state and the agents already run, then decide."""
    done = list(state.get("agents_done", []))
    rounds = sum(1 for line in state.get("supervisor_log", []) if line.startswith("supervisor:"))

    if rounds >= _MAX_ROUNDS:
        return _decide("done", f"safety stop after {rounds} rounds")

    signals = _signals(state.get("repo_data", {}))
    eligible = _eligible_agents(signals, done)

    if not eligible:
        return _decide("done", "no eligible agent left")

    try:
        choice, reason = _ask_llm(state, signals, eligible, done)
        source = "llm"
    except Exception as exc:  # noqa: BLE001 -- missing key, network, invalid response
        choice = _first_eligible(eligible)
        reason = f"LLM unavailable ({type(exc).__name__}), deterministic order"
        source = "fallback"

    # Validate the model's answer -- a model output never routes unchecked.
    if choice not in eligible and choice != "done":
        choice = _first_eligible(eligible)
        reason = f"invalid choice corrected → {choice}"
        source = "corrected"

    # An empty report is not allowed: if nothing has run yet, something must.
    if choice == "done" and not done:
        choice = _first_eligible(eligible)
        reason = f"refused to stop before any agent ran → {choice}"
        source = "corrected"

    return _decide(choice, reason, source)


def _first_eligible(eligible: list[str]) -> str:
    """First eligible agent by severity order. Only called with a non-empty list."""
    return next(a for a in _FALLBACK_ORDER if a in eligible)


def _decide(choice: str, reason: str, source: str = "rule") -> dict:
    return {
        "next_agent": choice,
        "supervisor_log": [f"supervisor: [{source}] {choice} — {reason}"],
    }


def _signals(repo_data: dict) -> dict:
    """A compact summary to decide on -- we do not send the whole repo to the model."""
    meta = repo_data.get("meta", {}) or {}
    readme = repo_data.get("readme", "") or ""
    issues = repo_data.get("open_issues", []) or []
    deps = repo_data.get("dependency_files", {}) or {}
    code = repo_data.get("code_files", {}) or {}
    return {
        "full_name": meta.get("full_name", ""),
        "language": meta.get("language"),
        "stars": meta.get("stars", 0),
        "pushed_at": meta.get("pushed_at", ""),
        "readme_chars": len(readme),
        "readme_headings": [
            line.strip("# ").strip()
            for line in readme.splitlines()
            if line.strip().startswith("#")
        ][:12],
        "open_issue_count": len(issues),
        "issue_titles": [i.get("title", "") for i in issues][:10],
        "dependency_files": list(deps),
        "code_file_count": len(code),
    }


def _eligible_agents(signals: dict, done: list[str]) -> list[str]:
    """Who has real material to work on? Computed, never guessed."""
    eligible = []
    if "security" not in done and (signals["dependency_files"] or signals["code_file_count"]):
        eligible.append("security")
    if "issues" not in done and signals["open_issue_count"] > 0:
        eligible.append("issues")
    if "docs" not in done:
        eligible.append("docs")  # a missing README is itself a finding, so always eligible
    return eligible


def _ask_llm(state: AgentState, signals: dict, eligible: list[str], done: list[str]):
    """Ask the model, return (choice, reason). Raises on any fault; the caller handles it."""
    llm = get_llm(temperature=0).with_structured_output(SupervisorDecision)
    prompt = (
        f"Repository signals:\n"
        f"  full_name: {signals['full_name']}\n"
        f"  primary language: {signals['language']}\n"
        f"  stars: {signals['stars']}, last push: {signals['pushed_at']}\n"
        f"  README: {signals['readme_chars']} chars, "
        f"headings={signals['readme_headings']}\n"
        f"  open issues: {signals['open_issue_count']}, "
        f"titles={signals['issue_titles']}\n"
        f"  dependency files: {signals['dependency_files']}\n"
        f"  source files available to scan: {signals['code_file_count']}\n\n"
        f"Agents already run: {done or 'none'}\n"
        f"Eligible agents: {eligible}\n\n"
        f"Which agent runs next?"
    )
    decision: SupervisorDecision = llm.invoke(
        [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": prompt}]
    )
    return decision.next_agent, decision.reason.strip()


def route_from_supervisor(state: AgentState) -> str:
    """Conditional edge 3 -- the loop: an agent name, or on to the report."""
    choice = state.get("next_agent", "done")
    return choice if choice in AGENTS else "report"
