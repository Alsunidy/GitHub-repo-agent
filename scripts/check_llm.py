"""يتحقق أن مفتاح OpenAI يعمل فعلاً — قبل اتهام الـ graph.

    python scripts/check_llm.py

ينفّذ استدعاءً واحداً بمخرَج منظَّم (نفس الآلية التي يستخدمها المشرف).
نجاحه يعني أن مسار الـ LLM في المشرف سيعمل.
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
    print(f"الموديل : {os.getenv('LLM_MODEL') or DEFAULT_MODEL}")
    print(f"المفتاح : OPENAI_API_KEY = {'موجود' if key else 'غير موجود'}")

    try:
        llm = get_llm(temperature=0).with_structured_output(SupervisorDecision)
    except LLMUnavailable as exc:
        print(f"\n✗ {exc}")
        return 1

    print("\nأرسل استدعاءً تجريبياً بمخرَج منظَّم...")
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
        print(f"✗ فشل الاستدعاء: {type(exc).__name__}: {exc}")
        print("\nالأسباب الشائعة: مفتاح خاطئ، أو رصيد منتهٍ، أو اسم موديل غير متاح "
              "لحسابك (جرّب LLM_MODEL في .env).")
        return 1

    print(f"✓ الرد: next_agent={decision.next_agent!r} reason={decision.reason!r}")
    print("\nالمخرَج المنظَّم يعمل — مسار الـ LLM في المشرف جاهز.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
