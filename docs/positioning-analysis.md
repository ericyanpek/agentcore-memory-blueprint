# Positioning Analysis

> Chinese is the primary version: **[定位分析.md](定位分析.md)**.

These are working notes from an external evidence review on 2026-08-14, recording the
positioning judgment behind this project: which cell holds the differentiation, which four
rebuttals must be written down by us first, and which circulating figures cannot be cited.
It is a **judgment**, not a set of verified facts.

## What this document is, and how to read the verification marks

**Most citations here have never been verified in this repository.** The citation discipline
of this repository (see `CLAUDE.md`) requires every citation to be fetched page by page and
matched word for word; second-hand summaries have already produced three errors here. These
notes were written without going through that process.

Every external citation below therefore carries a verification mark:

| Mark | Meaning | May it be promoted into another document |
|---|---|---|
| **Verified** | The source page was fetched in this repository and every sub-claim matched word for word | Yes |
| Unverified | From this external review; the source page was not fetched here | No — fetch and check it yourself first |
| **Measured here** | Evidence produced by a run of this repository, see [scenario-test-report.md](scenario-test-report.md) | Yes |

Only two external citations are **Verified** (see "Rebuttal four" below). Everything else is
unverified — even where it looks plausible, even where the figures are specific. **Looking
plausible is exactly the failure mode this repository guards against.** Before moving any
unverified item from here into [design-rationale.md](design-rationale.md),
[references.md](references.md), or the README, fetch the source page yourself.

This was written on 2026-08-14, and this branch has since fixed some of what it identifies.
Wherever the current state differs from the original judgment, it is marked with a
"**Current state**" note rather than quietly editing the judgment away — where a judgment was
wrong is itself a useful record.

## The positioning in one sentence

What is scarce in an enterprise is not memory storage, it is **the moment at which experience
gets written down**. This project puts curation at the write boundary of shared memory:
structured proposal, policy gate, human review, verbatim storage, attributable and revocable.

Knowledge Bases and Skills are not its competitors, they are downstream of it.

## The differentiation splits into three cells

This is the most important structure in the document. Treating "memory governance" as one
thing mixes the already-solved part with the genuinely empty part, and the most valuable cell
is the one nobody then sees.

| Cell | The question it asks | State of the industry | This project |
|---|---|---|---|
| Authorization | Who is entitled to write the shared scope | Solved, not novel | IAM condition keys plus two Memory resources |
| Curation | Is this fact fit to be shared | **Empty across the industry** | The differentiation is here |
| Maintenance | Is this fact still true | Automated implementations exist, shown unreliable | Currently missing |

### Authorization: do not spend the page count here

Zep's ABAC (policy bound to an API key, write permission fail-closed), Cognee's dataset-level
ACL, and Databricks Unity Catalog all cover this cell (all unverified). This project
implements it with IAM condition keys and two Memory resources, which is the right engineering
choice but not a new one. **Spending the page count here gives the differentiation away.**

### Curation: this is where the gap is

Citations behind "curation is empty" (all unverified): Letta states "when a block is shared,
all attached agents can read and write to it"; Databricks states "Scope is the isolation
boundary between users. Configure the scope in trusted code, and never let the model set it.
The app service principal can read every scope."; Microsoft Foundry best practices state
"Avoid giving agents access to memories shared across all users"; Anthropic's Claude Code
routes team sharing of `CLAUDE.md` through source review, and states that automatic memory is
"just you"; a vendor-neutral protocol paper (arXiv:2606.01138) states "no framework ships a
governance surface that lets a human review writes before they enter long-term storage".

The shape all of this material points at: sharing is a **permission problem**, and the written
content itself has no gate.

### Maintenance: the best argument for a human gate

This cell yields an argument stronger than the security one (all unverified): the STALE
benchmark (arXiv:2605.06527) reports that frontier models with a purpose-built memory
framework recognize that "their own memory has gone stale" at best 55.2% of the time; Zep's
Fact Invalidation is the only shipped invalidation mechanism, but the decision is one LLM call,
at the same reliability tier as the write; mem0 states of its own Memory Decay that it is "a
ranking bias, not truth maintenance".

The inference: **automated maintenance is unreliable, therefore a human is needed.** This is
more usable than "review is needed because it is unsafe", because it does not depend on
assuming an attacker.

## The countervailing 2026 trend must be conceded up front

| Product | Date | What it does |
|---|---|---|
| Anthropic Claude Tag | 2026-06 | "Memory generated in public channels is shared across the workspace automatically"; admins can only delete after the fact |
| Microsoft procedural memory | Build 2026 | A CRUD interface, no approval |
| TencentDB Agent Memory "Team Memory" | 2026-08 | per-item owner/version/status/usage-history, and open source |

(All three unverified.) The TencentDB entry deserves the most attention: it puts status into
the record itself, which is precisely the maintenance cell this project lacks.

The industry direction is "**share first, remediate later**", and this project is the only one
going "approve first". That is the differentiation and also a **burden of argument** — going
against the trend is not the same as being right, and the reason has to be stated.

## The innovation is not the approval flow, it is capture economics

The current documentation locates the innovation in "governance / approval / submission", and
approval is the least new of the three cells — this project's own
[design-rationale.md](design-rationale.md) concedes that the candidate state machine is
near-isomorphic to the AgentCore Registry.

**The position nobody occupies is: reducing the agent-memory problem to the incentive
structure of knowledge contribution.**

On theory (all unverified): Cabrera & Cabrera, "Knowledge-Sharing Dilemmas" (Organization
Studies 23(5):687–710, 2002), frames knowledge contribution as a public-goods dilemma, stating
"there tends to be under-supply of contributions in social dilemma situations"; Wasko & Faraj,
"Why Should I Share?" (MIS Quarterly 29(1):35–57, 2005), finds contribution driven by
reciprocity, reputation, and network commitment, not by the existence of an artifact — that is,
**building the KB and the Skills does not make anyone write into them.**

On evidence (all unverified): Agent READMEs (arXiv:2511.12884) counts 2,303 context files
across 1,925 repositories, "maintained through frequent, small additions", with coverage of
62.3% for build, 69.9% for implementation, and 67.7% for architecture, but 14.5% for security
and 14.5% for performance — teams write down what makes the agent run, not the judgments that
were hard to earn. Shallow Skills adoption (arXiv:2602.14690, 2,923 repositories) reports
Skills "used predominantly as static documents rather than executable workflows". Stack
Overflow monthly question volume peaked at 207,204 in 2014-03 and is around 1,442 in 2026-07
(about −99.3%). Practitioners give two sentences as the root cause: "nothing breaks when it's
stale, so the gap grows silently", and "the update has no natural trigger".

Cases of successful iteration rely on one class of mechanism only: a gate in the same PR, an
incident trigger, a periodic ablation or a GC agent proposing deletions — **all of them lower
the cost of contributing at the moment the context is hottest.**

Suggested formulation: the problem with KBs and Skills was never storage or retrieval, it is
that **there is no natural write trigger**; and the public-goods dilemma guarantees that
without a trigger there is no contribution. **The capture trigger is the product; the approval
flow is only what makes it trustworthy.**

## Three counterexamples inside this project

The argument gets broken by our own repository first, so it is recorded here.

| Counterexample | Original observation (2026-08-14) | Current state |
|---|---|---|
| `skills/` never modified | Across 22 commits `docs/` changed 13 times; both commits touching `skills/` were additions, zero modifications | Unchanged. `skills/` still only ever gains files |
| Promotion path broken in code | `src/handlers/mark_status.py:52` emits `memory.promotion.proposed` with no EventBridge rule subscribing (verified as true) | **Fixed.** A rule routes it to a KMS-encrypted SQS queue drained by a human, and the README architecture diagram now reads "human ingestion / human review" |
| Proposals are not agent-initiated | The candidates in the scenario report were produced by a script calling the API directly; `poc/runtime_agent.py` has no proposal tool | Unchanged. The capture hook is still unimplemented |

The first is the ugliest: `skills/validate-revenue-metric/SKILL.md` ends with "Future changes
require a Git review and a validation test against a representative dataset" — which is exactly
the path **that is never walked a second time**, written by this repository's own hand.

One passage can be turned around and reused: the README's explanation of why no Knowledge Base
was built ("a genuinely usable Knowledge Base needs a defined data source, a chunking strategy,
a vector store, an ingestion job, and retrieval validation") **is itself the reason shared
memory exists** — the friction is too high, so experience never lands.

## Four rebuttals that must be written into the documentation

### One: "stale and confident" is worse than "absent"

"a stale AGENTS.md is worse than no AGENTS.md" (unverified). So "imperfect capture vs. total
loss" **is not an automatic win**.

The mechanism holds on its own, independent of any citation: vector similarity measures topical
relevance, not temporal relevance. A pricing page from 18 months ago and this morning's update
are indistinguishable to cosine; and the older document may **score higher** because it was
written in more detail.

### Two: the exit mechanism

The shared tier is a staging area, and things in a staging area are supposed to leave (the
argument is in [why-layer-by-write-authority.md](why-layer-by-write-authority.md)).

**Two corrections between the original judgment and the current state:**

- The event-expiry capability the original analysis relied on was a **factual error, since
  corrected** (both the README pair and the roadmap pair). It has been verified that the members
  of `MemoryRecordCreateInput` are only
  `['content', 'memoryStrategyId', 'namespaces', 'requestIdentifier', 'timestamp']`, with no
  expiry field.
- The original analysis said "indexed keys cannot be added now, so supersession is blocked",
  and that premise **is wrong**. Indexed keys are indeed fixed at CreateMemory time and cannot
  be added later, but `review_status` was already an indexed key and retrieval was already
  pre-filtering on it — supersession needs no new key. The only one actually missing was
  `superseded_by`, now declared in `infra/lib/memory-governance-stack.ts` (effective only for a
  newly created Memory).

**Still not done**: the supersession mechanism itself.

### Three: a curation gate cannot handle deduplication

Measured here: of 4 records in the shared tier, 2 are the same sentence (`mem-5f417b6c` and
`mem-d9d4444b`), with an identical relevance score of 0.6626. The gate governs "is it fit",
and **inherently cannot govern "do we already have it"**. (**Measured here**, citable.)

**Current state**: the limitations section has been moved forward and this item added. Gate-side
deduplication is still unimplemented.

### Four: reviewer throughput and fatigue

These are the only two **Verified** external citations in the document — the source pages were
fetched and every sub-claim matched word for word.

- arXiv:2607.02579, *When Not to Write Memory: Governing False Promotion from Correlated Agent
  Traces* (Yijiashun Qi, Xiang Xu, Yuxuan Li). **Verified**: false promotion 0.371→0.032; among
  133 external candidates, human adjudication found **not one** fit for automatic promotion; all
  11 verification-gate positives were rejected.
- arXiv:2606.22721, *Habituation at the Gate: Rising Approval and Declining Scrutiny in Human
  Review of AI Agent Code*. **Verified**: 400 repeat reviewers, 11,429 reviews, 7 months;
  approval rate 30.1%→36.8%; a cumulative gap of +14.5pp across experience deciles; inline
  comments −22%.

The first supports a human gate (automatic promotion scores 0/133 on real candidates); the
second gives its cost (the same people grow more lenient as they review). Only the two together
are the complete argument; citing the first alone is selective citation.

Accompanying material, Oversight Has a Capacity (arXiv:2606.08919, unverified), holds that
review attention is a finite pool and that the gate's own escalation policy exhausts it. For a
direction on response, see SAP SE (arXiv:2608.00122, unverified): move approval to the moment
of capture and have the contributor do it — "the Contributor Client initiates task-adjacent
capture with user approval" — addressing the trigger problem and reviewer fatigue at once.

**Current state**: the limitations section now includes reviewer fatigue at +14.5pp and GovMem's
0/133.

## What the argument bears

The sentence that must go into the positioning: **memory governance is load-bearing within the
memory domain, not across the whole agent stack.**

Agent effectiveness is the job of the observe → evaluate → optimize loop; memory governance is
**one input** to that loop. This sentence deflects two classes of objection at once:

- "You did not measure accuracy" — not at this layer. The objective function of governance is
  blast radius, attributability, and revocability.
- "Isn't this just an approval flow" — approval is the means, capture economics is the end.

Why "questioning governance with a 20 vs. 3–8 memory ablation" is a category error: the
objective function of that ablation (arXiv:2603.02473, unverified) is multi-turn dialogue QA
correctness, whereas the objective function of governance is on the poisoning side.

A deduction, so as not to inflate attack figures: an independent replication in 2026-01
(arXiv:2601.05504, unverified) finds that "realistic conditions with pre-existing legitimate
memories dramatically reduce attack effectiveness". What holds up is the diffusion side —
**sharing is precisely the mechanism that turns a local error into a broadcast error**, and the
legitimacy of governance is there, not in the absolute attack success rate.

## On "the industry ignores shared memory": use the defensible version

The strong version ("the industry ignores this axis") breaks on first contact. Do not use it.

In support (the cognitive-psychology lineage genuinely omits it, all unverified): CoALA
(arXiv:2309.02427) has three dimensions — storage, action space, decision procedure — with no
scope dimension at all; the largest 2025–26 survey (arXiv:2512.13564, 47 authors) switches to
forms/functions/dynamics and still has no scope axis; LangChain concedes "Right now, all memory
is specific for that agent. We have no concept of user-level or org-level memory."

Counterexamples that will be used against you (all unverified): the first of the three basic
dimensions in arXiv:2504.15965 is object (personal/system memory); Collaborative Memory
(Accenture, arXiv:2505.18279) already names and formalizes the axis; arXiv:2606.24535 has a
section literally titled "5.2 Memory Scopes"; Databricks states "The scope is required on every
memory entry request". And the axis is 30 years old: Walsh & Ungson (1991) locate memory at
"individual, group and organizational levels", and Nonaka's SECI has an explicit ontological
axis. Bridging work also exists: G-Memory (NeurIPS 2025 spotlight, arXiv:2506.07398) states it
is "inspired by organizational memory theory".

Suggested formulation: **the scope axis is mature in the organizational-memory and governance
lineage and absent from the cognitive-psychology lineage everyone teaches from — it is a gap in
synthesis, not a conceptual vacuum.**

Do not coin terminology. Use memory scope / scoped memory, shared memory tier, collaborative
memory, transactive memory.

## The unciteable list

This is the most reusable section here. The entries below have been traced and found
unsourceable. **Do not write them into any document in this repository.**

| The circulating claim | What tracing it found |
|---|---|
| "68% of wikis have ≥73% outdated pages" (attributed to MIT Sloan 2022, 214 enterprises) | Traces to lifetips.alibaba.com; MITSMR has no such publication. **Judged fabricated** |
| "70–73% of KM projects fail" / "$31.5B lost per year" / "42% of institutional knowledge leaves with people" | All SEO or vendor blogs, no original research |
| "80% of enterprise RAG projects fail badly" / "60% fail on data freshness" / "hallucination rate 10.2%→66.1% (attributed to Google Research)" | The citing pages themselves carry no traceable source |
| "Cursor withdrew its automatic Memories feature" | A single second-hand source only; nothing in the Cursor changelog. Confirm it yourself before citing |
| The material in the section on RAG corpus maintenance | Mostly vendor-adjacent writing. The only rigorous citable sentence is arXiv:2401.05856, "Validation of a RAG system is only feasible during operation." |
| Vendor-published memory benchmark figures (mem0 92.5 / 94.4 and similar) | Treat as marketing unless independently replicated. One replication is known: mem0 claims 93.4% on LongMemEval, measured at 73.8% |

These six rows are not trivia. They are **six figures specific enough to look credible**, with
nothing behind them. This is how the three earlier citation errors in this repository got in.

## Three principles for whoever picks this up

1. **The differentiation is in curation, not authorization.**
2. **The innovation is in capture economics, not the approval flow.**
3. **Do not judge governance by QA accuracy; and do not claim governance improves answer
   quality.**

Both halves of the third matter. Dropping the first half lets irrelevant evidence pull the
argument off course; dropping the second makes the argument promise what it cannot bear.
