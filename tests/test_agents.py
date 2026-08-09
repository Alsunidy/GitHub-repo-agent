"""Tests for backend/graph/agents.py — no network, no LLM keys required:
get_llm is mocked at the module boundary for every test. Each agent is
tested both with a mocked "successful" LLM response and with the LLM
raising, to prove the deterministic fallback actually engages."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from backend.graph.agents import (
    CriterionAssessment,
    DocsAssessment,
    DuplicateGroup,
    IssuesAnalysis,
    PriorityRanking,
    TitleDetail,
    TitleDetailBatch,
    docs_agent,
    issues_agent,
    security_agent,
)

_FINDING_KEYS = {"agent", "severity", "title", "detail", "evidence"}


def _fake_llm(return_value=None, raise_exc=None):
    """Mimics get_llm(...).with_structured_output(Model) -> chain with .invoke()."""
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


def _base_repo_data(**overrides):
    data = {
        "meta": {"full_name": "owner/repo"},
        "readme": "",
        "open_issues": [],
        "dependency_files": {},
        "code_files": {},
    }
    data.update(overrides)
    return data


def _state(repo_data, language="en"):
    return {"language": language, "owner": "owner", "repo": "repo", "repo_data": repo_data}


def _issue(number, title, body, days_ago, comments):
    created = (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "number": number,
        "title": title,
        "body": body,
        "created_at": created,
        "comments": comments,
        "labels": [],
    }


def _assert_valid_findings(findings, agent_name):
    assert len(findings) >= 1
    for finding in findings:
        assert set(finding) == _FINDING_KEYS
        assert finding["agent"] == agent_name
        assert finding["severity"] in {"critical", "high", "medium", "low", "none"}


# --------------------------------------------------------------- security_agent


def test_security_agent_llm_success_produces_one_finding_per_secret(monkeypatch):
    code_files = {"config.py": 'TOKEN = "ghp_0123456789abcdefghijklmnopqrstuvwxyz"\n'}
    state = _state(_base_repo_data(code_files=code_files))

    fake = _fake_llm(
        return_value=TitleDetailBatch(
            items=[TitleDetail(title="Exposed GitHub token", detail="A token was hard-coded.")]
        )
    )
    monkeypatch.setattr("backend.graph.agents.get_llm", lambda *a, **k: fake)

    result = security_agent(state)

    assert result["agents_done"] == ["security"]
    _assert_valid_findings(result["findings"], "security")
    assert len(result["findings"]) == 1
    assert result["findings"][0]["severity"] == "critical"
    assert result["findings"][0]["evidence"] == ["config.py:1"]


def test_security_agent_falls_back_deterministically_when_llm_fails(monkeypatch):
    code_files = {"config.py": 'TOKEN = "ghp_0123456789abcdefghijklmnopqrstuvwxyz"\n'}
    state = _state(_base_repo_data(code_files=code_files))

    fake = _fake_llm(raise_exc=RuntimeError("no API key"))
    monkeypatch.setattr("backend.graph.agents.get_llm", lambda *a, **k: fake)

    result = security_agent(state)

    assert result["agents_done"] == ["security"]
    _assert_valid_findings(result["findings"], "security")
    assert len(result["findings"]) == 1
    assert result["findings"][0]["severity"] == "critical"
    assert result["findings"][0]["evidence"] == ["config.py:1"]


def test_security_agent_reports_none_when_nothing_found_and_never_calls_llm(monkeypatch):
    state = _state(_base_repo_data())
    monkeypatch.setattr("backend.graph.agents.get_llm", _never_call_llm())

    result = security_agent(state)

    assert result["agents_done"] == ["security"]
    _assert_valid_findings(result["findings"], "security")
    assert result["findings"][0]["severity"] == "none"


# ----------------------------------------------------------------- issues_agent


def test_issues_agent_llm_success_reports_duplicates_and_priority(monkeypatch):
    open_issues = [
        _issue(1, "App crashes on empty input", "Crashes on empty string.", 5, 2),
        _issue(2, "يتعطل التطبيق عند إدخال فارغ", "نفس المشكلة بالعربية.", 3, 0),
    ]
    state = _state(_base_repo_data(open_issues=open_issues))

    analysis = IssuesAnalysis(
        duplicate_groups=[
            DuplicateGroup(
                issue_numbers=[1, 2],
                title="Duplicate crash reports",
                detail="Same bug reported in two languages.",
            )
        ],
        priority=PriorityRanking(
            issue_numbers=[1], title="Fix the crash", detail="Most impactful issue."
        ),
    )
    fake = _fake_llm(return_value=analysis)
    monkeypatch.setattr("backend.graph.agents.get_llm", lambda *a, **k: fake)

    result = issues_agent(state)

    assert result["agents_done"] == ["issues"]
    _assert_valid_findings(result["findings"], "issues")
    assert len(result["findings"]) == 2  # duplicate group + priority; nothing stale here

    duplicate = next(f for f in result["findings"] if f["title"] == "Duplicate crash reports")
    assert duplicate["evidence"] == ["#1", "#2"]
    assert duplicate["severity"] == "medium"


def test_issues_agent_stale_detection_is_deterministic_when_llm_fails(monkeypatch):
    open_issues = [_issue(3, "Typo in docs", "recieve -> receive", 200, 0)]
    state = _state(_base_repo_data(open_issues=open_issues))

    fake = _fake_llm(raise_exc=RuntimeError("no API key"))
    monkeypatch.setattr("backend.graph.agents.get_llm", lambda *a, **k: fake)

    result = issues_agent(state)

    assert result["agents_done"] == ["issues"]
    _assert_valid_findings(result["findings"], "issues")
    assert len(result["findings"]) == 1
    assert result["findings"][0]["severity"] == "low"
    assert result["findings"][0]["evidence"] == ["#3"]


def test_issues_agent_reports_none_when_nothing_to_report(monkeypatch):
    open_issues = [_issue(9, "Recent issue with activity", "Still relevant.", 2, 3)]
    state = _state(_base_repo_data(open_issues=open_issues))

    fake = _fake_llm(return_value=IssuesAnalysis(duplicate_groups=[], priority=None))
    monkeypatch.setattr("backend.graph.agents.get_llm", lambda *a, **k: fake)

    result = issues_agent(state)

    assert result["agents_done"] == ["issues"]
    _assert_valid_findings(result["findings"], "issues")
    assert result["findings"][0]["severity"] == "none"


# ------------------------------------------------------------------- docs_agent


def test_docs_agent_empty_readme_is_deterministic_and_never_calls_llm(monkeypatch):
    state = _state(_base_repo_data(readme=""))
    monkeypatch.setattr("backend.graph.agents.get_llm", _never_call_llm())

    result = docs_agent(state)

    assert result["agents_done"] == ["docs"]
    _assert_valid_findings(result["findings"], "docs")
    assert len(result["findings"]) == 1
    assert result["findings"][0]["severity"] == "critical"
    assert set(result["findings"][0]["evidence"]) == {
        "what it is",
        "installation",
        "usage",
        "license",
    }


def test_docs_agent_llm_success_reports_only_missing_criteria(monkeypatch):
    readme = "# Project\n\nDoes a thing. Install with pip. MIT licensed."
    state = _state(_base_repo_data(readme=readme))

    assessment = DocsAssessment(
        assessments=[
            CriterionAssessment(met=True, detail="Covered."),
            CriterionAssessment(met=True, detail="Covered."),
            CriterionAssessment(met=False, detail="No usage example given."),
            CriterionAssessment(met=True, detail="Covered."),
        ]
    )
    fake = _fake_llm(return_value=assessment)
    monkeypatch.setattr("backend.graph.agents.get_llm", lambda *a, **k: fake)

    result = docs_agent(state)

    assert result["agents_done"] == ["docs"]
    _assert_valid_findings(result["findings"], "docs")
    assert len(result["findings"]) == 1
    assert result["findings"][0]["evidence"] == ["usage"]
    assert result["findings"][0]["severity"] == "low"


def test_docs_agent_all_criteria_met_reports_complete(monkeypatch):
    readme = "# Project\n\nDoes a thing. Install with pip. MIT licensed."
    state = _state(_base_repo_data(readme=readme))

    assessment = DocsAssessment(
        assessments=[CriterionAssessment(met=True, detail="Covered.") for _ in range(4)]
    )
    fake = _fake_llm(return_value=assessment)
    monkeypatch.setattr("backend.graph.agents.get_llm", lambda *a, **k: fake)

    result = docs_agent(state)

    assert result["agents_done"] == ["docs"]
    _assert_valid_findings(result["findings"], "docs")
    assert result["findings"][0]["severity"] == "none"


def test_docs_agent_falls_back_to_keyword_heuristics_when_llm_fails(monkeypatch):
    readme = (
        "# Project\n\nA longer description of what this project actually does, "
        "well beyond the bare minimum length used by the fallback heuristic."
    )
    state = _state(_base_repo_data(readme=readme))

    fake = _fake_llm(raise_exc=RuntimeError("no API key"))
    monkeypatch.setattr("backend.graph.agents.get_llm", lambda *a, **k: fake)

    result = docs_agent(state)

    assert result["agents_done"] == ["docs"]
    _assert_valid_findings(result["findings"], "docs")
    # no install/usage/license keywords present -> exactly those three flagged
    evidences = {f["evidence"][0] for f in result["findings"]}
    assert evidences == {"installation", "usage", "license"}
