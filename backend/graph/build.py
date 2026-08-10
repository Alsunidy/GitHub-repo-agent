"""Graph assembly: nodes, conditional edges, the loop, and the human approval gate.

    START
      ↓
  guardrail ──rejected──────────────────────────────────────┐
      ↓ fetch                                               │
    fetch ────failed────────────────────────────────────────┤
      ↓ supervisor                                          │
  ┌─→ supervisor ──security/issues/docs──→ agent ──┐        │
  └──────────────────────────────────────────────── ┘        │
      ↓ report                                              │
    report                                                  │
      ↓                                                     │
  ⏸ interrupt — human approval                              │
      ↓                                                     │
    publish ────────────────────────────────────────────────┴──→ END

Three conditional edges that genuinely change the path:
  1. route_after_guardrail — an invalid URL ends the run with no external call.
  2. route_after_fetch     — a tool failure ends the run before any agent starts.
  3. route_from_supervisor — the loop: which agent, or on to the report?
"""

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from backend.graph.fetch import fetch_node, route_after_fetch
from backend.graph.guardrail import guardrail_node, route_after_guardrail
from backend.graph.supervisor import route_from_supervisor, supervisor_node
from backend.state import AgentState

# -- temporary: delete at the first integration point (see backend/stubs.py) --
try:
    from backend.graph.agents import docs_agent, issues_agent, security_agent
    from backend.graph.report import report_node
except ImportError:  # pragma: no cover
    from backend.stubs import docs_agent, issues_agent, report_node, security_agent

try:
    from backend.tools.github_tools import MissingToken, open_issue
except ImportError:  # pragma: no cover
    from backend.stubs import MissingToken, open_issue
# ---------------------------------------------------------------------------

# User-facing text stays bilingual -- see the note in guardrail.py.
_PUBLISH_MESSAGES = {
    "cancelled": {
        "en": "No issue was opened — you declined.",
        "ar": "لم يُفتح أي بلاغ — رفضتَ النشر.",
    },
    "missing_token": {
        "en": "Approved, but no issue was opened: GITHUB_TOKEN is not set. "
              "The report above is unaffected.",
        "ar": "تمت الموافقة، لكن لم يُفتح البلاغ: GITHUB_TOKEN غير مضبوط. "
              "التقرير أعلاه غير متأثر.",
    },
    "failed": {
        "en": "Approved, but opening the issue failed: {error}. "
              "The report above is unaffected.",
        "ar": "تمت الموافقة، لكن فتح البلاغ فشل: {error}. "
              "التقرير أعلاه غير متأثر.",
    },
}


def publish_node(state: AgentState) -> dict:
    """Runs only after human approval -- the only node that writes to the world."""
    language = state.get("language", "en")

    if not state.get("approved"):
        return {
            "issue_url": None,
            "supervisor_log": [
                f"publish: cancelled — {_PUBLISH_MESSAGES['cancelled'][language]}"
            ],
        }

    try:
        url = open_issue(
            state["owner"],
            state["repo"],
            state.get("issue_title") or f"Repo health report — {state['repo']}",
            state.get("issue_body") or state.get("report", ""),
        )
    except MissingToken:
        return {
            "issue_url": None,
            "supervisor_log": [
                f"publish: failed — {_PUBLISH_MESSAGES['missing_token'][language]}"
            ],
        }
    except Exception as exc:  # noqa: BLE001 -- a write failure must not lose the analysis
        message = _PUBLISH_MESSAGES["failed"][language].format(
            error=f"{type(exc).__name__}: {exc}"
        )
        return {"issue_url": None, "supervisor_log": [f"publish: failed — {message}"]}

    return {"issue_url": url, "supervisor_log": [f"publish: opened {url}"]}


def build_graph(checkpointer=None):
    """Build the graph, compiled to pause before publishing for human approval."""
    builder = StateGraph(AgentState)

    builder.add_node("guardrail", guardrail_node)
    builder.add_node("fetch", fetch_node)
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("security", security_agent)
    builder.add_node("issues", issues_agent)
    builder.add_node("docs", docs_agent)
    builder.add_node("report", report_node)
    builder.add_node("publish", publish_node)

    builder.add_edge(START, "guardrail")

    # (1) invalid URL -> a polite end, with no external call at all
    builder.add_conditional_edges(
        "guardrail",
        route_after_guardrail,
        {"rejected": END, "fetch": "fetch"},
    )

    # (2) fetch failure -> end without running a single agent
    builder.add_conditional_edges(
        "fetch",
        route_after_fetch,
        {"failed": END, "supervisor": "supervisor"},
    )

    # (3) the loop: the supervisor dispatches, every agent returns to it
    builder.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "security": "security",
            "issues": "issues",
            "docs": "docs",
            "report": "report",
        },
    )
    for agent in ("security", "issues", "docs"):
        builder.add_edge(agent, "supervisor")

    builder.add_edge("report", "publish")
    builder.add_edge("publish", END)

    # The checkpointer is what makes the interrupt work: without it there is no
    # thread_id to resume from.
    return builder.compile(
        checkpointer=checkpointer or MemorySaver(),
        interrupt_before=["publish"],
    )
