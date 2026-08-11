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

# Splits a version string into (digit, text) tokens so components compare as
# numbers ("9" < "10") instead of as text ("10" < "9"). Not a real PEP 440
# parser -- pre-release suffixes like "rc1" just sort as trailing text, which
# is good enough to pick the highest of a handful of "fixed" versions OSV
# reports without adding a dependency for it.
_VERSION_TOKEN_RE = re.compile(r"\d+|\D+")

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


def _version_key(version: str) -> tuple:
    """Sort key for a version string -- see _VERSION_TOKEN_RE. The (0, ...)
    / (1, ...) tag keeps a digit token and a text token comparable (Python
    can't compare int to str directly) while still sorting digits by value."""
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part.lower())
        for part in _VERSION_TOKEN_RE.findall(version)
    )


def _fixed_versions(vuln: dict) -> list[str]:
    """The version(s) marked "fixed" in this vulnerability's affected
    ranges, PyPI version numbers only.

    OSV reports the same fix through several range *types* at once -- a
    "GIT" range marks it by commit hash, an "ECOSYSTEM" range marks it by
    the package's own version number. Mixing them would compare a commit
    hash against a version string, which is meaningless (and briefly did:
    "eb31d8453..." sorted as "higher" than every real Django release). Only
    ECOSYSTEM matches our query's ecosystem (PyPI), so it's the only type
    that means anything here.

    A vulnerability can also carry several ECOSYSTEM ranges (e.g. one per
    release branch that got a backport); within a single range OSV lists
    events chronologically, so the LAST "fixed" event in that range is the
    most recent fix for it."""
    versions = []
    for affected in vuln.get("affected", []) or []:
        for value_range in affected.get("ranges", []) or []:
            if value_range.get("type") != "ECOSYSTEM":
                continue
            fixed = None
            for event in value_range.get("events", []) or []:
                if event.get("fixed"):
                    fixed = event["fixed"]
            if fixed:
                versions.append(fixed)
    return versions


def _highest_fixed_version(vulns: list[dict]) -> str | None:
    """The highest "fixed" version across every vulnerability OSV returned
    for this package -- the version that clears all of them at once."""
    all_fixed = [v for vuln in vulns for v in _fixed_versions(vuln)]
    return max(all_fixed, key=_version_key) if all_fixed else None


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
        "fixed_version": _highest_fixed_version(vulns),
    }


def check_vulnerabilities(requirements_text: str, limit: int = 10) -> list[dict]:
    """Query OSV.dev for each pinned package (up to `limit`).

    Returns a list of {"package", "version", "vuln_ids", "total_count",
    "summary", "fixed_version"} on success — vuln_ids capped at MAX_VULN_IDS
    and summary taken from the first vuln only, to keep payloads small for
    the agents; total_count carries the real number found. fixed_version is
    the highest version marked "fixed" across every vulnerability found (see
    _highest_fixed_version), or None if OSV gave no fix information at all.
    Failed packages come back as {"package", "version", "error"} instead.
    Never raises.
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
