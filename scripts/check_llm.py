"""Verify the OpenAI key actually works -- before blaming the graph.

    python scripts/check_llm.py

Makes one structured-output call, the same mechanism the supervisor uses.
If this passes, the supervisor's LLM path will work.
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import os  # noqa: E402

from backend.graph.supervisor import SupervisorDecision  # noqa: E402
from backend.llm import DEFAULT_MODEL, LLMUnavailable, get_llm  # noqa: E402


def main() -> int:
    key = os.getenv("OPENAI_API_KEY", "")
    print(f"model : {os.getenv('LLM_MODEL') or DEFAULT_MODEL}")
    print(f"key   : OPENAI_API_KEY = {'set' if key else 'not set'}")

    try:
        llm = get_llm(temperature=0).with_structured_output(SupervisorDecision)
    except LLMUnavailable as exc:
        print(f"\nFAIL: {exc}")
        return 1

    print("\nSending one structured-output call...")
    try:
        decision = llm.invoke(
            [
                {"role": "system", "content": "You route work to agents."},
                {"role": "user", "content":
                    "A repository has no README at all. Eligible agents: ['docs']. "
                    "Which agent runs next?"},
            ]
        )
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: call failed: {type(exc).__name__}: {exc}")
        print("\nUsual causes: wrong key, exhausted credit, or a model name your "
              "account cannot access (try LLM_MODEL in .env).")
        return 1

    print(f"PASS: next_agent={decision.next_agent!r} reason={decision.reason!r}")
    print("\nStructured output works -- the supervisor's LLM path is ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
