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


def _finding(agent, severity, title, evidence=None, **extra):
    finding = {
        "agent": agent,
        "severity": severity,
        "title": title,
        "detail": f"detail for {title}",
        "evidence": evidence or [],
    }
    finding.update(extra)
    return finding


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
    fake = _fake_llm(return_value=ReportText(executive_summary="Summary.", recommendations=["Fix it."]))
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
    fake = _fake_llm(return_value=ReportText(executive_summary="Summary.", recommendations=["Fix it."]))
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


def test_report_node_by_area_condenses_findings_already_in_top_issues(monkeypatch):
    findings = [
        _finding("docs", "low", "Missing license"),
        _finding("security", "critical", "Exposed secret"),
        _finding("issues", "medium", "Duplicate issues"),
        _finding("security", "high", "Vulnerable package"),
    ]
    state = _state(findings, ["security", "issues", "docs"])
    fake = _fake_llm(return_value=ReportText(executive_summary="Summary.", recommendations=["Fix it."]))
    monkeypatch.setattr("backend.graph.report.get_llm", lambda *a, **k: fake)

    result = report_node(state)
    by_area = result["report"].split("## Findings by Area")[1].split("## Recommendations")[0]

    # the three findings that made the top 3 are pointed at, not repeated
    for title in ("Exposed secret", "Vulnerable package", "Duplicate issues"):
        line = next(line for line in by_area.splitlines() if title in line)
        assert "see" in line.lower() and "detail for" not in line

    # the one finding that did NOT make the top 3 still gets its full text
    missing_license_line = next(line for line in by_area.splitlines() if "Missing license" in line)
    assert "detail for Missing license" in missing_license_line


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


def test_report_node_numbers_each_recommendation_on_its_own_line(monkeypatch):
    # The model used to be asked for recommendations as one string and would
    # answer "1. ... 2. ... 3. ..." inline, which Markdown renders as a single
    # list item swallowing the rest. One entry per step, numbered by the code.
    findings = [_finding("security", "critical", "Exposed secret")]
    state = _state(findings, ["security"])
    fake = _fake_llm(
        return_value=ReportText(
            executive_summary="Summary.",
            # the second entry arrives pre-numbered — the model ignoring its
            # instructions must not produce "2. 1. Update the dependency."
            recommendations=["Remove the secret.", "1. Update the dependency.", "  "],
        )
    )
    monkeypatch.setattr("backend.graph.report.get_llm", lambda *a, **k: fake)

    section = report_node(state)["report"].split("## Recommendations")[1].strip()

    assert section.splitlines() == [
        "1. Remove the secret.",
        "2. Update the dependency.",
    ]


def test_report_node_falls_back_when_the_model_returns_no_recommendations(monkeypatch):
    findings = [_finding("security", "critical", "Exposed secret")]
    state = _state(findings, ["security"])
    fake = _fake_llm(
        return_value=ReportText(executive_summary="Summary.", recommendations=[])
    )
    monkeypatch.setattr("backend.graph.report.get_llm", lambda *a, **k: fake)

    section = report_node(state)["report"].split("## Recommendations")[1].strip()

    assert section == "1. Review the findings below and address the most severe ones first."


def test_report_node_writes_exact_upgrade_recommendation_in_english(monkeypatch):
    findings = [
        _finding(
            "security", "high", "Flask DoS vulnerability",
            evidence=["GHSA-xxxx"], package="flask", current_version="0.12.2", fixed_version="3.1.3",
        )
    ]
    state = _state(findings, ["security"])
    fake = _fake_llm(
        return_value=ReportText(executive_summary="Summary.", recommendations=["Rotate any leaked secrets."])
    )
    monkeypatch.setattr("backend.graph.report.get_llm", lambda *a, **k: fake)

    section = report_node(state)["report"].split("## Recommendations")[1].strip()

    assert section.splitlines() == [
        "1. Update flask from 0.12.2 to 3.1.3 or newer.",
        "2. Rotate any leaked secrets.",
    ]


def test_report_node_writes_exact_upgrade_recommendation_in_arabic(monkeypatch):
    findings = [
        _finding(
            "security", "high", "ثغرة في Flask",
            evidence=["GHSA-xxxx"], package="flask", current_version="0.12.2", fixed_version="3.1.3",
        )
    ]
    state = _state(findings, ["security"], language="ar")
    fake = _fake_llm(
        return_value=ReportText(executive_summary="ملخص.", recommendations=["راجع سجل الأمان دورياً."])
    )
    monkeypatch.setattr("backend.graph.report.get_llm", lambda *a, **k: fake)

    section = report_node(state)["report"].split("## التوصيات")[1].strip()

    assert section.splitlines() == [
        "1. حدّث flask من 0.12.2 إلى 3.1.3 أو أحدث.",
        "2. راجع سجل الأمان دورياً.",
    ]


def test_report_node_upgrade_recommendation_survives_llm_failure(monkeypatch):
    findings = [
        _finding(
            "security", "high", "Flask DoS vulnerability",
            evidence=["GHSA-xxxx"], package="flask", current_version="0.12.2", fixed_version="3.1.3",
        )
    ]
    state = _state(findings, ["security"])
    fake = _fake_llm(raise_exc=RuntimeError("no API key"))
    monkeypatch.setattr("backend.graph.report.get_llm", lambda *a, **k: fake)

    section = report_node(state)["report"].split("## Recommendations")[1].strip()

    assert section.splitlines()[0] == "1. Update flask from 0.12.2 to 3.1.3 or newer."


def test_report_node_drops_llm_recommendation_that_repeats_a_covered_package(monkeypatch):
    # The model is told which packages already have an exact instruction; if
    # it names one anyway (ignoring that note), the line must not survive --
    # two conflicting version claims for the same package would be worse
    # than one correct one.
    findings = [
        _finding(
            "security", "high", "Flask DoS vulnerability",
            evidence=["GHSA-xxxx"], package="flask", current_version="0.12.2", fixed_version="3.1.3",
        )
    ]
    state = _state(findings, ["security"])
    fake = _fake_llm(
        return_value=ReportText(
            executive_summary="Summary.",
            recommendations=["Upgrade flask to the latest release as soon as possible."],
        )
    )
    monkeypatch.setattr("backend.graph.report.get_llm", lambda *a, **k: fake)

    section = report_node(state)["report"].split("## Recommendations")[1].strip()

    assert section == "1. Update flask from 0.12.2 to 3.1.3 or newer."


def test_report_node_drops_covered_package_regardless_of_case(monkeypatch):
    # The model writes package names as normal prose ("Flask", "PyYAML"),
    # not as the lowercase name requirements.txt uses -- the dedup check
    # must not be case-sensitive, or a capitalized duplicate slips through.
    findings = [
        _finding(
            "security", "high", "Flask DoS vulnerability",
            evidence=["GHSA-xxxx"], package="flask", current_version="0.12.2", fixed_version="3.1.3",
        )
    ]
    state = _state(findings, ["security"])
    fake = _fake_llm(
        return_value=ReportText(
            executive_summary="Summary.",
            recommendations=["Update the Flask package to the latest release."],
        )
    )
    monkeypatch.setattr("backend.graph.report.get_llm", lambda *a, **k: fake)

    section = report_node(state)["report"].split("## Recommendations")[1].strip()

    assert section == "1. Update flask from 0.12.2 to 3.1.3 or newer."


def test_report_node_no_upgrade_line_without_fixed_version(monkeypatch):
    findings = [_finding("security", "critical", "Exposed secret", package=None, fixed_version=None)]
    state = _state(findings, ["security"])
    fake = _fake_llm(return_value=ReportText(executive_summary="Summary.", recommendations=["Rotate the key."]))
    monkeypatch.setattr("backend.graph.report.get_llm", lambda *a, **k: fake)

    section = report_node(state)["report"].split("## Recommendations")[1].strip()

    assert section == "1. Rotate the key."


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
