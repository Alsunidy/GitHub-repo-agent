"""FastAPI backend -- the only process that runs the graph.

The UI never imports the graph (a hard requirement of the brief); it talks to
these three routes over HTTP. The contract is CONTRACTS.md section 3.

Run:
    uvicorn backend.api:app --port 8000

The human-in-the-loop pause is what makes two routes necessary instead of one:

    POST /analyze  -> invoke the graph; it runs to the publish node and stops
                      there (interrupt_before), so nothing is written to GitHub
                      yet. The report comes back with a thread_id.
    POST /approve  -> write the human decision into that thread's state and
                      resume it. Only now can the publish node open the issue.

The thread's paused state lives in the graph's MemorySaver, which is in-process
memory: restarting the server forgets every thread waiting for approval. That is
acceptable for a demo (a pause lasts seconds) and is the one line to change --
swap the checkpointer in build_graph() -- if this ever needs to survive
restarts.
"""

import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from backend.graph.build import build_graph
from backend.state import initial_state

app = FastAPI(
    title="GitHub Repo Health Agent",
    description="Multi-agent repository review with human approval before writing.",
    version="1.0.0",
)

# One compiled graph for the whole process: its checkpointer is what holds the
# paused threads, so /approve can resume the exact run /analyze left waiting.
_graph = build_graph()


class AnalyzeRequest(BaseModel):
    repo_url: str = Field(description="The GitHub repository URL, as the user typed it.")
    language: str = Field(default="en", description='"en" or "ar".')


class AnalyzeResponse(BaseModel):
    thread_id: str
    status: str  # "awaiting_approval" | "rejected"
    report: str
    agents_done: list[str]


class ApproveRequest(BaseModel):
    thread_id: str
    approved: bool


class ApproveResponse(BaseModel):
    status: str  # "done" | "cancelled"
    issue_url: Optional[str] = None
    # Not in the original contract, purely additive: when an approved publish
    # cannot go through (no GITHUB_TOKEN, GitHub rejected the write), the UI
    # would otherwise just show "no issue was opened" with no reason.
    message: Optional[str] = None


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    """Run one full review and stop at the approval gate."""
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    try:
        state = _graph.invoke(initial_state(req.repo_url, req.language), config)
    except Exception as exc:  # noqa: BLE001 -- an unexpected fault is a 500, not a stack trace to the user
        raise HTTPException(
            status_code=500,
            detail=f"The analysis failed: {type(exc).__name__}: {exc}",
        ) from exc

    # The graph pauses before `publish` on every path that produced a report.
    # Reaching END instead means the guardrail or the fetch stopped the run --
    # that is the "rejected" status, and its text is already in `report`.
    paused = bool(_graph.get_state(config).next)

    return AnalyzeResponse(
        thread_id=thread_id,
        status="awaiting_approval" if paused else "rejected",
        report=state.get("report", ""),
        agents_done=state.get("agents_done", []),
    )


@app.post("/approve", response_model=ApproveResponse)
def approve(req: ApproveRequest) -> ApproveResponse:
    """Record the human decision and resume the paused thread."""
    config = {"configurable": {"thread_id": req.thread_id}}
    snapshot = _graph.get_state(config)

    if not snapshot.values:
        raise HTTPException(status_code=404, detail="Unknown thread_id.")
    if not snapshot.next:
        raise HTTPException(
            status_code=409,
            detail="This analysis is not waiting for approval (it was rejected, "
                   "or the decision was already made).",
        )

    _graph.update_state(config, {"approved": req.approved})

    try:
        final = _graph.invoke(None, config)
    except Exception as exc:  # noqa: BLE001 -- publish_node handles its own failures; this is the unexpected rest
        raise HTTPException(
            status_code=500,
            detail=f"Resuming the analysis failed: {type(exc).__name__}: {exc}",
        ) from exc

    issue_url = final.get("issue_url")
    return ApproveResponse(
        status="done" if req.approved else "cancelled",
        issue_url=issue_url,
        message=None if issue_url else _publish_message(final),
    )


def _publish_message(final_state: dict) -> Optional[str]:
    """The publish node's own line from the decision trace -- it is the only
    place that knows *why* a publish produced no issue URL."""
    for line in reversed(final_state.get("supervisor_log", []) or []):
        if line.startswith("publish:"):
            # "publish: failed — <user-facing text>" -> the text after the dash
            return line[len("publish:"):].split("—", 1)[-1].strip()
    return None


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
