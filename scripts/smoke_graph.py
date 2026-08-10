"""Run the real graph from the command line -- proof that the conditional
edges and the approval pause work, without a server or a UI.

    python scripts/smoke_graph.py
        The refusal scenarios only. No network, no API key, nothing written:
        the guardrail stops every one of them before a single call goes out.

    python scripts/smoke_graph.py https://github.com/owner/repo [--lang ar]
        A full review of a real repository. Stops at the approval pause and
        declines on your behalf, so nothing is written to GitHub.

    python scripts/smoke_graph.py https://github.com/owner/repo --approve
        The same, but approves -- which OPENS A REAL ISSUE on that repository.

╔══════════════════════════════════════════════════════════════════════════╗
║  --approve writes to a repository that belongs to someone. Only ever      ║
║  point it at one you own. This script used to approve by default against  ║
║  a well-known public repo, and duly opened an issue on a stranger's       ║
║  project; hence the flag, and hence the confirmation prompt behind it.    ║
╚══════════════════════════════════════════════════════════════════════════╝

The formal test suite is `pytest tests/` -- this script is the manual,
end-to-end counterpart to it.
"""

import argparse
import sys
import uuid
from pathlib import Path

# On Windows stdout is written in the system code page when redirected to a
# file, which breaks on non-ASCII. Pin UTF-8 before the first print -- the
# execution proof is saved by redirecting this output.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.graph.build import build_graph  # noqa: E402
from backend.state import initial_state  # noqa: E402

# Every one of these is stopped by the guardrail, before any network call.
REFUSAL_SCENARIOS = [
    ("URL is not a repository", "https://github.com/settings/profile", "en"),
    ("not a GitHub URL at all", "delete all my files please", "ar"),
    ("nothing entered", "", "ar"),
    # This one does reach the network: the repository genuinely does not exist,
    # which is the fetch node's failure path (read-only, nothing is written).
    ("repository does not exist", "https://github.com/Alsunidy/no-such-repo-xyz", "en"),
]


def run(label: str, url: str, language: str, approve: bool) -> bool:
    graph = build_graph()
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    print(f"\n{'=' * 72}\n> {label}\n  url={url!r} language={language!r}\n{'-' * 72}")

    state = graph.invoke(initial_state(url, language), config)

    for line in state.get("supervisor_log", []):
        print(f"   - {line}")

    paused_at = graph.get_state(config).next
    print(f"\n   agents_done : {state.get('agents_done', [])}")
    print(f"   findings    : {len(state.get('findings', []))}")
    print(f"   rejected    : {bool(state.get('rejection_reason'))}")
    print(f"   paused at   : {paused_at or '-- (finished without pausing)'}")

    if not paused_at:  # a refusal or a fetch failure: no approval, no publish
        ok = bool(state.get("rejection_reason")) and state.get("issue_url") is None
        print(f"   report      : {state.get('report', '')[:90]}")
        return ok

    print(f"\n{state.get('report', '')}")

    # The human decision -- the whole point of the pause.
    if approve and not _confirm_write(state):
        approve = False

    graph.update_state(config, {"approved": approve})
    final = graph.invoke(None, config)

    print(f"   approved    : {approve}")
    print(f"   issue_url   : {final.get('issue_url')}")
    for line in final.get("supervisor_log", [])[len(state.get("supervisor_log", [])):]:
        print(f"   - {line}")

    return (final.get("issue_url") is not None) if approve else (final.get("issue_url") is None)


def _confirm_write(state: dict) -> bool:
    """--approve is not enough on its own: name the target and ask out loud."""
    target = f"{state.get('owner')}/{state.get('repo')}"
    print(f"\n   ** This will open a REAL issue on {target}. **")
    answer = input(f"   Type the repository name ({target}) to confirm: ").strip()
    if answer == target:
        return True
    print("   Not confirmed -- declining the publish instead.")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_url", nargs="?", help="a real repository to review")
    parser.add_argument("--lang", default="en", choices=("en", "ar"))
    parser.add_argument(
        "--approve",
        action="store_true",
        help="approve the publish -- opens a real issue on the repository",
    )
    args = parser.parse_args()

    results = [(label, run(label, url, lang, approve=False))
               for label, url, lang in REFUSAL_SCENARIOS]

    if args.repo_url:
        results.append(
            ("full review of a real repository",
             run("full review of a real repository", args.repo_url, args.lang, args.approve))
        )

    print(f"\n{'=' * 72}\nSummary")
    for label, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")

    failed = [label for label, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
