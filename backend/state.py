"""Contract 1 -- the State shared by every node.

This file is owned by track 1. Any change to a field name or type must be
reported to the other track immediately (contract rule 3).
"""

import operator
from typing import Annotated, Optional, TypedDict


class AgentState(TypedDict):
    """One repository analysis, from the URL through to the opened issue."""

    # --- inputs ---
    repo_url: str                 # the URL exactly as the user typed it
    language: str                 # "en" | "ar" -- language of the report and messages

    # --- filled by the guardrail ---
    owner: str                    # owner name parsed from the URL
    repo: str                     # repository name parsed from the URL
    rejection_reason: Optional[str]   # rejection text, or None when the request is fine

    # --- filled by the fetch tool (written once) ---
    repo_data: dict               # see "repo_data shape" in CONTRACTS.md

    # --- decided by the supervisor on every round ---
    next_agent: str               # "security" | "issues" | "docs" | "done"

    # --- accumulated (Annotated + operator.add) ---
    agents_done: Annotated[list[str], operator.add]      # names of the agents that ran
    findings: Annotated[list[dict], operator.add]        # see "finding shape"

    # --- final outputs ---
    report: str                   # Markdown report in the user's language
    issue_url: Optional[str]      # issue link once opened, or None

    # --- contract addition: human-in-the-loop ---
    # Without these fields /approve has no way to know what to open.
    # Purely additive: nothing the other track relied on has changed.
    issue_title: str              # proposed issue title, shown by the UI before approval
    issue_body: str               # proposed issue body (condensed from the report)
    approved: Optional[bool]      # None = not asked yet | True = approved | False = declined

    # --- contract addition: a trace of the supervisor's decisions ---
    # The brief asks for tracing to be shown in the demo: "or your own logged state".
    supervisor_log: Annotated[list[str], operator.add]


def initial_state(repo_url: str, language: str = "en") -> AgentState:
    """A complete starting state, so no node ever trips over a missing key."""
    return AgentState(
        repo_url=repo_url,
        language=language if language in ("en", "ar") else "en",
        owner="",
        repo="",
        rejection_reason=None,
        repo_data={},
        next_agent="",
        agents_done=[],
        findings=[],
        report="",
        issue_url=None,
        issue_title="",
        issue_body="",
        approved=None,
        supervisor_log=[],
    )
