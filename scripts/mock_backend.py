"""Mock backend for developing ui/app.py before the real FastAPI backend
exists. Returns the fixed-shape responses defined by CONTRACTS.md's API
contract (section 3) — no LangGraph involved at all.

╔══════════════════════════════════════════════════════════════════════╗
║  Development scaffolding only — same status as backend/stubs.py.      ║
║  Delete once the real backend (FastAPI + graph) exists and ui/app.py  ║
║  has been pointed at it (see WORK_SPLIT.md, second integration point).║
╚══════════════════════════════════════════════════════════════════════╝

Run:
    python scripts/mock_backend.py

Then point the UI at it via .env:
    FAHES_BACKEND=http://localhost:8000
Switching to the real backend later is a one-line change to that value —
ui/app.py never needs to change.
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from backend.tools.github_tools import parse_repo_url  # noqa: E402

app = FastAPI(title="Fahes mock backend (dev only)")

# thread_id -> {"owner": str, "repo": str} | {"owner": None} for a rejected request
_THREADS: dict[str, dict] = {}

_REPORTS = {
    "en": (
        "## Executive Summary\n\n"
        "This is a canned report from the **mock backend** — no repository "
        "was actually analysed. It exists to build and test the UI before "
        "the real backend is ready.\n\n"
        "## Top Issues\n\n"
        "1. **[high] Example vulnerable dependency** — a made-up finding for UI testing. "
        "(Evidence: GHSA-0000-0000-0000)\n"
        "2. **[medium] Example duplicate issues** — #3 and #7 look like the same bug. "
        "(Evidence: #3, #7)\n"
        "3. **[low] README is missing: license** — no license section found. "
        "(Evidence: license)\n"
    ),
    "ar": (
        "## الملخص التنفيذي\n\n"
        "هذا تقرير ثابت من **الخادم الوهمي** — لم يُفحص أي مستودع فعلياً. "
        "الغرض منه بناء واختبار الواجهة قبل جاهزية الخادم الحقيقي.\n\n"
        "## أخطر المشاكل\n\n"
        "1. **[high] اعتمادية وهمية بها ثغرة** — نتيجة تجريبية لاختبار الواجهة. "
        "(الدليل: GHSA-0000-0000-0000)\n"
        "2. **[medium] بلاغات مكررة وهمية** — يبدو أن #3 و#7 نفس المشكلة. "
        "(الدليل: #3, #7)\n"
        "3. **[low] ينقص README: الترخيص** — لا يوجد قسم ترخيص. "
        "(الدليل: license)\n"
    ),
}

_REJECTION = {
    "en": "This doesn't look like a GitHub repository URL. Please check it and try again.",
    "ar": "هذا لا يبدو رابط مستودع GitHub. تأكّد من الرابط وحاول مرة أخرى.",
}


class AnalyzeRequest(BaseModel):
    repo_url: str
    language: str = "en"


class ApproveRequest(BaseModel):
    thread_id: str
    approved: bool


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    thread_id = str(uuid.uuid4())
    language = req.language if req.language in ("en", "ar") else "en"
    parsed = parse_repo_url(req.repo_url)

    if parsed is None:
        _THREADS[thread_id] = {"owner": None}
        return {
            "thread_id": thread_id,
            "status": "rejected",
            "report": _REJECTION[language],
            "agents_done": [],
        }

    owner, repo = parsed
    _THREADS[thread_id] = {"owner": owner, "repo": repo}
    return {
        "thread_id": thread_id,
        "status": "awaiting_approval",
        "report": _REPORTS[language],
        "agents_done": ["security", "issues", "docs"],
    }


@app.post("/approve")
def approve(req: ApproveRequest):
    thread = _THREADS.get(req.thread_id)
    if not req.approved or not thread or not thread.get("owner"):
        return {"status": "cancelled", "issue_url": None}

    issue_url = f"https://github.com/{thread['owner']}/{thread['repo']}/issues/999"
    return {"status": "done", "issue_url": issue_url}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
