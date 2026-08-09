"""OSV.dev tools for the Repo Health Agent.

check_vulnerabilities() never raises: a failure on one package (network
error, bad response, ...) is recorded as an "error" entry in the returned
list instead of aborting the whole scan.
"""
import re

import requests

OSV_API_URL = "https://api.osv.dev/v1/query"
REQUEST_TIMEOUT = 10  # seconds, per package query
ECOSYSTEM = "PyPI"
MAX_VULN_IDS = 5  # cap ids handed to agents; total_count carries the real total

# "package[extra]==1.2.3" — pinned exact versions only, per CONTRACTS.md.
# Other specifiers (>=, ~=, git+, -e, ...) are intentionally ignored.
_PINNED_RE = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?\s*==\s*([A-Za-z0-9][A-Za-z0-9._+-]*)"
)


def parse_requirements(text: str) -> list[tuple[str, str]]:
    """Extract (package, version) pairs from lines pinned with == only."""
    pairs = []
    for raw_line in (text or "").splitlines():
        line = raw_line.split("#", 1)[0].strip()  # drop inline comments
        if not line:
            continue
        match = _PINNED_RE.match(line)
        if match:
            pairs.append((match.group(1), match.group(2)))
    return pairs


def _query_one(package: str, version: str) -> dict:
    resp = requests.post(
        OSV_API_URL,
        json={"package": {"name": package, "ecosystem": ECOSYSTEM}, "version": version},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    vulns = resp.json().get("vulns", [])
    return {
        "package": package,
        "version": version,
        "vuln_ids": [v["id"] for v in vulns[:MAX_VULN_IDS]],
        "total_count": len(vulns),
        "summary": vulns[0].get("summary", "") if vulns else "no known vulnerabilities",
    }


def check_vulnerabilities(requirements_text: str, limit: int = 10) -> list[dict]:
    """Query OSV.dev for each pinned package (up to `limit`).

    Returns a list of {"package", "version", "vuln_ids", "total_count",
    "summary"} on success — vuln_ids capped at MAX_VULN_IDS and summary
    taken from the first vuln only, to keep payloads small for the agents;
    total_count carries the real number found. Failed packages come back as
    {"package", "version", "error"} instead. Never raises.
    """
    results = []
    for package, version in parse_requirements(requirements_text)[:limit]:
        try:
            results.append(_query_one(package, version))
        except Exception as exc:  # noqa: BLE001 — any failure becomes a result, not a crash
            results.append(
                {
                    "package": package,
                    "version": version,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    return results
