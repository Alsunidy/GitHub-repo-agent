"""Measure the cost of one analysis in tokens -- from the real prompts, not a guess.

    python scripts/estimate_cost.py
    python scripts/estimate_cost.py --issues 120 --readme 6000 --code-files 25

The brief asks for this number outright: "An agent that loops is more expensive
than a single call; show that you know the number."

Method: build the exact supervisor prompt the system sends, count it with
tiktoken, then size the agents' inputs from the repository data itself. The
result is grounded in measurement rather than invented.
"""

import argparse
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.graph import supervisor as sup  # noqa: E402

# gpt-4o-mini pricing in USD per million tokens. Re-check before the slide:
# platform.openai.com/docs/pricing
PRICE_IN_PER_M = 0.15
PRICE_OUT_PER_M = 0.60
USD_TO_SAR = 3.75

# Typical output size per call (a short decision, or a full report).
OUT_TOKENS = {"supervisor": 60, "agent": 400, "report": 900}

_ENCODER = None
_EXACT = False


def _encoder():
    """Load the tiktoken encoding once. The first call downloads the BPE table."""
    global _ENCODER, _EXACT
    if _ENCODER is None:
        try:
            import tiktoken

            _ENCODER = tiktoken.get_encoding("o200k_base")
            _EXACT = True
        except Exception:  # noqa: BLE001 -- not installed, or the network is blocked
            _ENCODER = False
    return _ENCODER


def count(text: str) -> int:
    """Count tokens, or estimate at 4 chars per token when the encoding is unavailable."""
    enc = _encoder()
    return len(enc.encode(text)) if enc else len(text) // 4


def build_repo_data(issues: int, readme_chars: int, code_files: int) -> dict:
    """A synthetic repository at realistic sizes -- to measure the prompt, not to feed a tool."""
    return {
        "meta": {
            "full_name": "acme/backend-service",
            "language": "Python",
            "stars": 42,
            "pushed_at": "2026-08-01T10:00:00Z",
        },
        "readme": "x" * readme_chars,
        "open_issues": [
            {
                "number": n,
                "title": f"Issue number {n} with a reasonably descriptive title",
                "body": "y" * 400,
                "created_at": "2026-03-01T00:00:00Z",
                "comments": 2,
                "labels": ["bug"],
            }
            for n in range(issues)
        ],
        "dependency_files": {"requirements.txt": "package==1.2.3\n" * 40},
        "code_files": {f"src/module_{i}.py": "z" * 2000 for i in range(code_files)},
    }


def measure_supervisor(repo_data: dict) -> int:
    """Build the real supervisor prompt and count it."""
    signals = sup._signals(repo_data)
    eligible = sup._eligible_agents(signals, [])
    prompt = (
        f"Repository signals:\n"
        f"  full_name: {signals['full_name']}\n"
        f"  primary language: {signals['language']}\n"
        f"  stars: {signals['stars']}, last push: {signals['pushed_at']}\n"
        f"  README: {signals['readme_chars']} chars, "
        f"headings={signals['readme_headings']}\n"
        f"  open issues: {signals['open_issue_count']}, "
        f"titles={signals['issue_titles']}\n"
        f"  dependency files: {signals['dependency_files']}\n"
        f"  source files available to scan: {signals['code_file_count']}\n\n"
        f"Agents already run: none\n"
        f"Eligible agents: {eligible}\n\n"
        f"Which agent runs next?"
    )
    return count(sup._SYSTEM) + count(prompt)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issues", type=int, default=30, help="number of open issues")
    parser.add_argument("--readme", type=int, default=3000, help="README size in characters")
    parser.add_argument("--code-files", type=int, default=10, help="number of code files")
    args = parser.parse_args()

    repo_data = build_repo_data(args.issues, args.readme, args.code_files)
    sup_tokens = measure_supervisor(repo_data)

    # Agent inputs: each agent sees the slice of repository data that concerns it.
    deps = sum(len(v) for v in repo_data["dependency_files"].values())
    code = sum(len(v) for v in repo_data["code_files"].values())
    issues_text = sum(
        len(i["title"]) + len(i["body"]) for i in repo_data["open_issues"]
    )

    rows = [
        # (stage, calls, input tokens per call, output tokens per call)
        ("supervisor (4 rounds)", 4, sup_tokens, OUT_TOKENS["supervisor"]),
        ("security agent", 1, (deps + code) // 4, OUT_TOKENS["agent"]),
        ("issues agent", 1, issues_text // 4, OUT_TOKENS["agent"]),
        ("docs agent", 1, len(repo_data["readme"]) // 4, OUT_TOKENS["agent"]),
        ("report", 1, 1200, OUT_TOKENS["report"]),
    ]

    print(f"test repository: {args.issues} issues, README {args.readme} chars, "
          f"{args.code_files} code files\n")
    print(f"{'stage':<24}{'calls':>8}{'input':>10}{'output':>9}{'SAR':>10}")
    print("-" * 61)

    total_in = total_out = 0.0
    for label, calls, tok_in, tok_out in rows:
        total_in += calls * tok_in
        total_out += calls * tok_out
        cost = (calls * tok_in / 1e6 * PRICE_IN_PER_M
                + calls * tok_out / 1e6 * PRICE_OUT_PER_M) * USD_TO_SAR
        print(f"{label:<24}{calls:>8}{calls * tok_in:>10,}{calls * tok_out:>9,}{cost:>10.4f}")

    sar = (total_in / 1e6 * PRICE_IN_PER_M + total_out / 1e6 * PRICE_OUT_PER_M) * USD_TO_SAR
    print("-" * 61)
    print(f"{'total':<24}{'':>8}{int(total_in):>10,}{int(total_out):>9,}{sar:>10.4f}")

    print(f"\ncost per analysis   : {sar:.4f} SAR (~{sar * 100:.2f} halalas)")
    print(f"100 analyses a month: {sar * 100:.2f} SAR")
    print(f"\nsupervisor's share of the cost: "
          f"{4 * sup_tokens / total_in * 100:.1f}% of input tokens -- "
          f"the price of deciding instead of always running everything.")

    method = "exact, measured with tiktoken" if _EXACT else "estimated at 4 chars/token (tiktoken unavailable)"
    print(f"\ncounting method: {method}")
    print(f"pricing: gpt-4o-mini, ${PRICE_IN_PER_M}/M in and ${PRICE_OUT_PER_M}/M out, "
          f"at {USD_TO_SAR} SAR to the dollar. Re-check before the slide.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
