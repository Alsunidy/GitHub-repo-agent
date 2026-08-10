# Handoff: track 1 → track 2

> The graph is built, tested end to end, and currently running on stubs. This
> document tells you exactly what to build and where, so your code drops in
> without a single line changing in the graph.

---

## 1. Contract changes -- additive, nothing of yours breaks

Four fields were added to `AgentState`. **Every existing field is unchanged**,
so anything you built against the original contract still holds.

| Field | Type | Written by | Why it was added |
|---|---|---|---|
| `issue_title` | `str` | **the report node (you)** | `/approve` needs a title to open the issue with |
| `issue_body` | `str` | **the report node (you)** | and a body to put in it |
| `approved` | `Optional[bool]` | the backend on resume | `None` = not asked, `True` = approved, `False` = declined |
| `supervisor_log` | `Annotated[list[str], operator.add]` | every node | a decision trace -- the brief asks for tracing in the demo |

**Reasoning:** without `issue_title` and `issue_body`, `/approve` has no way to
know what to open. The alternative was parsing them back out of the report text
inside the graph, which is brittle and breaks the moment the report wording
changes.

**What this means for you:** `report_node` returns three keys, not one:
```python
return {"report": ..., "issue_title": ..., "issue_body": ...}
```

---

## 2. The LLM -- settled

The provider is **OpenAI**, the model is `gpt-4o-mini` (override with
`LLM_MODEL` in `.env`).

Do not build `ChatOpenAI` yourself. Call the factory:

```python
from backend.llm import get_llm

llm = get_llm(temperature=0)                      # a ready chat model
llm = get_llm().with_structured_output(MyModel)   # structured output
```

That keeps a model or settings change in one file instead of six.

Before debugging the graph, check the key on its own:
```bash
python scripts/check_llm.py
```

---

## 3. What you build -- and the exact names the graph imports

The graph imports these names precisely. A different name or path breaks the
wiring.

### `backend/tools/github_tools.py`
```python
def parse_repo_url(url: str) -> tuple[str, str] | None: ...
def fetch_repo_data(owner: str, repo: str) -> dict: ...
def open_issue(owner: str, repo: str, title: str, body: str) -> str: ...
class RepoNotFound(Exception): ...
class MissingToken(Exception): ...
```

### `backend/tools/osv_tools.py` and `backend/tools/secret_tools.py`
Exactly as in `CONTRACTS.md`. The graph does not import these directly -- your
security agent is what calls them.

### `backend/graph/agents.py`
Three functions, each taking the state and returning a dict:
```python
def security_agent(state: AgentState) -> dict:
    return {"findings": [...], "agents_done": ["security"]}

def issues_agent(state: AgentState) -> dict:
    return {"findings": [...], "agents_done": ["issues"]}

def docs_agent(state: AgentState) -> dict:
    return {"findings": [...], "agents_done": ["docs"]}
```

> **Critical:** every agent **must** return `agents_done` with its own name. The
> field accumulates via `operator.add`, so return one element, never the whole
> list. Forget it and the supervisor thinks the agent never ran and dispatches
> it again. (A safety belt stops the loop after 5 rounds, but that treats the
> symptom, not the cause.)

### `backend/graph/report.py`
```python
def report_node(state: AgentState) -> dict:
    return {"report": ..., "issue_title": ..., "issue_body": ...}
```
Read `state["findings"]` (accumulated from every agent) and `state["language"]`
(`"en"` or `"ar"`), and write the report in the user's language.

---

## 4. What reaches you in the state

By the time your agent runs, these fields are ready and guaranteed:

- `repo_data` -- complete, in the contract's shape, and **never empty**: the
  fetch node stops the run before you if the repository came back with nothing.
- `owner` / `repo` -- parsed and validated.
- `language` -- only `"en"` or `"ar"`, never a third value.
- `findings` -- whatever earlier agents accumulated (possibly empty if you are first).
- `agents_done` -- who ran before you.

**A missing repository or an invalid URL never reaches you** -- the guardrail
and fetch nodes stop both before the supervisor is even called.

---

## 5. The supervisor may not run your agent -- by design

The supervisor computes eligibility before it decides:

| Agent | Not run when |
|---|---|
| `security` | there are no dependency files **and** no code files |
| `issues` | there are no open issues |
| `docs` | -- always eligible (a missing README is itself a finding) |

On top of eligibility, the LLM chooses the order and may stop early. So **do not
assume in `report_node` that all three agents ran** -- read `agents_done` and
write the report from what actually happened.

---

## 6. Stub deletion list (first integration point)

The brief explicitly forbids any tool that returns canned data. When your code
is ready we delete:

1. `backend/stubs.py` -- the whole file
2. the `try/except ImportError` block in `backend/graph/guardrail.py`
3. the `try/except ImportError` block in `backend/graph/fetch.py`
4. both `try/except ImportError` blocks in `backend/graph/build.py`

Each block is marked `# -- temporary: delete at the first integration point --`.
After deletion only the direct `from ... import ...` lines remain.

To confirm nothing is left behind:
```bash
grep -rn "stubs" backend/ && echo "something remains!" || echo "clean"
```

---

## 7. Running what exists today

```bash
pip install -r requirements.txt
python scripts/smoke_graph.py        # 6 scenarios: happy, failure, rejection, approve/decline
python scripts/smoke_supervisor.py   # 11 checks of the supervisor's logic
```
Both run with no LLM key and no network (the supervisor falls back to its
deterministic order).

---

## 8. What is still shared work

The FastAPI backend is not built yet -- it is joint work at the second
integration point per `WORK_SPLIT.md`. The graph is ready for it:
`build_graph()` returns a graph compiled with `MemorySaver` and paused before
`publish`, so `/analyze` calls `invoke` and reads the report, and `/approve`
calls `update_state(config, {"approved": ...})` then `invoke(None, config)`.
