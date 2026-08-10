# Product definition -- Part 1 of the brief (20% of the grade)

> **Proposed name:** Taslīm ("handover")
> **In one sentence:** a written risk report on a codebase you did not write,
> in four minutes instead of four hours.

---

## 1. Market segmentation

**Primary segment:** software development agencies in Saudi Arabia, 5-30
developers, that **take on code they did not write** -- for maintenance, for
extension, or to quote on it.

| | |
|---|---|
| **Who pays** | The agency owner or delivery manager -- they carry the cost of a bad quote |
| **Who uses** | The tech lead assigned to assess the repository |
| **The trigger moment** | The client says: "here's our repo, what would you charge to maintain it?" |

**Not the segment:** "developers" or "tech companies" -- vague terms the brief
rejects outright. This segment is defined by an **event** (inheriting unfamiliar
code), not by a job title.

### How to build the list of fifty names before the presentation

The brief requires a segment narrow enough to name fifty real customers. Do not
invent names -- pull them from sources a grader can verify:

1. **LinkedIn** -- filter: `Software Development` + `Saudi Arabia` + `11-50 employees`
2. **The Monsha'at directory** and the commercial register -- activity "software development"
3. **Accelerator portfolios:** Misk, Flat6Labs, Sanabil 500, the Badir programme
4. **Certified integration partners** of the cloud providers operating in the region

Put the fifty in one table with company name, size, and where the name came
from, and attach it as an appendix slide. That alone separates you from teams
who say "small businesses".

**Later expansion:** in-house engineering teams at non-tech companies (banks,
retail, logistics). Their repositories carry mixed Arabic/English issue
trackers, which is exactly what the cross-language duplicate detection serves.

---

## 2. The need, the value, and why an agent

### The problem

Before quoting on maintaining code you did not write, you need to know what you
are inheriting. Today a senior developer spends 3-6 hours reading the repository
to write a risk estimate. The arithmetic:

| Item | Figure |
|---|---|
| Senior developer hours to assess one repository | 3-6 hours |
| Hourly cost (market estimate -- verify it) | SAR 150-200 |
| **Cost of assessing a single opportunity** | **SAR 450-1,200** |
| Share of quotes that convert to contracts | 20-30% |

So **70-80% of that cost is burned on work that is never won**. Worse: when the
assessment gets cut short to save time, repositories carrying vulnerabilities,
exposed secrets and documentation debt get quoted as if they were sound -- and
the difference comes out of the agency's margin for the life of the contract.

### Why an agent? (the question the brief asks outright)

**Replace it with a static form:** a form decides nothing. The user would have
to know which check they need -- which is precisely what they do not know,
because they have not seen the code yet.

**Replace it with a rule-based script:** it would run all three checks every
time, in one order. But repositories are not alike:
- No dependency file, and the vulnerability scan returns "no findings" -- noise, time, and tokens
- 300 open issues, and issue triage **is** the entire value
- No README, and documentation is the top priority rather than the last item on a list

**Replace it with a single LLM call:** it fails for three hard reasons.
1. The model **cannot know** vulnerabilities published after its training date --
   OSV.dev has to actually be queried
2. The repository's contents have to be fetched from the GitHub API -- the model
   does not have them
3. The final output is **an action in the real world**: opening an issue on
   someone else's repository. That is an irreversible side effect and needs a
   human approval gate, not a line in a prompt

### The measured evidence (not the claim)

This is real output from `scripts/smoke_graph.py` on the system as built:

```
supervisor: [llm] issues   — The repository has open issues that may be
                             duplicates, which could help prioritize fixes...
supervisor: [llm] security — Running the security agent is crucial to identify
                             vulnerabilities, especially given the presence of
                             a requirements file.
supervisor: [llm] docs     — The README is very short and likely lacks
                             important information...
```

**The deterministic order written in the code is `security → issues → docs`.**
The supervisor departed from it and started with `issues`, based on the signals
of this specific repository, and explained why.

A single call with a fixed prompt does not produce this. That is your answer in
the Q&A, with `proof_graph.txt` as the evidence.

---

## 3. Functional scope -- the MVP

### The tools the agents call

| Tool | What it actually does | External system |
|---|---|---|
| `fetch_repo_data` | Fetches metadata, README, open issues, dependency and code files | **GitHub REST API** |
| `check_vulnerabilities` | Queries known vulnerabilities per installed package, returns GHSA/CVE ids | **OSV.dev API** |
| `scan_secrets` | Scans files for known key patterns (`ghp_`, `sk-`, `AKIA...`) and masks what it finds | local |
| `open_issue` | Opens a real issue on the repository after the user approves | **GitHub REST API (write)** |

Three tools reach genuine external systems, and **none of them returns canned
data** -- an explicit requirement in the brief.

### What the agent decides versus what we fixed in the graph

| Decided by the agent (the supervisor) | Fixed in the graph |
|---|---|
| Which specialist agent runs next | URL validation (the guardrail) |
| In what order | Fetching the data once |
| When to stop -- it may not run all three | Assembling the report once the agents finish |
| The wording and severity of each finding | **The approval gate before writing to GitHub** |

The rule: **judgement to the model, safety to the code.** The supervisor
computes eligibility programmatically (who has material to work on), leaves
order and stopping to the model, then validates every decision it returns before
acting on it -- a choice naming an already-run or ineligible agent is corrected
automatically.

### Explicitly out of scope for the MVP

- Platforms other than GitHub (GitLab, Bitbucket)
- Automatic fixes or opening pull requests
- Continuous monitoring -- this product is a **point-in-time assessment**, not a watchdog
- Licence and legal compliance checks
- Dependency ecosystems other than Python in the first release (`requirements.txt` only)
- Analysis of code quality itself (complexity, test coverage)

---

## 4. Differentiation

| | Dependabot / Snyk / Socket | GitGuardian | **Taslīm** |
|---|---|---|---|
| Focus | Dependency vulnerabilities | Exposed secrets | **Four dimensions in one verdict** |
| Setup | Install on the repo + CI | Install | **Paste a URL -- no setup** |
| Issue triage | No | No | Yes |
| Duplicate detection **across Arabic and English** | No | No | Yes |
| Arabic report | No | No | Yes |
| Mode | Continuous monitoring | Continuous monitoring | **On-demand assessment** |

**The real alternative is not a competitor -- it is doing nothing.** Today the
agency either burns four senior-developer hours or quotes on instinct. The
competition is time and guesswork, not Snyk.

**Three points that are hard to copy quickly:**
1. **Genuinely bilingual** -- it catches the same bug filed twice, once in Arabic
   and once in English. No global competitor does this, because the Arabic market
   is not their priority.
2. **It writes nothing without human approval** -- opening an issue on a client's
   repository carries reputational weight. The gate is a selling point, not a
   technical limitation.
3. **It skips what has no material** -- no reports padded with "no findings".

---

## 5. Business model

### The real cost -- measured, not guessed

`scripts/estimate_cost.py` builds the exact supervisor prompt the system sends
and counts it, then sizes the agents' inputs from the repository data:

```
repository: 30 issues, README 3000 chars, 10 code files
counting method: exact, measured with tiktoken

stage                      calls     input   output       SAR
supervisor (4 rounds)          4     1,632      240    0.0015
security agent                 1     5,150      400    0.0038
issues agent                   1     3,380      400    0.0028
docs agent                     1       750      400    0.0013
report                         1     1,200      900    0.0027
total                               12,112    2,340    0.0121
```

**Cost per analysis = 1.21 halalas** (gpt-4o-mini).
**The supervisor's share: 13.5% of input tokens** -- that is the price of
deciding rather than always running everything. The brief says "an agent that
loops is more expensive than a single call; show that you know the number". The
number is 13.5%, and what it buys is skipping empty checks on repositories that
do not need them.

> Run the script yourself before the slide and refresh the figures:
> `python scripts/estimate_cost.py --issues 120 --readme 8000 --code-files 30`

### Pricing

| Plan | Price | Limit |
|---|---|---|
| **Agency** | SAR 299/month | 150 analyses |
| Additional analysis | SAR 3 | -- |

**The pricing logic:** a manual assessment costs the agency SAR 450-1,200 per
opportunity. A full month's plan is cheaper than **one manual assessment**. It
is not priced on cost -- it is priced on the hours it replaces.

### Projections

| | |
|---|---|
| 30 agencies x SAR 299 | **SAR 8,970/month** |
| Token cost (30 x 150 x 0.0121) | ~SAR 54/month |
| Gross margin on inference | >99% |

**Be honest on the slide:** the real cost is not tokens -- it is hosting,
support, and sales. Say so before the grader asks; the 99% figure on its own
reads naive.

**Retention:** moderate, not high. This is a point-in-time assessment that does
not embed itself in daily workflow. The route to raising it: an archive of past
assessments and a before/after comparison for the same client.

---

## 6. The risks a grader will ask about

| Question | Answer |
|---|---|
| "What stops GitHub building this tomorrow?" | Technically nothing. But the Arabic market is not their priority, and cross-language duplication is not a problem they see. The advantage is temporal, not permanent -- say so plainly. |
| "Why pay for what Snyk does for free?" | Snyk checks one dimension and needs installing on the repository. The value here is a combined verdict on a repository **you do not own yet**. |
| "What if the model gets it wrong?" | It writes nothing without human approval, and every finding carries evidence: a GHSA/CVE id, an issue number, or the name of a missing section. |
| "Rate limits?" | 60/hour without a token, 5,000/hour with one -- enough for roughly 150 analyses an hour. |
| "What about private repositories?" | It works with a token that has read access. Where it cannot, the system declines politely and does not invent a result. |

---

## A note on using this document

The figures here are of two kinds:
- **Measured from the system** (token cost, the supervisor's share, the
  supervisor output) -- use them as they are
- **Market estimates** (developer hourly rate, quote conversion rate, number of
  agencies) -- verify them with two or three calls to real agencies before the
  presentation, and say on the slide that they are estimates

The difference between the two is the difference between a team that knows its
product and a team reading numbers off a slide.
