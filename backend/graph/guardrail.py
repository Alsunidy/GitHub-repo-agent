"""node الحارس — البوابة الأولى: لا شيء يمر بلا رابط مستودع GitHub صالح.

يمنع ثلاث حالات: المدخل الفارغ، وما ليس رابطاً أصلاً، والرابط الذي يشير
إلى GitHub لكنه ليس مستودعاً (ملف شخصي، بحث، صفحة إعدادات...).
"""

# ── مؤقت: يُحذف عند نقطة الالتقاء الأولى (انظر backend/stubs.py) ──
try:
    from backend.tools.github_tools import parse_repo_url
except ImportError:  # pragma: no cover
    from backend.stubs import parse_repo_url
# ──────────────────────────────────────────────────────────────────

from backend.state import AgentState

# مسارات على github.com ليست مستودعات — تُرفض ولو طابقت شكل owner/repo
_RESERVED_OWNERS = {
    "settings", "notifications", "explore", "marketplace", "pricing",
    "search", "login", "join", "about", "features", "sponsors",
    "orgs", "topics", "trending", "collections", "events", "new",
}

_MESSAGES = {
    "empty": {
        "en": "Please enter a GitHub repository URL, for example: "
              "`https://github.com/pallets/flask`",
        "ar": "الرجاء إدخال رابط مستودع GitHub، مثل: "
              "`https://github.com/pallets/flask`",
    },
    "not_a_repo": {
        "en": "That does not look like a GitHub repository URL. I analyse "
              "repositories only, in the form `https://github.com/owner/repo`. "
              "I cannot analyse user profiles, search pages, or other sites.",
        "ar": "هذا لا يبدو رابط مستودع GitHub. أنا أحلّل المستودعات فقط، "
              "بالشكل `https://github.com/owner/repo`. لا أستطيع تحليل الملفات "
              "الشخصية أو صفحات البحث أو المواقع الأخرى.",
    },
}


def guardrail_node(state: AgentState) -> dict:
    """يملأ owner/repo، أو يملأ rejection_reason ويوقف المسار بأدب."""
    language = state.get("language", "en")
    raw_url = (state.get("repo_url") or "").strip()

    if not raw_url:
        return _reject("empty", language)

    parsed = parse_repo_url(raw_url)
    if parsed is None:
        return _reject("not_a_repo", language)

    owner, repo = parsed
    if owner.lower() in _RESERVED_OWNERS:
        return _reject("not_a_repo", language)

    return {
        "owner": owner,
        "repo": repo,
        "rejection_reason": None,
        "supervisor_log": [f"guardrail: accepted {owner}/{repo}"],
    }


def _reject(reason_key: str, language: str) -> dict:
    text = _MESSAGES[reason_key][language if language in ("en", "ar") else "en"]
    return {
        "owner": "",
        "repo": "",
        "rejection_reason": text,
        "report": text,
        "next_agent": "done",
        "supervisor_log": [f"guardrail: rejected ({reason_key})"],
    }


def route_after_guardrail(state: AgentState) -> str:
    """المسار الشرطي الأول: رفض مؤدب، أو المضي إلى الجلب."""
    return "rejected" if state.get("rejection_reason") else "fetch"
