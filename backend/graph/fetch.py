"""node الجلب — يملأ repo_data مرة واحدة، ويغطّي مسار الفشل الذي يطلبه البريف.

مساران للفشل هنا:
  1. RepoNotFound — المستودع غير موجود أو خاص (خطأ متوقَّع، رسالة مؤدبة).
  2. أي استثناء آخر — شبكة، حد استعلامات، رد غير متوقَّع. لا نُسقط النظام
     ولا نخترع بيانات: نوقف المسار ونشرح للمستخدم.
"""

# ── مؤقت: يُحذف عند نقطة الالتقاء الأولى (انظر backend/stubs.py) ──
try:
    from backend.tools.github_tools import RepoNotFound, fetch_repo_data
except ImportError:  # pragma: no cover
    from backend.stubs import RepoNotFound, fetch_repo_data
# ──────────────────────────────────────────────────────────────────

from backend.state import AgentState

_MESSAGES = {
    "not_found": {
        "en": "I could not reach `{full_name}`. The repository does not exist, "
              "or it is private and this token cannot see it. Please check the "
              "URL and try again.",
        "ar": "لم أتمكّن من الوصول إلى `{full_name}`. المستودع غير موجود، أو "
              "أنه خاص ولا يستطيع هذا المفتاح رؤيته. تأكّد من الرابط وحاول مرة أخرى.",
    },
    "tool_error": {
        "en": "I reached GitHub but the request failed: {error}. This is a "
              "temporary problem on my side, not a finding about the repository. "
              "Please try again in a moment.",
        "ar": "وصلت إلى GitHub لكن الطلب فشل: {error}. هذه مشكلة مؤقتة عندي، "
              "وليست ملاحظة على المستودع. حاول مرة أخرى بعد قليل.",
    },
    "empty": {
        "en": "`{full_name}` exists but returned no readable content — no README, "
              "no dependency files, and no source files I can inspect. There is "
              "nothing for me to analyse.",
        "ar": "`{full_name}` موجود لكنه لم يُرجع أي محتوى قابل للقراءة — لا README، "
              "ولا ملفات تبعيات، ولا ملفات مصدرية أستطيع فحصها. لا يوجد ما أحلّله.",
    },
}


def fetch_node(state: AgentState) -> dict:
    """يستدعي أداة GitHub الحقيقية ويضع النتيجة في الـ State."""
    owner, repo = state["owner"], state["repo"]
    language = state.get("language", "en")
    full_name = f"{owner}/{repo}"

    try:
        repo_data = fetch_repo_data(owner, repo)
    except RepoNotFound:
        return _fail("not_found", language, full_name=full_name)
    except Exception as exc:  # noqa: BLE001 — أي عطل في الأداة يُترجم لرسالة مفهومة
        return _fail("tool_error", language, error=f"{type(exc).__name__}: {exc}")

    if not _has_analysable_content(repo_data):
        return _fail("empty", language, full_name=full_name)

    meta = repo_data.get("meta", {})
    return {
        "repo_data": repo_data,
        "supervisor_log": [
            f"fetch: {full_name} — "
            f"{len(repo_data.get('open_issues', []))} open issues, "
            f"{len(repo_data.get('dependency_files', {}))} dependency files, "
            f"{len(repo_data.get('code_files', {}))} code files, "
            f"readme {len(repo_data.get('readme', ''))} chars, "
            f"language={meta.get('language')}"
        ],
    }


def _has_analysable_content(repo_data: dict) -> bool:
    """الأداة قد تنجح وترجع لا شيء — هذه أيضاً حالة فشل يجب التعامل معها."""
    if not repo_data:
        return False
    return any(
        (
            repo_data.get("readme"),
            repo_data.get("open_issues"),
            repo_data.get("dependency_files"),
            repo_data.get("code_files"),
        )
    )


def _fail(reason_key: str, language: str, **fmt) -> dict:
    text = _MESSAGES[reason_key][language if language in ("en", "ar") else "en"].format(**fmt)
    return {
        "rejection_reason": text,
        "report": text,
        "next_agent": "done",
        "supervisor_log": [f"fetch: failed ({reason_key})"],
    }


def route_after_fetch(state: AgentState) -> str:
    """المسار الشرطي الثاني: فشل الجلب يوقف كل شيء، والنجاح يسلّم للمشرف."""
    return "failed" if state.get("rejection_reason") else "supervisor"
