# Work split -- GitHub Repo Health Agent

> **Goal:** each side builds its piece independently, without waiting on the other.
> **Primary reference:** the contracts document `CONTRACTS.md` -- read and agreed
> before any code.
> **A note on terminology:** "node" = a work station inside the graph.
> "the contracts" = the agreed interfaces document.

---

## Before starting (together -- 30 minutes)

Read `CONTRACTS.md` and agree on three things:
1. The shape of the State (field names, types, and which accumulate)
2. The tool signatures (each function's name, inputs, and output shape)
3. The API contract (routes, request shape, response shape)

Any objection or change is settled now -- after that the document is frozen.

---

## Track 1 -- graph structure and the decision brain

| Item | Description |
|---|---|
| `state.py` | Define the State: fields and types, and which accumulate versus which are replaced |
| Guardrail node | Verify the GitHub URL is valid, and route anything invalid to a polite rejection |
| Fetch node | Call the GitHub tool and put the data in the State, plus the failure path when the repository is missing |
| **Supervisor node** | Read the repository state and the agents already run, and decide which agent runs next |
| Conditional edges + the loop | Wire the nodes, the branching conditions, and the return to the supervisor after each agent |

**How it works without waiting:** a `stubs.py` file holds fake versions of
track 2's tools with the agreed signatures -- the whole graph is built and
tested against them, and they are deleted at the first integration point.

**Suggested order:** State → guardrail → fetch → **supervisor** → edges and loop.

---

## Track 2 -- tools, the execution contract, and the UI

| Item | Description |
|---|---|
| GitHub tool | `parse_repo_url` + `fetch_repo_data` + `open_issue` |
| OSV tool | `check_vulnerabilities` -- check for vulnerabilities and return GHSA/CVE ids |
| Secret-scanning tool | `scan_secrets` -- detect exposed keys inside the code |
| The prompts | Instructions for the three agents and the report, plus language rules and guardrails |
| **Security agent node** | Run the vulnerability and secret scans and add the findings to the State |
| **Issues agent node** | Analyse the issues: duplicates (in both languages), stale items, priorities |
| **Docs agent node** | Grade the README against four criteria: what the project is, installation, usage, licence |
| Report node | Assemble the accumulated findings and write the final report in the chosen language |
| Streamlit UI | The interface, the language switch, and the approve/decline buttons |
| Tests | Happy path + failure paths + saving the execution proof |

**How it works without waiting:** the tools are tested with a direct script that
calls them without the graph at all, and the UI is built against a small fake
backend returning the fixed responses written in contract 3.

**Suggested order:** GitHub tool → OSV tool → secrets tool → prompts → the three
agents → report → UI → tests.

---

## Shared work

| Item | When |
|---|---|
| The HITL interrupt and the backend (FastAPI) | At the second integration point -- an hour together |
| The full README | Once the system is complete |
| The slides (architecture for track 1, product and market for track 2) | Once the system is complete |
| Two full rehearsals + recording a backup demo | The last two days |
| Final packaging (zip: code + README + slides as PDF) and sending | The day before the deadline |

---

## Integration points (only three)

1. **Agreeing the contracts** -- before any code
2. **First integration:** delete the stubs, wire the real tools into the graph,
   and build the backend and the interrupt together
3. **Second integration:** point the UI at the real backend and run the whole
   flow end to end

---

## Standing rules

- **Neither side edits the same file** -- the split is built on file separation
  to avoid conflicts
- **Any change to the contracts means telling the other side immediately** --
  silently changing the shape of a function's output is the number one cause of
  teams breaking each other's work
- **The stubs and the fake backend are development aids only** -- deleted
  entirely before submission, since the brief forbids any tool that returns
  canned data
- **Start with the hardest thing in your track:** the supervisor / the GitHub
  tool -- surprises come from the hardest part, and it is better they surface early
- **A two-sentence daily update:** what I finished, what I am on now, what I need
  from you
