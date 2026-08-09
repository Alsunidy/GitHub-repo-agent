"""تركيب الـ graph: الـ nodes، المسارات الشرطية، الحلقة، ونقطة الموافقة البشرية.

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
  ⏸ interrupt — الموافقة البشرية                            │
      ↓                                                     │
    publish ────────────────────────────────────────────────┴──→ END

ثلاثة مسارات شرطية تغيّر المسار فعلياً:
  1. route_after_guardrail — رابط غير صالح ينهي التنفيذ فوراً بلا أي استدعاء خارجي.
  2. route_after_fetch     — فشل الأداة ينهي التنفيذ بلا تشغيل أي وكيل.
  3. route_from_supervisor — الحلقة: أي وكيل، أم إلى التقرير؟
"""

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from backend.graph.fetch import fetch_node, route_after_fetch
from backend.graph.guardrail import guardrail_node, route_after_guardrail
from backend.graph.supervisor import route_from_supervisor, supervisor_node
from backend.state import AgentState

# ── مؤقت: يُحذف عند نقطة الالتقاء الأولى (انظر backend/stubs.py) ──
try:
    from backend.graph.agents import docs_agent, issues_agent, security_agent
    from backend.graph.report import report_node
except ImportError:  # pragma: no cover
    from backend.stubs import docs_agent, issues_agent, report_node, security_agent

try:
    from backend.tools.github_tools import MissingToken, open_issue
except ImportError:  # pragma: no cover
    from backend.stubs import MissingToken, open_issue
# ──────────────────────────────────────────────────────────────────

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
    """يعمل بعد الموافقة البشرية فقط — الوحيد الذي يكتب في العالم الخارجي."""
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
    except Exception as exc:  # noqa: BLE001 — فشل الكتابة لا يُسقط التحليل
        message = _PUBLISH_MESSAGES["failed"][language].format(
            error=f"{type(exc).__name__}: {exc}"
        )
        return {"issue_url": None, "supervisor_log": [f"publish: failed — {message}"]}

    return {"issue_url": url, "supervisor_log": [f"publish: opened {url}"]}


def build_graph(checkpointer=None):
    """يبني الـ graph ويُصرّفه متوقفاً قبل النشر بانتظار الموافقة البشرية."""
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

    # (1) رابط غير صالح → نهاية مؤدبة بلا أي استدعاء خارجي
    builder.add_conditional_edges(
        "guardrail",
        route_after_guardrail,
        {"rejected": END, "fetch": "fetch"},
    )

    # (2) فشل الجلب → نهاية بلا تشغيل أي وكيل
    builder.add_conditional_edges(
        "fetch",
        route_after_fetch,
        {"failed": END, "supervisor": "supervisor"},
    )

    # (3) الحلقة: المشرف يوزّع، وكل وكيل يعود إليه
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

    # الـ checkpointer شرط لعمل الـ interrupt: بدونه لا يوجد thread_id يُستأنف منه.
    return builder.compile(
        checkpointer=checkpointer or MemorySaver(),
        interrupt_before=["publish"],
    )
