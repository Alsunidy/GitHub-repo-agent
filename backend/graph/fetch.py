"""Fetch node -- fills repo_data once, and covers the failure path the brief asks for.

Three ways this fails:
  1. RepoNotFound -- the repo is missing or private (expected, polite message).
  2. Any other exception -- network, rate limit, unexpected response. We neither
     crash nor invent data: the run stops and the user is told what happened.
  3. Success returning nothing -- a repo with no readable content at all.
"""

from backend.state import AgentState
from backend.tools.github_tools import RepoNotFound, fetch_repo_data

# User-facing text stays bilingual -- see the note in guardrail.py.
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
        "en": "`{full_name}` exists but returned no readable content -- no README, "
              "no dependency files, and no source files I can inspect. There is "
              "nothing for me to analyse.",
        "ar": "`{full_name}` موجود لكنه لم يُرجع أي محتوى قابل للقراءة — لا README، "
              "ولا ملفات تبعيات، ولا ملفات مصدرية أستطيع فحصها. لا يوجد ما أحلّله.",
    },
}


def fetch_node(state: AgentState) -> dict:
    """Call the real GitHub tool and put the result in the state."""
    owner, repo = state["owner"], state["repo"]
    language = state.get("language", "en")
    full_name = f"{owner}/{repo}"

    try:
        repo_data = fetch_repo_data(owner, repo)
    except RepoNotFound:
        return _fail("not_found", language, full_name=full_name)
    except Exception as exc:  # noqa: BLE001 -- any tool fault becomes a readable message
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
    """A tool can succeed and still return nothing -- that is a failure too."""
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
    """Conditional edge 2: a fetch failure ends the run before any agent starts."""
    return "failed" if state.get("rejection_reason") else "supervisor"
