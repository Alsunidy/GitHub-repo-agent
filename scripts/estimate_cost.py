"""يقيس تكلفة التحليل الواحد بالتوكِنات — من الـ prompts الفعلية، لا بالتخمين.

    python scripts/estimate_cost.py
    python scripts/estimate_cost.py --issues 120 --readme 6000 --code-files 25

البريف يطلب صراحةً معرفة الرقم: "An agent that loops is more expensive than a
single call; show that you know the number."

الطريقة: نبني نفس نص prompt المشرف الذي يُرسل فعلاً، ونعدّه بـ tiktoken، ثم
نقدّر أحجام مدخلات الوكلاء من حجم بيانات المستودع نفسها. المخرَج تقدير أرضيته
قياس، وليس رقماً مخترعاً.
"""

import argparse
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.graph import supervisor as sup  # noqa: E402

# أسعار gpt-4o-mini بالدولار لكل مليون توكِن. راجعها قبل وضعها في السلايد:
# platform.openai.com/docs/pricing
PRICE_IN_PER_M = 0.15
PRICE_OUT_PER_M = 0.60
USD_TO_SAR = 3.75

# متوسط ما يُخرجه كل استدعاء (قرار قصير، أو تقرير كامل).
OUT_TOKENS = {"supervisor": 60, "agent": 400, "report": 900}


_ENCODER = None
_EXACT = False


def _encoder():
    """يحمّل ترميز tiktoken مرة واحدة. أول استدعاء ينزّل جدول BPE من الشبكة."""
    global _ENCODER, _EXACT
    if _ENCODER is None:
        try:
            import tiktoken

            _ENCODER = tiktoken.get_encoding("o200k_base")
            _EXACT = True
        except Exception:  # noqa: BLE001 — غير مثبّت، أو الشبكة محجوبة
            _ENCODER = False
    return _ENCODER


def count(text: str) -> int:
    """عدّ التوكِنات، أو تقدير 4 محارف/توكِن لو تعذّر تحميل الترميز."""
    enc = _encoder()
    return len(enc.encode(text)) if enc else len(text) // 4


def build_repo_data(issues: int, readme_chars: int, code_files: int) -> dict:
    """مستودع اصطناعي بأحجام واقعية — لقياس الـ prompt، لا لتغذية أداة."""
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
    """يبني نص prompt المشرف الحقيقي ويعدّه."""
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
    parser.add_argument("--issues", type=int, default=30, help="عدد البلاغات المفتوحة")
    parser.add_argument("--readme", type=int, default=3000, help="حجم README بالمحارف")
    parser.add_argument("--code-files", type=int, default=10, help="عدد ملفات الكود")
    args = parser.parse_args()

    repo_data = build_repo_data(args.issues, args.readme, args.code_files)
    sup_tokens = measure_supervisor(repo_data)

    # مدخلات الوكلاء: كل وكيل يرى الجزء الذي يخصه من بيانات المستودع.
    deps = sum(len(v) for v in repo_data["dependency_files"].values())
    code = sum(len(v) for v in repo_data["code_files"].values())
    issues_text = sum(
        len(i["title"]) + len(i["body"]) for i in repo_data["open_issues"]
    )

    rows = [
        # (المرحلة، عدد الاستدعاءات، توكِنات الدخل لكل استدعاء، توكِنات الخرج)
        ("المشرف (4 دورات)", 4, sup_tokens, OUT_TOKENS["supervisor"]),
        ("وكيل الأمن", 1, (deps + code) // 4, OUT_TOKENS["agent"]),
        ("وكيل البلاغات", 1, issues_text // 4, OUT_TOKENS["agent"]),
        ("وكيل التوثيق", 1, len(repo_data["readme"]) // 4, OUT_TOKENS["agent"]),
        ("التقرير", 1, 1200, OUT_TOKENS["report"]),
    ]

    print(f"مستودع الاختبار: {args.issues} بلاغاً، README {args.readme} محرفاً، "
          f"{args.code_files} ملف كود\n")
    print(f"{'المرحلة':<22}{'استدعاءات':>10}{'دخل':>10}{'خرج':>9}{'ريال':>10}")
    print("-" * 61)

    total_in = total_out = 0.0
    for label, calls, tok_in, tok_out in rows:
        total_in += calls * tok_in
        total_out += calls * tok_out
        cost = (calls * tok_in / 1e6 * PRICE_IN_PER_M
                + calls * tok_out / 1e6 * PRICE_OUT_PER_M) * USD_TO_SAR
        print(f"{label:<22}{calls:>10}{calls * tok_in:>10,}{calls * tok_out:>9,}{cost:>10.4f}")

    sar = (total_in / 1e6 * PRICE_IN_PER_M + total_out / 1e6 * PRICE_OUT_PER_M) * USD_TO_SAR
    print("-" * 61)
    print(f"{'الإجمالي':<22}{'':>10}{int(total_in):>10,}{int(total_out):>9,}{sar:>10.4f}")

    print(f"\nتكلفة التحليل الواحد: {sar:.4f} ريال (~{sar * 100:.2f} هللة)")
    print(f"مئة تحليل شهرياً    : {sar * 100:.2f} ريال")
    print(f"\nحصة المشرف من التكلفة: "
          f"{4 * sup_tokens / total_in * 100:.1f}% من توكِنات الدخل — "
          f"ثمن اتخاذ القرار بدل تشغيل كل شيء دائماً.")
    method = "قياس دقيق بـ tiktoken" if _EXACT else "تقدير 4 محارف/توكِن (tiktoken غير متاح)"
    print(f"\nطريقة العدّ: {method}")
    print(f"التسعير: gpt-4o-mini، ${PRICE_IN_PER_M}/M دخل و ${PRICE_OUT_PER_M}/M خرج، "
          f"بسعر صرف {USD_TO_SAR}. راجع الأسعار قبل السلايد.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
