"""يتحقق أن مفتاح الـ LLM يعمل فعلاً — قبل اتهام الـ graph.

    python scripts/check_llm.py

يطبع المزوّد والموديل، ثم ينفّذ استدعاءً واحداً بمخرَج منظَّم (نفس الآلية التي
يستخدمها المشرف). نجاحه يعني أن مسار الـ LLM في المشرف سيعمل.
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import os  # noqa: E402

from backend.graph.supervisor import SupervisorDecision  # noqa: E402
from backend.llm import _KEY_VARS, _MODELS, LLMUnavailable, get_llm  # noqa: E402

# بادئات المفاتيح — أكثر خطأ شائع هو مفتاح من مزوّد موجَّه لخادم مزوّد آخر.
_PREFIXES = {"sk-or-v1": "openrouter", "sk-ant-": "anthropic"}


def main() -> int:
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    key_var = _KEY_VARS.get(provider, "?")
    key = os.getenv(key_var, "")

    print(f"المزوّد : {provider}")
    print(f"الموديل : {os.getenv('LLM_MODEL') or _MODELS.get(provider, '?')}")
    print(f"المفتاح : {key_var} = {'موجود' if key else 'غير موجود'}")

    for prefix, owner in _PREFIXES.items():
        if key.startswith(prefix) and owner != provider:
            print(f"\n✗ المفتاح يبدأ بـ {prefix} ⇒ هذا مفتاح {owner}، "
                  f"لكن LLM_PROVIDER={provider}.")
            print(f"   الحل: اضبط LLM_PROVIDER={owner} في .env، أو استخدم مفتاح {provider}.")
            return 1

    try:
        llm = get_llm(temperature=0).with_structured_output(SupervisorDecision)
    except LLMUnavailable as exc:
        print(f"\n✗ لم يُبنَ الـ LLM: {exc}")
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
