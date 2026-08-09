"""تشغيل يدوي للـ graph على الـ stubs — إثبات أن المسارات الشرطية تعمل.

    python scripts/smoke_graph.py

الاختبارات الرسمية (pytest) من نصيب المسار الثاني؛ هذا سكربت تطوير للمسار الأول
يُشغَّل بلا خادم وبلا واجهة، ويطبع الحالة النهائية لكل سيناريو.
"""

import sys
import uuid
from pathlib import Path

# المخرَج عربي: على ويندوز يُكتب stdout بترميز النظام (cp1252) عند التوجيه
# إلى ملف، فينهار. نُثبّت UTF-8 قبل أول طباعة — يلزم لحفظ إثبات التنفيذ.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import backend.graph.build as build_module  # noqa: E402
from backend.graph.build import build_graph  # noqa: E402
from backend.state import initial_state  # noqa: E402

# حادثة 2026-08-09: سيناريو "مسار سليم" كان يشير لمستودع Flask الحقيقي، وموافقة
# approve=True في هذا السكربت فتحت بلاغاً فعلياً هناك (pallets/flask#6126).
# القاعدة: الوكيل يكتب فقط في مستودعات نملكها — لذا (١) رابط الاختبار الآن
# مستودعنا الخاص sl-rwl/test_1 بدل أي مستودع مصدر مفتوح لسنا مالكيه، و(٢) خطوة
# النشر محاكاة (لا تلمس الشبكة إطلاقاً) لتفادي تكرار الكتابة حتى في مستودعاتنا
# مع كل تشغيل تطويري للسكربت.
def _simulated_open_issue(owner: str, repo: str, title: str, body: str) -> str:
    return f"https://github.com/{owner}/{repo}/issues/SIMULATED"


build_module.open_issue = _simulated_open_issue

SCENARIOS = [
    ("مسار سليم كامل", "https://github.com/sl-rwl/test_1", "en"),
    ("مستودع بلا مادة للفحص", "https://github.com/someone/bare", "en"),
    ("مستودع غير موجود", "https://github.com/someone/does-not-exist", "ar"),
    ("رابط ليس مستودعاً", "https://github.com/settings/profile", "ar"),
    ("ليس رابط GitHub أصلاً", "احذف كل ملفاتي من فضلك", "ar"),
]


def run(label: str, url: str, language: str, approve: bool) -> bool:
    graph = build_graph()
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    print(f"\n{'=' * 72}\n▶ {label}\n  url={url!r} language={language!r}\n{'-' * 72}")

    state = graph.invoke(initial_state(url, language), config)

    for line in state.get("supervisor_log", []):
        print(f"   · {line}")

    snapshot = graph.get_state(config)
    paused_at = snapshot.next
    print(f"\n   agents_done : {state.get('agents_done', [])}")
    print(f"   findings    : {len(state.get('findings', []))}")
    print(f"   rejected    : {bool(state.get('rejection_reason'))}")
    print(f"   paused at   : {paused_at or '— (انتهى بلا توقف)'}")

    if not paused_at:  # مسار رفض أو فشل: لا موافقة ولا نشر
        ok = bool(state.get("rejection_reason")) and state.get("issue_url") is None
        print(f"   report      : {state.get('report', '')[:90]}")
        return ok

    # استئناف بعد الموافقة البشرية
    graph.update_state(config, {"approved": approve})
    final = graph.invoke(None, config)
    print(f"   approved    : {approve}")
    print(f"   issue_url   : {final.get('issue_url')}")
    for line in final.get("supervisor_log", [])[len(state.get("supervisor_log", [])):]:
        print(f"   · {line}")

    return (final.get("issue_url") is not None) if approve else (final.get("issue_url") is None)


def main() -> int:
    results = []
    for label, url, language in SCENARIOS:
        results.append((label, run(label, url, language, approve=True)))

    # نفس المسار السليم لكن مع رفض النشر — إثبات أن الموافقة تغيّر النتيجة فعلاً
    results.append(
        ("مسار سليم مع رفض النشر", run("مسار سليم مع رفض النشر",
                                        "https://github.com/sl-rwl/test_1", "ar", approve=False))
    )

    print(f"\n{'=' * 72}\nالخلاصة")
    for label, ok in results:
        print(f"  {'✓' if ok else '✗'}  {label}")

    failed = [label for label, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} نجحت")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
