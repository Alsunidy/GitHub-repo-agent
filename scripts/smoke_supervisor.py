"""فحص منطق المشرف وحده — الأهلية، وتصحيح قرارات الـ LLM الخاطئة.

    python scripts/smoke_supervisor.py

لا يحتاج مفتاح LLM: نحقن قرارات وهمية مكان _ask_llm لنتحقق من أن الكود
لا يثق بمخرَج النموذج في التوجيه.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.graph import supervisor as sup  # noqa: E402
from backend.state import initial_state  # noqa: E402

RICH = {
    "meta": {"full_name": "o/r", "language": "Python", "stars": 5, "pushed_at": "2026-07-01"},
    "readme": "# R\n## Install\n",
    "open_issues": [{"title": "bug"}],
    "dependency_files": {"requirements.txt": "flask==0.12.2"},
    "code_files": {"a.py": "x = 1"},
}
NO_DEPS_NO_CODE = {**RICH, "dependency_files": {}, "code_files": {}}
NO_ISSUES = {**RICH, "open_issues": []}


def _state(repo_data: dict, done: list[str], log: list[str] | None = None) -> dict:
    state = initial_state("https://github.com/o/r", "en")
    state["repo_data"] = repo_data
    state["agents_done"] = done
    state["supervisor_log"] = log or []
    return state


def _run(repo_data, done, fake=None, log=None) -> str:
    """يشغّل المشرف مع قرار LLM وهمي (أو بلا LLM إذا fake=None)."""
    original = sup._ask_llm
    sup._ask_llm = fake or original
    try:
        return sup.supervisor_node(_state(repo_data, done, log))["next_agent"]
    finally:
        sup._ask_llm = original


CASES = [
    # (الوصف، المتوقَّع، الفعلي)
    (
        "الأهلية: بلا تبعيات ولا كود ⇒ وكيل الأمن غير مؤهَّل",
        ["issues", "docs"],
        sup._eligible_agents(sup._signals(NO_DEPS_NO_CODE), []),
    ),
    (
        "الأهلية: بلا بلاغات مفتوحة ⇒ وكيل البلاغات غير مؤهَّل",
        ["security", "docs"],
        sup._eligible_agents(sup._signals(NO_ISSUES), []),
    ),
    (
        "الأهلية: المنفَّذ لا يُعاد",
        ["docs"],
        sup._eligible_agents(sup._signals(RICH), ["security", "issues"]),
    ),
    (
        "بلا LLM ⇒ سقوط حتمي على الأخطر أولاً",
        "security",
        _run(RICH, []),
    ),
    (
        "قرار LLM سليم يُحترم",
        "docs",
        _run(RICH, [], fake=lambda *a: ("docs", "readme is empty")),
    ),
    (
        "قرار LLM لوكيل منفَّذ مسبقاً ⇒ يُصحَّح",
        "issues",
        _run(RICH, ["security"], fake=lambda *a: ("security", "loop me")),
    ),
    (
        "قرار LLM لوكيل غير مؤهَّل ⇒ يُصحَّح",
        "issues",
        _run(NO_DEPS_NO_CODE, [], fake=lambda *a: ("security", "nothing to scan")),
    ),
    (
        "LLM يوقف قبل عمل أي وكيل ⇒ يُرفض، تقرير فارغ ممنوع",
        "security",
        _run(RICH, [], fake=lambda *a: ("done", "looks fine")),
    ),
    (
        "LLM يوقف بعد عمل وكيل ⇒ يُحترم",
        "done",
        _run(RICH, ["security"], fake=lambda *a: ("done", "enough for this repo")),
    ),
    (
        "كل الوكلاء انتهوا ⇒ done",
        "done",
        _run(RICH, ["security", "issues", "docs"]),
    ),
    (
        "حزام الأمان: دورات كثيرة ⇒ إنهاء قسري",
        "done",
        _run(RICH, [], log=["supervisor: x"] * sup._MAX_ROUNDS),
    ),
]


def main() -> int:
    failed = 0
    for label, expected, actual in CASES:
        ok = expected == actual
        failed += not ok
        print(f"  {'✓' if ok else '✗'}  {label}")
        if not ok:
            print(f"      المتوقَّع: {expected!r}\n      الفعلي  : {actual!r}")

    print(f"\n{len(CASES) - failed}/{len(CASES)} نجحت")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
