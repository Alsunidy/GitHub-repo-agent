"""Manual smoke test for github_tools.py and osv_tools.py — not part of the
automated test suite.

Exercises parse_repo_url() and fetch_repo_data() against a real public repo,
then feeds the fetched requirements.txt into check_vulnerabilities() to hit
OSV.dev for real. Run from the repo root:

    python scripts/try_github_tools.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()

from backend.tools.github_tools import fetch_repo_data, parse_repo_url  # noqa: E402
from backend.tools.osv_tools import check_vulnerabilities  # noqa: E402
from backend.tools.secret_tools import scan_secrets  # noqa: E402

REPO_URL = "https://github.com/sl-rwl/test_1"
FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "fake_secrets_sample.py")


def _print_secret_findings(findings):
    if not findings:
        print("(no secrets detected)")
        return
    for item in findings:
        print(f"{item['file']}:{item['line']} [{item['kind']}] {item['snippet']}")


def main():
    parsed = parse_repo_url(REPO_URL)
    print(f"parse_repo_url({REPO_URL!r}) -> {parsed}")
    if parsed is None:
        print("Could not parse repo URL, stopping.")
        return

    owner, repo = parsed
    data = fetch_repo_data(owner, repo)

    meta = data["meta"]
    dep_files_present = [name for name, content in data["dependency_files"].items() if content]

    print("--- repo_data summary ---")
    print(f"full_name: {meta['full_name']}")
    print(f"open_issues: {len(data['open_issues'])}")
    print(f"readme length: {len(data['readme'])} chars")
    print(f"dependency files found: {dep_files_present or 'none'}")
    print(f"code_files fetched: {len(data['code_files'])} -> {list(data['code_files'])[:5]}")

    requirements_text = data["dependency_files"].get("requirements.txt")
    print("\n--- check_vulnerabilities(requirements.txt) via OSV.dev ---")
    if not requirements_text:
        print("(no requirements.txt in this repo, skipping)")
    else:
        for item in check_vulnerabilities(requirements_text):
            if "error" in item:
                print(f"{item['package']}=={item['version']}: ERROR — {item['error']}")
            elif item["vuln_ids"]:
                shown = ", ".join(item["vuln_ids"])
                more = (
                    f" (+{item['total_count'] - len(item['vuln_ids'])} more)"
                    if item["total_count"] > len(item["vuln_ids"])
                    else ""
                )
                print(f"{item['package']}=={item['version']}: {shown}{more} — {item['summary']}")
            else:
                print(f"{item['package']}=={item['version']}: no known vulnerabilities")

    print(f"\n--- scan_secrets() on code_files fetched from {meta['full_name']} ---")
    _print_secret_findings(scan_secrets(data["code_files"]))

    # app.py in test_1 likely has no real secrets, so this local fixture with
    # known fake secrets proves the scanner actually detects something.
    print(f"\n--- scan_secrets() on local fixture ({FIXTURE_PATH}) ---")
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        fixture_content = f.read()
    _print_secret_findings(scan_secrets({FIXTURE_PATH: fixture_content}))


if __name__ == "__main__":
    main()
