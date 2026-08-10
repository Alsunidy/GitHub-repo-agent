"""Specialist agents — each reads repo_data, runs its tools, and asks the
LLM to phrase the raw tool output into human-readable findings.

Every agent must return exactly one element in agents_done (see
HANDOFF.md): the field is accumulated via operator.add, so returning the
full list or omitting the field makes the supervisor think the agent never
ran and re-schedule it.
"""
import json
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

from backend.llm import get_llm
from backend.prompts import docs_system_prompt, issues_system_prompt, security_system_prompt
from backend.state import AgentState
from backend.tools.osv_tools import check_vulnerabilities
from backend.tools.secret_tools import scan_secrets

STALE_DAYS = 90


class FindingItem(BaseModel):
    """One finding, matching the shape in CONTRACTS.md minus the `agent` key
    (each agent stamps its own name on when returning findings)."""

    severity: Literal["critical", "high", "medium", "low", "none"] = Field(
        description="How serious this finding is."
    )
    title: str = Field(description="Short title for the finding.")
    detail: str = Field(description="One or two sentence explanation.")
    evidence: list[str] = Field(
        description="Concrete evidence: vulnerability ids, file:line, issue numbers, ..."
    )


class TitleDetail(BaseModel):
    """The only thing the LLM is allowed to decide per item: its wording."""

    title: str = Field(description="Short title for this specific item.")
    detail: str = Field(description="One or two sentence explanation of this item.")


class TitleDetailBatch(BaseModel):
    items: list[TitleDetail] = Field(
        description="Exactly one entry per input item, in the same order."
    )


def _finding(agent: str, item: FindingItem) -> dict:
    return {
        "agent": agent,
        "severity": item.severity,
        "title": item.title,
        "detail": item.detail,
        "evidence": item.evidence,
    }


def _raw_items(vuln_results: list[dict], secret_results: list[dict]) -> list[dict]:
    """Deterministic, code-built list: one entry per real vulnerable package
    or exposed secret. Severity and evidence live here, not with the LLM —
    this is what makes the number of findings reproducible run to run."""
    items = []
    for vuln in vuln_results:
        if vuln.get("error") or not vuln.get("vuln_ids"):
            continue
        items.append(
            {
                "kind": "vulnerability",
                "severity": "high",
                "evidence": vuln["vuln_ids"],
                "package": vuln["package"],
                "version": vuln["version"],
                "summary": vuln.get("summary", ""),
            }
        )
    for secret in secret_results:
        items.append(
            {
                "kind": "secret",
                "severity": "critical",
                "evidence": [f"{secret['file']}:{secret['line']}"],
                "file": secret["file"],
                "line": secret["line"],
                "secret_kind": secret["kind"],
                "snippet": secret["snippet"],
            }
        )
    return items


def security_agent(state: AgentState) -> dict:
    """Runs the OSV vulnerability scan and the secret scan, builds one raw
    item per real result (fixed structure), and asks the LLM only to write
    the title/detail text for each — never to decide which findings exist
    or how many."""
    language = state.get("language", "en")
    repo_data = state.get("repo_data", {}) or {}
    dependency_files = repo_data.get("dependency_files", {}) or {}
    code_files = repo_data.get("code_files", {}) or {}

    requirements_text = dependency_files.get("requirements.txt", "")
    vuln_results = check_vulnerabilities(requirements_text) if requirements_text else []
    secret_results = scan_secrets(code_files)

    raw_items = _raw_items(vuln_results, secret_results)

    if not raw_items:
        finding_items = [_no_findings_item(language)]
    else:
        texts = _titles_for(raw_items, language)
        finding_items = [
            FindingItem(
                severity=item["severity"],
                title=text.title,
                detail=text.detail,
                evidence=item["evidence"],
            )
            for item, text in zip(raw_items, texts)
        ]

    return {
        "findings": [_finding("security", item) for item in finding_items],
        "agents_done": ["security"],
    }


def _titles_for(raw_items: list[dict], language: str) -> list[TitleDetail]:
    """One (title, detail) per raw_items entry, same order. Falls back to a
    plain, non-generated phrasing if the LLM is unavailable or returns the
    wrong count — the finding set itself never depends on the LLM."""
    try:
        texts = _ask_llm_titles(language, raw_items)
    except Exception:  # noqa: BLE001 — no key, network, bad output: fall back, don't crash the graph
        texts = None

    if texts is not None and len(texts) == len(raw_items):
        return texts
    return [_deterministic_text(item, language) for item in raw_items]


def _ask_llm_titles(language: str, raw_items: list[dict]) -> list[TitleDetail]:
    llm = get_llm(temperature=0).with_structured_output(TitleDetailBatch)
    prompt = (
        "Write a title and detail for each numbered item below. Return "
        "exactly one entry per item, in the same order — do not add, "
        "remove, merge, or reorder items.\n\n"
        f"{json.dumps(raw_items, ensure_ascii=False, indent=2)}"
    )
    result: TitleDetailBatch = llm.invoke(
        [
            {"role": "system", "content": security_system_prompt(language)},
            {"role": "user", "content": prompt},
        ]
    )
    return result.items


def _deterministic_text(item: dict, language: str) -> TitleDetail:
    """Used only if the LLM is unavailable or miscounts — plain, ungenerated
    phrasing straight from the tool output."""
    if item["kind"] == "vulnerability":
        title = (
            f"{item['package']}=={item['version']} لديها ثغرات معروفة"
            if language == "ar"
            else f"{item['package']}=={item['version']} has known vulnerabilities"
        )
        detail = item.get("summary", "")
    else:
        title = (
            f"مفتاح مكشوف ({item['secret_kind']}) في {item['file']}"
            if language == "ar"
            else f"Exposed {item['secret_kind']} in {item['file']}"
        )
        detail = (
            f"تم العثور على سرّ مكتوب مباشرة في السطر {item['line']}."
            if language == "ar"
            else f"A hard-coded secret was found on line {item['line']}."
        )
    return TitleDetail(title=title, detail=detail)


def _no_findings_item(language: str) -> FindingItem:
    title = "لا توجد ملاحظات أمنية" if language == "ar" else "No security findings"
    detail = (
        "لم يُعثر على ثغرات معروفة في الاعتماديات ولا مفاتيح مكشوفة في الكود المفحوص."
        if language == "ar"
        else "No known dependency vulnerabilities or exposed secrets were found in the scanned code."
    )
    return FindingItem(severity="none", title=title, detail=detail, evidence=[])


# --------------------------------------------------------------- issues_agent


class DuplicateGroup(BaseModel):
    """A set of issues the LLM believes describe the same underlying
    problem — language/wording may differ, meaning must not."""

    issue_numbers: list[int] = Field(
        description="Issue numbers that describe the same underlying problem (2 or more)."
    )
    title: str
    detail: str


class PriorityRanking(BaseModel):
    issue_numbers: list[int] = Field(
        description="Up to 3 issue numbers, most important first."
    )
    title: str
    detail: str


class IssuesAnalysis(BaseModel):
    """The only things left for the LLM to decide about the issue list:
    which issues mean the same thing, and which matter most. Staleness is
    computed deterministically before this ever runs — see _stale_issues."""

    duplicate_groups: list[DuplicateGroup] = Field(default_factory=list)
    priority: Optional[PriorityRanking] = None


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _stale_issues(open_issues: list[dict]) -> list[dict]:
    """Deterministic: an issue is stale if it has zero comments and is
    older than STALE_DAYS — dates and counts don't need an LLM's judgment."""
    now = datetime.now(timezone.utc)
    stale = []
    for issue in open_issues:
        if issue.get("comments", 0):
            continue
        try:
            created = _parse_iso(issue["created_at"])
        except (KeyError, TypeError, ValueError):
            continue
        if (now - created).days > STALE_DAYS:
            stale.append(issue)
    return stale


def _stale_finding(stale_issues: list[dict], language: str) -> FindingItem:
    numbers = [f"#{issue['number']}" for issue in stale_issues]
    title = (
        f"{len(stale_issues)} بلاغاً مهملاً (أقدم من {STALE_DAYS} يوماً بلا تعليقات)"
        if language == "ar"
        else f"{len(stale_issues)} stale issue(s) (older than {STALE_DAYS} days, no comments)"
    )
    detail = (
        f"البلاغات التالية لم تحظَ بأي تعليق ومرّ عليها أكثر من {STALE_DAYS} "
        f"يوماً منذ فتحها: {', '.join(numbers)}."
        if language == "ar"
        else f"The following issues have received no comments and are older "
        f"than {STALE_DAYS} days: {', '.join(numbers)}."
    )
    return FindingItem(severity="low", title=title, detail=detail, evidence=numbers)


def _real_issue_numbers(numbers: list[int], valid_numbers: set[int]) -> list[int]:
    """Evidence must come from the actual input, never the model's memory:
    drop any issue number the LLM mentioned that isn't one of this
    repository's real open issues, and de-duplicate. Guards against the LLM
    attaching a stray or hallucinated number to the wrong finding."""
    seen = set()
    result = []
    for n in numbers:
        if n in valid_numbers and n not in seen:
            seen.add(n)
            result.append(n)
    return result


def issues_agent(state: AgentState) -> dict:
    """Splits deterministically-answerable staleness (dates, comment counts,
    computed in code) from what genuinely needs language understanding
    (semantic duplicates — including across Arabic/English — and priority
    judgment), and only asks the LLM for the latter."""
    language = state.get("language", "en")
    repo_data = state.get("repo_data", {}) or {}
    open_issues = repo_data.get("open_issues", []) or []
    valid_numbers = {issue["number"] for issue in open_issues if "number" in issue}

    finding_items = []

    stale = _stale_issues(open_issues)
    if stale:
        finding_items.append(_stale_finding(stale, language))

    try:
        analysis = _ask_llm_issues(language, open_issues)
    except Exception:  # noqa: BLE001 — no key, network, bad output: skip the judgment-based findings, don't crash the graph
        analysis = None

    if analysis:
        for group in analysis.duplicate_groups:
            numbers = _real_issue_numbers(group.issue_numbers, valid_numbers)
            if len(numbers) < 2:
                continue  # not actually a duplicate once fabricated numbers are dropped
            finding_items.append(
                FindingItem(
                    severity="medium",
                    title=group.title,
                    detail=group.detail,
                    evidence=[f"#{n}" for n in numbers],
                )
            )
        if analysis.priority:
            numbers = _real_issue_numbers(analysis.priority.issue_numbers, valid_numbers)[:3]
            if numbers:
                finding_items.append(
                    FindingItem(
                        severity="medium",
                        title=analysis.priority.title,
                        detail=analysis.priority.detail,
                        evidence=[f"#{n}" for n in numbers],
                    )
                )

    if not finding_items:
        finding_items = [_no_issues_findings_item(language)]

    return {
        "findings": [_finding("issues", item) for item in finding_items],
        "agents_done": ["issues"],
    }


def _ask_llm_issues(language: str, open_issues: list[dict]) -> IssuesAnalysis:
    llm = get_llm(temperature=0).with_structured_output(IssuesAnalysis)
    prompt = (
        "Open issues for this repository:\n"
        f"{json.dumps(open_issues, ensure_ascii=False, indent=2)}\n\n"
        "Find genuine duplicate groups (by meaning, including across "
        "languages) and rank the top 3 by priority."
    )
    return llm.invoke(
        [
            {"role": "system", "content": issues_system_prompt(language)},
            {"role": "user", "content": prompt},
        ]
    )


def _no_issues_findings_item(language: str) -> FindingItem:
    title = "لا توجد ملاحظات على البلاغات" if language == "ar" else "No issue findings"
    detail = (
        "لا بلاغات مهملة، ولا تكرار واضح، ولا أولوية تستحق الإبراز بين البلاغات المفتوحة."
        if language == "ar"
        else "No stale issues, no clear duplicates, and no priority worth "
        "calling out among the open issues."
    )
    return FindingItem(severity="none", title=title, detail=detail, evidence=[])


# ----------------------------------------------------------------- docs_agent

# Exactly these four, per CONTRACTS.md and the brief — never more.
_DOC_CRITERIA = ("what_it_is", "installation", "usage", "license")
_DOC_CRITERION_INFO = {
    "what_it_is": {"evidence": "what it is", "en": "what the project is", "ar": "ما هو المشروع"},
    "installation": {"evidence": "installation", "en": "installation steps", "ar": "خطوات التثبيت"},
    "usage": {"evidence": "usage", "en": "usage instructions", "ar": "طريقة التشغيل"},
    "license": {"evidence": "license", "en": "a license", "ar": "الترخيص"},
}


class CriterionAssessment(BaseModel):
    met: bool = Field(description="Whether the README adequately covers this criterion.")
    detail: str = Field(description="One or two sentences: why it's met, or what's missing.")


class DocsAssessment(BaseModel):
    assessments: list[CriterionAssessment] = Field(
        description="Exactly 4 entries, in this fixed order: what_it_is, installation, usage, license."
    )


def docs_agent(state: AgentState) -> dict:
    """Grades the README against exactly four fixed criteria — never more.
    An empty README is a critical finding decided in code, no LLM involved;
    for a non-empty README, the LLM only judges met/not-met and writes the
    explanation for each of the four fixed criteria, in the fixed order."""
    language = state.get("language", "en")
    repo_data = state.get("repo_data", {}) or {}
    readme = (repo_data.get("readme") or "").strip()

    if not readme:
        return {
            "findings": [_finding("docs", _missing_readme_item(language))],
            "agents_done": ["docs"],
        }

    try:
        assessments = _ask_llm_docs(language, readme)
    except Exception:  # noqa: BLE001 — no key, network, bad output: fall back, don't crash the graph
        assessments = None

    if assessments is None or len(assessments) != len(_DOC_CRITERIA):
        assessments = _deterministic_docs_assessment(readme, language)

    finding_items = [
        _missing_criterion_item(criterion, assessment.detail, language)
        for criterion, assessment in zip(_DOC_CRITERIA, assessments)
        if not assessment.met
    ]

    if not finding_items:
        finding_items = [_docs_complete_item(language)]

    return {
        "findings": [_finding("docs", item) for item in finding_items],
        "agents_done": ["docs"],
    }


def _ask_llm_docs(language: str, readme: str) -> list[CriterionAssessment]:
    llm = get_llm(temperature=0).with_structured_output(DocsAssessment)
    prompt = (
        "README content:\n----------------\n"
        f"{readme}\n----------------\n\n"
        "Assess it against the four fixed criteria, in this order: "
        "what_it_is, installation, usage, license."
    )
    result: DocsAssessment = llm.invoke(
        [
            {"role": "system", "content": docs_system_prompt(language)},
            {"role": "user", "content": prompt},
        ]
    )
    return result.assessments


def _deterministic_docs_assessment(readme: str, language: str) -> list[CriterionAssessment]:
    """Used only if the LLM is unavailable — crude keyword heuristics
    instead of real reading comprehension, just enough to keep the graph
    from crashing for lack of an API key."""
    lower = readme.lower()
    met_by_criterion = {
        "what_it_is": len(readme) > 20,  # any real content beyond a bare title
        "installation": any(kw in lower for kw in ("install", "pip install", "npm install", "setup")),
        "usage": any(kw in lower for kw in ("usage", "example", "```", "how to run")),
        "license": any(kw in lower for kw in ("license", "mit", "apache", "gpl")),
    }
    return [
        CriterionAssessment(
            met=met_by_criterion[criterion],
            detail=_deterministic_detail(criterion, met_by_criterion[criterion], language),
        )
        for criterion in _DOC_CRITERIA
    ]


def _deterministic_detail(criterion: str, met: bool, language: str) -> str:
    info = _DOC_CRITERION_INFO[criterion]
    if language == "ar":
        return (
            f"تم رصد إشارة إلى {info['ar']} في README."
            if met
            else f"لم يُعثر على إشارة إلى {info['ar']} في README."
        )
    return (
        f"README appears to cover {info['en']}."
        if met
        else f"README does not appear to cover {info['en']}."
    )


def _missing_criterion_item(criterion: str, detail: str, language: str) -> FindingItem:
    info = _DOC_CRITERION_INFO[criterion]
    title = f"ينقص README: {info['ar']}" if language == "ar" else f"README is missing: {info['en']}"
    return FindingItem(severity="low", title=title, detail=detail, evidence=[info["evidence"]])


def _missing_readme_item(language: str) -> FindingItem:
    title = "لا يوجد ملف README" if language == "ar" else "README is missing"
    detail = (
        "لا يوجد محتوى في README إطلاقاً — لا وصف للمشروع، ولا خطوات تثبيت، "
        "ولا طريقة تشغيل، ولا ترخيص."
        if language == "ar"
        else "There is no README content at all — no project description, "
        "installation steps, usage instructions, or license."
    )
    evidence = [info["evidence"] for info in _DOC_CRITERION_INFO.values()]
    return FindingItem(severity="critical", title=title, detail=detail, evidence=evidence)


def _docs_complete_item(language: str) -> FindingItem:
    title = "التوثيق مكتمل" if language == "ar" else "Documentation is complete"
    detail = (
        "يغطي README المعايير الأربعة: ما هو المشروع، التثبيت، طريقة التشغيل، والترخيص."
        if language == "ar"
        else "The README covers all four criteria: what the project is, "
        "installation, usage, and license."
    )
    return FindingItem(severity="none", title=title, detail=detail, evidence=[])
