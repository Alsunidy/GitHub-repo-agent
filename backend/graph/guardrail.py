"""Guardrail node -- the first gate: nothing passes without a valid repo URL.

It blocks three cases: empty input, input that is not a URL at all, and URLs
that point at github.com but not at a repository (a profile, a search page,
a settings page).
"""

from backend.state import AgentState
from backend.tools.github_tools import parse_repo_url

# Paths on github.com that are not repositories. Rejected even when they
# happen to match the owner/repo shape.
_RESERVED_OWNERS = {
    "settings", "notifications", "explore", "marketplace", "pricing",
    "search", "login", "join", "about", "features", "sponsors",
    "orgs", "topics", "trending", "collections", "events", "new",
}

# User-facing text stays bilingual: the report language is a product feature
# and part of the agreed contract (state field `language`).
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
    """Fill owner/repo, or fill rejection_reason and stop the run politely."""
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
    """Conditional edge 1: polite rejection, or carry on to the fetch."""
    return "rejected" if state.get("rejection_reason") else "fetch"
