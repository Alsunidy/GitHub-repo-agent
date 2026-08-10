# System architecture -- Part 2 of the brief (20% of the grade)

> The diagram below is generated from the compiled graph itself via
> `python scripts/export_architecture.py`, so it cannot contradict the code.

```mermaid
graph TD;
	__start__([__start__]):::first
	guardrail(guardrail)
	fetch(fetch)
	supervisor(supervisor)
	security(security)
	issues(issues)
	docs(docs)
	report(report)
	publish("publish<hr/><small><em>interrupt = before</em></small>")
	__end__([__end__]):::last
	__start__ --> guardrail;
	guardrail -. rejected .-> __end__;
	guardrail -.-> fetch;
	fetch -. failed .-> __end__;
	fetch -.-> supervisor;
	supervisor -.-> security;
	supervisor -.-> issues;
	supervisor -.-> docs;
	supervisor -.-> report;
	security --> supervisor;
	issues --> supervisor;
	docs --> supervisor;
	report --> publish;
	publish --> __end__;
```

**The loop is the heart of the design:** the supervisor does not run the three
agents in a fixed order. Control returns to it after every agent so it can
decide -- from what has been found so far -- who runs next, or whether to stop.

---

## 1. Nodes and their responsibilities

| Node | Responsibility | File |
|---|---|---|
| `guardrail` | Verifies the input is a valid GitHub repository URL and rejects anything else with a polite message in the user's language, before any external call | `graph/guardrail.py` |
| `fetch` | Fetches the repository data once and puts it in the state | `graph/fetch.py` |
| `supervisor` | Computes which agents have material to work on, asks the model for priority and stopping, then validates its answer before acting on it | `graph/supervisor.py` |
| `security` | Checks dependency files against OSV.dev and scans source files for exposed secrets | `graph/agents.py` |
| `issues` | Triages open issues: duplicates -- including the same bug filed in both Arabic and English -- stale items, and priority | `graph/agents.py` |
| `docs` | Grades the README against four criteria: what the project is, installation, usage, licence | `graph/agents.py` |
| `report` | Assembles the accumulated findings into a report in the user's language, and writes the proposed issue title and body | `graph/report.py` |
| `publish` | The only node that writes to the outside world -- runs only after explicit human approval | `graph/build.py` |

## 2. Conditional edges -- and exactly what each inspects

| Function | What it inspects | Possible outcomes |
|---|---|---|
| `route_after_guardrail` | Is `rejection_reason` not `None`? | `rejected → END` \| `fetch` |
| `route_after_fetch` | Did the fetch node set `rejection_reason`? | `failed → END` \| `supervisor` |
| `route_from_supervisor` | The value of `next_agent` -- an agent name, or `"done"`? | `security` \| `issues` \| `docs` \| `report` |

Two end the run early; the third is the loop. All three genuinely change the
path rather than decorating it.

## 3. The State -- what accumulates and what is overwritten

| Field | Type | Behaviour | Written by |
|---|---|---|---|
| `repo_url` | `str` | input | the user |
| `language` | `str` | input -- `"en"` or `"ar"` | the user |
| `owner` / `repo` | `str` | overwritten | `guardrail` |
| `rejection_reason` | `Optional[str]` | overwritten | `guardrail` · `fetch` |
| `repo_data` | `dict` | written once | `fetch` |
| `next_agent` | `str` | overwritten each round | `supervisor` |
| `agents_done` | `Annotated[list[str], add]` | **accumulates** | each agent adds its own name |
| `findings` | `Annotated[list[dict], add]` | **accumulates** | each agent |
| `supervisor_log` | `Annotated[list[str], add]` | **accumulates** | every node -- the decision trace |
| `report` | `str` | overwritten | `report` · the rejection paths |
| `issue_title` / `issue_body` | `str` | overwritten | `report` |
| `approved` | `Optional[bool]` | set by the human | the backend on resume |
| `issue_url` | `Optional[str]` | overwritten | `publish` |

Only three fields accumulate via `operator.add`; the rest are overwritten. That
distinction is what lets three agents write into the state without one erasing
another's work.

## 4. Tools and external systems

| Tool | Attached to | External system | What it does |
|---|---|---|---|
| `fetch_repo_data` | `fetch` | **GitHub REST** | metadata, README, open issues, dependency and code files |
| `check_vulnerabilities` | `security` | **OSV.dev** | known vulnerabilities per installed package, with GHSA/CVE ids as evidence |
| `scan_secrets` | `security` | local | known key patterns, with the snippet partially masked |
| `open_issue` | `publish` | **GitHub REST -- write** | opens a real issue -- the one irreversible action |

Three tools reach a genuine external system, and none of them returns canned data.

## 5. Persistence and human intervention

The graph is compiled with `MemorySaver` and `interrupt_before=["publish"]`.
When execution reaches `publish` it pauses and the state is saved under a
`thread_id`, so the user reads the whole report **before** anything is written
to someone else's repository.

| Step | What happens |
|---|---|
| `POST /analyze` | Calls `invoke`; the graph pauses before publishing and returns the report plus a `thread_id` with status `awaiting_approval` |
| -- waiting -- | The state lives in the checkpointer. The user reads and decides with no time limit |
| `POST /approve` | `update_state(config, {"approved": ...})` then `invoke(None, config)` -- resumes from exactly where it paused |
| `approved = false` | `publish` runs and exits immediately with `issue_url = None`. Nothing is written |

## 6. Failure paths

| Failure | Where | Behaviour |
|---|---|---|
| URL is not a GitHub repository | `guardrail` | A polite rejection in the user's language and an immediate end -- with no external call at all |
| `RepoNotFound` | `fetch` | Explains the repository is missing or private, and ends before any agent runs |
| Network fault or rate limit | `fetch` | Translates the exception into a readable message, and states it is a problem on our side, not a finding about the repository |
| Tool succeeds but returns nothing | `fetch` | Treated as a failure: no README, no dependencies, no code means nothing to analyse |
| The LLM is unavailable | `supervisor` | **Does not stop** -- falls back to a deterministic order: security, then issues, then docs |
| The model picks an ineligible or already-run agent | `supervisor` | The decision is corrected before routing. And if it tries to stop before any agent ran, that is refused -- an empty report is not allowed |
| `MissingToken` on publish | `publish` | The report survives intact and `issue_url = None` with a clear reason. A write failure never loses the analysis |

One rule throughout: the system explains what happened and **never invents a result**.

---

## Why an agent? -- real output, not a claim

The deterministic order written in `_FALLBACK_ORDER` is
`security → issues → docs`. On the test repository the model read the signals,
started with `issues` instead, and justified it:

```
supervisor: [llm] issues   — open issues that may be duplicates, which could
                             help prioritize fixes...
supervisor: [llm] security — crucial to identify vulnerabilities, given the
                             presence of a requirements file.
supervisor: [llm] docs     — the README is very short and likely lacks
                             important information.
supervisor: [rule] done    — no eligible agent left
```

A single call with a fixed prompt does not produce this, and a rule-based script
would have run all three in the same order on every repository.

**The cost of that decision is measured:** 13.5% of input tokens -- about 1.21
halalas per analysis. Details in `docs/PRODUCT.md`, full log in `proof_graph.txt`.
