"""Tests for backend/tools/osv_tools.py — no network: requests.post is
mocked at the module boundary."""
from unittest.mock import Mock, patch

import requests

from backend.tools.osv_tools import check_vulnerabilities, parse_requirements


def test_parse_requirements_keeps_only_exact_pins():
    text = """
    # comment line, ignored
    flask==0.12.2
    requests>=2.19.0
    django~=2.2
    numpy == 1.26.0
    -e .
    git+https://example.com/pkg.git
    """
    assert parse_requirements(text) == [("flask", "0.12.2"), ("numpy", "1.26.0")]


def test_parse_requirements_supports_extras():
    assert parse_requirements("somepkg[extra]==1.0.0") == [("somepkg", "1.0.0")]


def test_parse_requirements_empty_text():
    assert parse_requirements("") == []


def test_check_vulnerabilities_records_error_instead_of_raising_on_network_failure():
    with patch(
        "backend.tools.osv_tools.requests.post",
        side_effect=requests.exceptions.ConnectionError("boom"),
    ):
        results = check_vulnerabilities("flask==0.12.2\n")

    assert len(results) == 1
    assert results[0]["package"] == "flask"
    assert results[0]["version"] == "0.12.2"
    assert "error" in results[0]
    assert "ConnectionError" in results[0]["error"]


def test_check_vulnerabilities_one_package_failing_does_not_block_the_others():
    def fake_post(url, json, timeout):  # noqa: A002 — matches requests.post's own signature
        if json["package"]["name"] == "flask":
            raise requests.exceptions.Timeout("slow")
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"vulns": []}
        return response

    with patch("backend.tools.osv_tools.requests.post", side_effect=fake_post):
        results = check_vulnerabilities("flask==0.12.2\nrequests==2.19.0\n")

    assert len(results) == 2
    assert "error" in results[0]
    assert results[1] == {
        "package": "requests",
        "version": "2.19.0",
        "vuln_ids": [],
        "total_count": 0,
        "summary": "no known vulnerabilities",
        "fixed_version": None,
    }


def _vuln(vuln_id: str, ranges: list[dict]) -> dict:
    return {"id": vuln_id, "summary": f"summary for {vuln_id}", "affected": [{"ranges": ranges}]}


def _ecosystem_range(*fixed_versions: str) -> dict:
    """An ECOSYSTEM range with one "fixed" event per version given, in
    order — mirrors OSV's real shape (events are chronological)."""
    return {"type": "ECOSYSTEM", "events": [{"introduced": "0"}] + [{"fixed": v} for v in fixed_versions]}


def test_check_vulnerabilities_ignores_git_commit_hashes_in_fixed_version():
    # Real OSV responses report the same fix twice: once as a GIT range
    # (commit hash) and once as an ECOSYSTEM range (package version). Mixing
    # them previously let a commit hash like "eb31d8453..." win a max()
    # comparison against real version numbers -- only ECOSYSTEM must count.
    vulns = [
        _vuln(
            "GHSA-1",
            [
                {"type": "GIT", "events": [{"introduced": "0"}, {"fixed": "eb31d845323618d688ad429479c6dda973056136"}]},
                _ecosystem_range("2.2.1"),
            ],
        )
    ]
    fake_response = Mock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {"vulns": vulns}

    with patch("backend.tools.osv_tools.requests.post", return_value=fake_response):
        result = check_vulnerabilities("django==2.2.0\n")[0]

    assert result["fixed_version"] == "2.2.1"


def test_check_vulnerabilities_fixed_version_is_the_highest_across_all_vulns():
    # Three separate vulnerabilities, three different fix versions -- the
    # package needs the highest one to clear all of them at once, and "1.9"
    # vs "1.10" must compare numerically, not as text.
    vulns = [
        _vuln("GHSA-1", [_ecosystem_range("1.9")]),
        _vuln("GHSA-2", [_ecosystem_range("1.10")]),
        _vuln("GHSA-3", [_ecosystem_range("1.2")]),
    ]
    fake_response = Mock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {"vulns": vulns}

    with patch("backend.tools.osv_tools.requests.post", return_value=fake_response):
        result = check_vulnerabilities("somepkg==1.0\n")[0]

    assert result["fixed_version"] == "1.10"


def test_check_vulnerabilities_fixed_version_none_without_ecosystem_fix_data():
    vulns = [_vuln("GHSA-1", [{"type": "GIT", "events": [{"fixed": "deadbeef"}]}])]
    fake_response = Mock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {"vulns": vulns}

    with patch("backend.tools.osv_tools.requests.post", return_value=fake_response):
        result = check_vulnerabilities("somepkg==1.0\n")[0]

    assert result["fixed_version"] is None


def test_check_vulnerabilities_caps_vuln_ids_and_reports_total_count():
    vulns = [{"id": f"GHSA-{i}", "summary": f"summary {i}"} for i in range(7)]
    fake_response = Mock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {"vulns": vulns}

    with patch("backend.tools.osv_tools.requests.post", return_value=fake_response):
        results = check_vulnerabilities("django==2.2.0\n")

    assert len(results) == 1
    result = results[0]
    assert len(result["vuln_ids"]) == 5
    assert result["total_count"] == 7
    assert result["summary"] == "summary 0"
