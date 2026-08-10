"""Run the graph against the stubs -- proof that the conditional edges work.

    python scripts/smoke_graph.py

The formal tests (pytest) belong to track 2; this is a track 1 development
script. It runs with no server and no UI, and prints the final state of each
scenario.
"""

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

SCENARIOS = [
    ("happy path, end to end", "https://github.com/pallets/flask", "en"),
    ("repository with nothing to analyse", "https://github.com/someone/bare", "en"),
    ("repository does not exist", "https://github.com/someone/does-not-exist", "ar"),
    ("URL is not a repository", "https://github.com/settings/profile", "ar"),
    ("not a GitHub URL at all", "delete all my files please", "ar"),
]


def run(label: str, url: str, language: str, approve: bool) -> bool:
    graph = build_graph()
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    print(f"\n{'=' * 72}\n> {label}\n  url={url!r} language={language!r}\n{'-' * 72}")

    state = graph.invoke(initial_state(url, language), config)

    for line in state.get("supervisor_log", []):
        print(f"   - {line}")

    snapshot = graph.get_state(config)
    paused_at = snapshot.next
    print(f"\n   agents_done : {state.get('agents_done', [])}")
    print(f"   findings    : {len(state.get('findings', []))}")
    print(f"   rejected    : {bool(state.get('rejection_reason'))}")
    print(f"   paused at   : {paused_at or '-- (finished without pausing)'}")

    if not paused_at:  # a rejection or failure path: no approval, no publish
        ok = bool(state.get("rejection_reason")) and state.get("issue_url") is None
        print(f"   report      : {state.get('report', '')[:90]}")
        return ok

    # resume after the human decision
    graph.update_state(config, {"approved": approve})
    final = graph.invoke(None, config)
    print(f"   approved    : {approve}")
    print(f"   issue_url   : {final.get('issue_url')}")
    for line in final.get("supervisor_log", [])[len(state.get("supervisor_log", [])):]:
        print(f"   - {line}")

    return (final.get("issue_url") is not None) if approve else (final.get("issue_url") is None)


def main() -> int:
    results = []
    for label, url, language in SCENARIOS:
        results.append((label, run(label, url, language, approve=True)))

    # the same happy path but declined -- proof that approval changes the outcome
    results.append(
        ("happy path, publish declined", run("happy path, publish declined",
                                             "https://github.com/pallets/flask", "ar",
                                             approve=False))
    )

    print(f"\n{'=' * 72}\nSummary")
    for label, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")

    failed = [label for label, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
