"""FastAPI backend -- implements the API contract in CONTRACTS.md (section 3).

    uvicorn backend.main:app --reload --port 8000

The graph is built once, at import time, and reused for every request. Its
MemorySaver checkpointer is what lets /approve resume the exact thread
/analyze started; building a fresh graph per request would lose that
thread's history and /approve would have nothing to resume.
"""
import uuid

from fastapi import FastAPI
from pydantic import BaseModel

from backend.graph.build import build_graph
from backend.state import initial_state

app = FastAPI(title="GitHub Repo Health Agent")
_graph = build_graph()


class AnalyzeRequest(BaseModel):
    repo_url: str
    language: str = "en"


class ApproveRequest(BaseModel):
    thread_id: str
    approved: bool


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    thread_id = str(uuid.uuid4())
    config = _config(thread_id)

    state = _graph.invoke(initial_state(req.repo_url, req.language), config)

    if state.get("rejection_reason"):
        return {
            "thread_id": thread_id,
            "status": "rejected",
            "report": state.get("report", ""),
            "agents_done": [],
        }

    return {
        "thread_id": thread_id,
        "status": "awaiting_approval",
        "report": state.get("report", ""),
        "agents_done": state.get("agents_done", []),
    }


@app.post("/approve")
def approve(req: ApproveRequest):
    config = _config(req.thread_id)

    # Per HANDOFF.md: resume the paused thread by writing the human decision
    # into its state, then invoke(None, ...) to run from where it paused.
    _graph.update_state(config, {"approved": req.approved})
    final = _graph.invoke(None, config)

    return {
        "status": "done" if req.approved else "cancelled",
        "issue_url": final.get("issue_url"),
    }
