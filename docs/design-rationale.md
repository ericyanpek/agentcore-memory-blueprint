# Design Rationale: Why These Choices

> Translation. The primary document is [设计取舍依据](设计取舍依据.md) (Chinese).
> Related: [architecture.md](architecture.md) ·
> [roadmap.md](roadmap.md)

This document records why the blueprint makes four specific choices, and what
external evidence supports or contests each one. It is written to be falsifiable:
each claim names a source, and claims that could not be verified are marked as such.

The blueprint was designed before this evidence was collected. The purpose of this
document is to state which design decisions survive external scrutiny, and which
ones are merely conventions that happen not to have been challenged yet.

## 1. Verbatim publication instead of a second extraction pass

**The choice.** On approval, `BatchCreateMemoryRecords` stores the reviewed
statement unchanged (`src/blueprint/memory.py`). No extraction model rewrites it.
The reviewer's text is byte-identical to the stored record.

The original motivation was auditability: if a second model paraphrases an approved
statement, the reviewer did not actually approve what is stored, and the audit trail
becomes a claim rather than a fact.

**Independent support for the performance side of this choice.** A factorial study
(ICLR 2026) crossing three write strategies — raw chunks, mem0-style extraction,
MemGPT-style summarization — against three retrieval methods reports that the
retrieval method dominates: average accuracy spans 20 points across retrieval
methods (57.1% to 77.2%) but only 3–8 points across write strategies, and raw
chunked storage with zero LLM calls matches or outperforms the lossy alternatives
([arXiv:2603.02473](https://arxiv.org/abs/2603.02473), code at
[memory-probe](https://github.com/boqiny/memory-probe)). Failure analysis in the same
paper locates most breakdowns at the retrieval stage rather than at utilization.

The paper's own stated limitations matter for how far this generalizes: a single
backbone model, a single benchmark, a fixed retrieval budget, prompt-based
reimplementations rather than fully learned memory systems, and LLM judges for
correctness. It explicitly notes that raw chunking's advantage **may diminish under
tighter context budgets** where compression becomes necessary — which is the same
budget dependence recorded in section 2 and in [roadmap.md](roadmap.md) item 5.

**Market evidence in the same direction.** mem0's 2026 algorithm revision removed
`UPDATE` and `DELETE` from its write path in favour of a single-pass append,
deferring contradiction handling to ranking time
([mem0 memory evaluation docs](https://docs.mem0.ai/core-concepts/memory-evaluation)).
A vendor whose differentiator was write-time adjudication retreated from write-time
adjudication.

**Countervailing evidence.** Uniform append-only stores accumulate low-value
records over long horizons, and at least one study reports retrieval quality
decaying over multi-week usage where a learned write policy holds up better
([arXiv:2606.21144](https://arxiv.org/html/2606.21144)). The reconciliation the
blueprint adopts: **gate admission, do not rewrite representation.** The policy
gate and human review control *whether* a statement is admitted; neither alters
*how* it is worded.

## 2. Deterministic retrieval precedence

**The choice.** `docs/architecture.md` fixes a total order — live data and tool
results, then Skills and configuration in Git, then Knowledge Base documents, then
approved shared memory, then personal preference, then model inference. Higher
layers override lower ones. Memory can never override current data.

**Why this matters more than it appears.** Three documented failure modes make an
unordered context assembly actively harmful, not merely suboptimal:

- **Position sensitivity.** Evidence placed mid-context is recovered substantially
  less reliably than evidence at either end
  ([Liu et al., TACL 2024](https://arxiv.org/abs/2307.03172)).
- **Distractor similarity.** Long-context degradation worsens when distractors are
  semantically close to the answer — which is the defining characteristic of a
  populated memory store, since memory is retrieved *because* it is similar.
- **Experience following.** Agents reproduce the quality of what they retrieve. A
  store containing a stale or poisoned record yields output that faithfully
  reflects it.

A precedence rule converts "which memories are relevant" into "which authority
wins", and the second question has a deterministic answer while the first does not.

**Where the blueprint is currently silent.** Precedence orders *layers*; it does not
bound *volume*. `src/agent/context_builder.py` has no context budget. Retention
versus consolidation is budget-dependent with a measured crossover — retention
performs well under loose budgets and degrades sharply under tight ones
([arXiv:2607.17545](https://arxiv.org/html/2607.17545v1)). See
[roadmap.md](roadmap.md) item 3.

## 3. Human review as an anti-poisoning control

**The choice.** No path exists from an agent or a desktop client to the shared
Memory resource. Only the publisher Lambda holds
`bedrock-agentcore:BatchCreateMemoryRecords`, and it is invoked only from the
approved branch of the review workflow.

**This addresses a demonstrated attack class, not a hypothetical one.**

- **MINJA** injects malicious records into an agent's memory bank using ordinary
  queries only, requiring no privileged access to the store. The paper reports high
  injection and downstream attack success rates, and finds that conventional
  defences — including guard models, embedding sanitization, and prompt-based
  detection — do not reliably prevent it
  ([arXiv:2503.03704](https://arxiv.org/abs/2503.03704), NeurIPS 2025).
- **Reported incidents.** Publicly discussed cases include SpAIware, LayerX's
  "Tainted Memories" write into ChatGPT Atlas memory, and Radware's "ZombieAgent".
  Most directly relevant to this blueprint: **MemoryTrap**, reported and remediated
  against Claude Code, where a single poisoned memory object propagated across
  sessions, users, and subagents
  ([Help Net Security, 2026-04-14](https://www.helpnetsecurity.com/2026/04/14/idan-habler-cisco-agentic-ai-memory-attacks/)).

Since this blueprint's desktop integration is specifically about Claude Code and
Codex CLI sharing one cloud memory, MemoryTrap is the precedent that justifies
gating the shared write path rather than trusting client behaviour.

**Scope limit, stated precisely.** Review covers the **shared tier only**. Personal
long-term memory is written by AgentCore's own extraction with no review step, and
short-term events are written directly. A poisoned personal preference is confined
to one actor by IAM, but it is not reviewed. This is a deliberate boundary, not an
oversight — reviewing every personal preference would make the system unusable — but
it should not be described as "memory is reviewed".

## 4. Two Memory resources instead of one

**The choice.** `PersonalMemory` and `SharedProjectMemory` are separate resources,
so the boundary between them is expressible as a resource ARN in an IAM policy
rather than as a namespace convention checked in application code.

**AWS's own guidance supports namespace- and IAM-based scoping** as the primary
isolation mechanism for AgentCore Memory
([Organizing agents' memory at scale](https://aws.amazon.com/blogs/machine-learning/organizing-agents-memory-at-scale-namespace-design-patterns-in-agentcore-memory/)).
The blueprint goes one step further by separating resources, which makes
"the desktop role cannot write shared memory" a statement about a *resource* the
role has no action on, rather than a statement about a *string comparison* that has
to be correct everywhere.

**What this does not buy.** Resource separation protects the shared tier. It does
not isolate users from each other inside the personal resource. That requires the
per-actor IAM conditions demonstrated in `poc/validate_identity_pool.py`, which the
Runtime role does not currently carry. See `docs/architecture.md` and
[roadmap.md](roadmap.md) item 2.

## 5. On evaluating memory quality

The blueprint validates **governance properties** (isolation holds, the gate
blocks, tokens do not replay). It does not claim that memory improves answer
quality, and it should not begin claiming so by citing standard benchmark numbers.

Published memory benchmarks have documented methodological problems:

- **LoCoMo.** An independent audit reports 99 score-corrupting ground-truth errors
  across 1,540 questions (6.4%), placing the honest ceiling near 93–94% rather than
  100%; the same audit finds the `gpt-4o-mini` judge accepts 62.81% of
  deliberately wrong but topically adjacent answers, with vague answers passing far
  more often than specific factual errors
  ([audit](https://penfieldlabs.substack.com/p/we-audited-locomo-64-of-the-answer),
  [data](https://github.com/dial481/locomo-audit)). For calibration, Northcutt et
  al. (NeurIPS 2021) found ~3.3% label error across ten major benchmarks was enough
  to destabilize rankings.
- **LongMemEval-S.** Each question's corpus fits within current frontier context
  windows, which makes it closer to a context-window test than a memory test
  ([same source](https://penfieldlabs.substack.com/p/proposal-a-new-benchmark-for-long)).
- **Vendor figures are mutually contested.** Published reproductions of competitor
  scores differ substantially from the originals in both directions
  ([getzep/zep-papers#5](https://github.com/getzep/zep-papers/issues/5)).

If this blueprint later measures quality, the defensible protocol is: task-level
success rather than recall, a verbatim-RAG baseline, a random-retrieval control, and
disclosure of the embedding model and write-path cost. Benchmarks that score
extraction, updating, and QA separately — such as HaluMem
([arXiv:2511.03506](https://arxiv.org/abs/2511.03506)) — are more diagnostic than a
single aggregate number, because they localize where errors originate.

## 6. Long context does not remove the requirement

Large context windows weaken the *token-cost* argument for retrieval-based memory
and do not weaken the *governance* argument. Long context cannot provide
cross-session persistence, per-record authority, or an audit trail linking a
statement to an approver and evidence. Prompt caching reduces cost but does not
address position sensitivity or distractor similarity, because cached long context
is still long context.

The durable justification for this design is therefore auditable, governed,
cross-session authority — not token economics. That framing survives the next
increase in context window size.

## Unverified and open

- Whether AgentCore's managed consolidation performs any **undocumented**
  supersession beyond the de-duplication and superseding referenced in the memory
  record streaming documentation. The behaviour is not specified as a contract, so
  the blueprint does not depend on it.
- The often-quoted claim that injecting an order of magnitude more records sharply
  reduces accuracy was traceable only to secondary sources during this review and
  is therefore treated as directional, not load-bearing.
