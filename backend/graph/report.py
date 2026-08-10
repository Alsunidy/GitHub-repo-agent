"""node التقرير — يجمّع findings المتراكمة من الوكلاء ويكتب التقرير النهائي.

Structure (section order, which findings are "top issues", severity
ranking) is fixed in code, not left to the LLM — the same split used in
agents.py: code decides what can be decided with certainty, the LLM only
writes the prose (executive summary + recommendations). When every finding
is severity "none" (or there are none at all), the report is built without
any LLM call at all, so a healthy repository can never get a fabricated
problem.
"""
import json
import re
from collections import Counter

from pydantic import BaseModel, Field

from backend.llm import get_llm
from backend.prompts import report_system_prompt
from backend.state import AgentState

_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "none": 4}
_AGENT_ORDER = ("security", "issues", "docs")

_LABELS = {
    "en": {
        "title": "Repository Health Report",
        "issue_title_prefix": "Repo health report",
        "executive_summary": "Executive Summary",
        "top_issues": "Top Issues",
        "healthy_line": "No actionable issues were found.",
        "by_area": "Findings by Area",
        "recommendations": "Recommendations",
        "evidence": "Evidence",
        "agents": {"security": "Security", "issues": "Issues", "docs": "Documentation"},
    },
    "ar": {
        "title": "تقرير صحة المستودع",
        "issue_title_prefix": "تقرير صحة المستودع",
        "executive_summary": "الملخص التنفيذي",
        "top_issues": "أخطر المشاكل",
        "healthy_line": "لم يُعثر على أي مشكلة فعلية تستحق العمل عليها.",
        "by_area": "التفاصيل حسب المجال",
        "recommendations": "التوصيات",
        "evidence": "الدليل",
        "agents": {"security": "الأمان", "issues": "البلاغات", "docs": "التوثيق"},
    },
}


class ReportText(BaseModel):
    """The only two things the LLM writes — everything else about the
    report's shape is decided in code before this is ever called."""

    executive_summary: str = Field(
        description="Exactly two sentences summarizing overall repository health."
    )
    # A list, not one string: asked for prose the model returns "1. ... 2. ..."
    # on a single line, which Markdown renders as one item swallowing the rest.
    # One step per entry puts the numbering back in the renderer's hands.
    recommendations: list[str] = Field(
        description="Practical next steps, ONE per entry, each grounded only in "
                    "the given findings. Do not number or bullet them yourself."
    )


def report_node(state: AgentState) -> dict:
    """Reads state["findings"] / state["agents_done"] / state["language"].
    Never assumes all three agents ran — the supervisor may have skipped
    one, so only sections for agents actually in agents_done are built."""
    language = state.get("language", "en")
    findings = state.get("findings", []) or []
    agents_done = state.get("agents_done", []) or []
    repo_data = state.get("repo_data", {}) or {}
    full_name = (repo_data.get("meta") or {}).get("full_name") or (
        f"{state.get('owner', '')}/{state.get('repo', '')}"
    )

    labels = _LABELS["ar" if language == "ar" else "en"]

    # Deterministic ranking — the model never decides finding order.
    sorted_findings = sorted(findings, key=lambda f: _SEVERITY_RANK.get(f.get("severity"), 99))
    actionable = [f for f in sorted_findings if f.get("severity") != "none"]
    top_issues = actionable[:3]

    if actionable:
        try:
            text = _ask_llm_report(language, sorted_findings, agents_done)
        except Exception:  # noqa: BLE001 — no key, network, bad output: fall back, don't crash the graph
            text = _deterministic_report_text(actionable, language)
        # An empty (or all-blank) list would leave the section headed and
        # empty — fall back rather than print a heading over nothing.
        if not _clean_recommendations(text.recommendations):
            text.recommendations = _deterministic_report_text(actionable, language).recommendations
    else:
        # Nothing actionable: never call the LLM — a healthy repo must
        # never risk a fabricated problem.
        text = _healthy_report_text(language)

    report = _render_report(labels, text, top_issues, sorted_findings, agents_done, full_name)

    return {
        "report": report,
        "issue_title": f"{labels['issue_title_prefix']} — {full_name}",
        "issue_body": report,
    }


def _ask_llm_report(language: str, sorted_findings: list[dict], agents_done: list[str]) -> ReportText:
    llm = get_llm(temperature=0).with_structured_output(ReportText)
    prompt = (
        f"Agents that ran: {agents_done}\n\n"
        "All findings, already sorted most severe first:\n"
        f"{json.dumps(sorted_findings, ensure_ascii=False, indent=2)}\n\n"
        "Write the executive summary and recommendations only."
    )
    return llm.invoke(
        [
            {"role": "system", "content": report_system_prompt(language)},
            {"role": "user", "content": prompt},
        ]
    )


def _deterministic_report_text(actionable: list[dict], language: str) -> ReportText:
    """Used only if the LLM call fails — a plain, non-generated summary
    straight from the finding counts so the graph never crashes for lack
    of an API key."""
    counts = Counter(f.get("severity", "unknown") for f in actionable)
    breakdown = ", ".join(f"{n} {sev}" for sev, n in counts.items())
    if language == "ar":
        summary = (
            f"تم العثور على {len(actionable)} ملاحظة تحتاج انتباهاً في هذا المستودع ({breakdown}). "
            "أخطرها مذكور أدناه مع الأدلة."
        )
        recommendations = ["راجع القسم أعلاه وعالج الملاحظات الأشد خطورة أولاً."]
    else:
        summary = (
            f"{len(actionable)} finding(s) need attention in this repository ({breakdown}). "
            "The most severe are listed below with their evidence."
        )
        recommendations = ["Review the findings below and address the most severe ones first."]
    return ReportText(executive_summary=summary, recommendations=recommendations)


def _healthy_report_text(language: str) -> ReportText:
    if language == "ar":
        return ReportText(
            executive_summary=(
                "لم يُعثر على أي مشكلة فعلية في هذا المستودع بناءً على ما فحصناه — "
                "المستودع في حالة سليمة."
            ),
            recommendations=["لا توصيات مطلوبة حالياً؛ يُستحسن إعادة الفحص دورياً مع تطور المستودع."],
        )
    return ReportText(
        executive_summary=(
            "No actual problems were found in this repository based on what was "
            "checked — the repository is healthy."
        ),
        recommendations=[
            "No recommendations needed right now; re-run this review periodically "
            "as the repository evolves."
        ],
    )


def _render_report(
    labels: dict,
    text: ReportText,
    top_issues: list[dict],
    sorted_findings: list[dict],
    agents_done: list[str],
    full_name: str,
) -> str:
    lines = [
        f"# {labels['title']} — {full_name}",
        "",
        f"## {labels['executive_summary']}",
        "",
        text.executive_summary,
        "",
        f"## {labels['top_issues']}",
        "",
    ]

    if top_issues:
        for i, finding in enumerate(top_issues, start=1):
            lines.append(f"{i}. {_render_finding_line(finding, labels)}")
    else:
        lines.append(labels["healthy_line"])
    lines.append("")

    lines.append(f"## {labels['by_area']}")
    lines.append("")
    for agent in _AGENT_ORDER:
        if agent not in agents_done:
            continue
        agent_findings = [f for f in sorted_findings if f.get("agent") == agent]
        if not agent_findings:
            continue
        lines.append(f"### {labels['agents'][agent]}")
        for finding in agent_findings:
            lines.append(f"- {_render_finding_line(finding, labels)}")
        lines.append("")

    lines.append(f"## {labels['recommendations']}")
    lines.append("")
    for i, recommendation in enumerate(_clean_recommendations(text.recommendations), start=1):
        lines.append(f"{i}. {recommendation}")

    return "\n".join(lines).strip() + "\n"


# "1. ", "2) ", "- ", "* ", "• " at the start of an entry.
_LEADING_MARKER = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s+")


def _clean_recommendations(recommendations: list[str]) -> list[str]:
    """The model is told not to number its own entries; when it does anyway,
    the numbering added here would double up ("1. 1. ..."). Strip whatever
    marker it prefixed, and drop blank entries."""
    cleaned = []
    for item in recommendations or []:
        stripped = _LEADING_MARKER.sub("", (item or "").strip()).strip()
        if stripped:
            cleaned.append(stripped)
    return cleaned


def _render_finding_line(finding: dict, labels: dict) -> str:
    evidence = ", ".join(finding.get("evidence", [])) or "—"
    return (
        f"**[{finding.get('severity')}] {finding.get('title')}** — {finding.get('detail')} "
        f"({labels['evidence']}: {evidence})"
    )
