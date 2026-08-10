"""Tests for backend/graph/report.py — no network, no LLM keys required:
get_llm is mocked at the module boundary. The "everything is healthy" path
is asserted to never call get_llm at all — a healthy repo must never risk a
fabricated problem."""
from unittest.mock import MagicMock

from backend.graph.report import ReportText, report_node


def _fake_llm(return_value=None, raise_exc=None):
    chain = MagicMock()
    if raise_exc is not None:
        chain.invoke.side_effect = raise_exc
    else:
        chain.invoke.return_value = return_value
    llm = MagicMock()
    llm.with_structured_output.return_value = chain
    return llm


def _never_call_llm():
    def _boom(*_args, **_kwargs):
        raise AssertionError("get_llm should not be called on this path")

    return _boom


def _finding(agent, severity, title, evidence=None):
    return {
        "agent": agent,
        "severity": severity,
        "title": title,
        "detail": f"detail for {title}",
        "evidence": evidence or [],
    }


def _state(findings, agents_done, **overrides):
    state = {
        "language": "en",
        "owner": "owner",
        "repo": "repo",
        "repo_data": {"meta": {"full_name": "owner/repo"}},
        "findings": findings,
        "agents_done": agents_done,
    }
    state.update(overrides)
    return state


def test_report_node_returns_the_three_contract_keys(monkeypatch):
    findings = [_finding("security", "critical", "Exposed secret")]
    state = _state(findings, ["security"])
    fake = _fake_llm(return_value=ReportText(executive_summary="Summary.", recommendations="Fix it."))
    monkeypatch.setattr("backend.graph.report.get_llm", lambda *a, **k: fake)

    result = report_node(state)

    assert set(result) == {"report", "issue_title", "issue_body"}
    assert result["issue_body"] == result["report"]
    assert result["issue_title"] == "Repo health report — owner/repo"


def test_report_node_ranks_findings_by_severity_deterministically(monkeypatch):
    findings = [
        _finding("docs", "low", "Missing license"),
        _finding("security", "critical", "Exposed secret"),
        _finding("issues", "medium", "Duplicate issues"),
        _finding("security", "high", "Vulnerable package"),
    ]
    state = _state(findings, ["security", "issues", "docs"])
    fake = _fake_llm(return_value=ReportText(executive_summary="Summary.", recommendations="Fix it."))
    monkeypatch.setattr("backend.graph.report.get_llm", lambda *a, **k: fake)

    result = report_node(state)

    top_section = result["report"].split("## Top Issues")[1].split("## Findings by Area")[0]
    # most severe first: critical, then high, then medium — the low one
    # doesn't fit in the top 3 and must be excluded from this section.
    assert (
        top_section.index("Exposed secret")
        < top_section.index("Vulnerable package")
        < top_section.index("Duplicate issues")
    )
    assert "Missing license" not in top_section
    # ... but it's still visible in the full by-area breakdown.
    assert "Missing license" in result["report"]


def test_report_node_all_none_findings_gives_healthy_report_without_llm(monkeypatch):
    findings = [
        _finding("security", "none", "No security findings"),
        _finding("issues", "none", "No issue findings"),
        _finding("docs", "none", "Documentation is complete"),
    ]
    state = _state(findings, ["security", "issues", "docs"])
    monkeypatch.setattr("backend.graph.report.get_llm", _never_call_llm())

    result = report_node(state)

    assert "No actionable issues were found." in result["report"]
    assert "healthy" in result["report"].lower()


def test_report_node_no_findings_at_all_gives_healthy_report_without_llm(monkeypatch):
    state = _state(findings=[], agents_done=[])
    monkeypatch.setattr("backend.graph.report.get_llm", _never_call_llm())

    result = report_node(state)

    assert "healthy" in result["report"].lower()


def test_report_node_falls_back_deterministically_when_llm_fails(monkeypatch):
    findings = [_finding("security", "critical", "Exposed secret", evidence=["config.py:1"])]
    state = _state(findings, ["security"])
    fake = _fake_llm(raise_exc=RuntimeError("no API key"))
    monkeypatch.setattr("backend.graph.report.get_llm", lambda *a, **k: fake)

    result = report_node(state)

    assert "1 finding(s) need attention" in result["report"]
    assert "Exposed secret" in result["report"]


def test_report_node_skips_sections_for_agents_that_never_ran():
    # Only docs ran; findings is all-"none" so the healthy path is taken
    # (no LLM call needed either) — this also proves agents_done gates
    # which "## Findings by Area" subsections get built.
    findings = [_finding("docs", "none", "Documentation is complete")]
    state = _state(findings, ["docs"])

    result = report_node(state)

    assert "### Security" not in result["report"]
    assert "### Issues" not in result["report"]
    assert "### Documentation" in result["report"]
