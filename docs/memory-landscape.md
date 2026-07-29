# AgentCore Memory Against the Field

> Translation. The primary document is [记忆产品横评](记忆产品横评.md) (Chinese).
> Related: [design-rationale.md](design-rationale.md) · [roadmap.md](roadmap.md)

This document answers two questions: where AgentCore Memory's capability boundary sits
relative to the field, and what this blueprint amplifies when layered on top of it.
Written to the same standard as the rest of this repository: primary sources cited,
AgentCore's shortfalls and competitors' strengths stated plainly, unverifiable claims
marked as such.

Checked 2026-07-29. These products move quickly; re-verify before relying on any row.

## 1. Capability comparison

| | Retrieval | Invalidation | Shared scope | Write gated | Isolation enforced at |
|---|---|---|---|---|---|
| **AgentCore Memory** | Semantic only (cosine), **10 metadata operators + pre-filtering** | **None** (superseding goes through deletion) | Namespace convention | No | **IAM condition keys** |
| **mem0** | **Hybrid: semantic + BM25 + entity matching** | Automatic path is ADD-only; explicit update/delete is yours to call | `user_id`/`agent_id`/`run_id` + `org_id` | No | Application parameter |
| **Zep / Graphiti** | Semantic + BM25 + graph traversal | **Fact Invalidation: invalid-at stored on the edge** | Standalone Graph (vs User Graph) | No | Application |
| **Letta** | Semantic | Versioned blocks | `shared_block_ids`; one agent writes, **others see it immediately** | No (read-only block flag exists) | Application |
| **Vertex Memory Bank** | Semantic | Consolidation with contradiction resolution | Scope, overridable | No (but has a **pre-extraction hook**) | Application |
| **Databricks** | Semantic | — | Scope + Unity Catalog | No (post-hoc CRUD) | UC ACLs |
| **Foundry Agent Memory** | Semantic | TTL + per-item CRUD | Scope | No (post-hoc curation) | Application |

### Where AgentCore is genuinely behind

**1. Retrieval is semantic only — no keyword, no hybrid.** The docs state
`RetrieveMemoryRecords` "performs a semantic search" and that the score "is derived from
the cosine similarity of embedding vectors." The API exposes no BM25, hybrid fusion, or
reranking parameter, and the embedding model is not user-selectable (what *is* selectable
is the **inference** model for extraction and consolidation — a different thing).

This gap is quantified: an ICLR 2026 factorial study found **retrieval method moves
accuracy 20 points (57.1% → 77.2%) against only 3–8 for write strategy**
([arXiv:2603.02473](https://arxiv.org/abs/2603.02473)). mem0's 2026 rewrite went in
exactly the opposite direction from AgentCore: writes reverted to ADD-only, retrieval
became hybrid. **On retrieval quality alone, mem0's and Zep's configurations are stronger
than AgentCore's, and that is a product boundary rather than a usage question.**

For contrast, AgentCore **Registry** advertises "hybrid semantic and keyword search."
Memory does not — this is a deliberate feature split, not an oversight.

**2. No invalidation semantics — and AWS's own documents contradict each other.**

An AWS machine-learning blog states that consolidation "marks the outdated memories as
**INVALID** instead of instantly deleting them," maintaining an immutable audit trail
([deep dive blog](https://aws.amazon.com/blogs/machine-learning/building-smarter-ai-agents-agentcore-long-term-memory-deep-dive/)).
But the API reference's `MemoryRecord` carries only `content`, `createdAt`,
`memoryRecordId`, `memoryStrategyId`, `namespaces`, and `metadata` — **no status or
validity field** — and memory record streaming defines exactly three event types
(`MemoryRecordCreated`/`MemoryRecordUpdated`/`MemoryRecordDeleted`), with consolidation
superseding documented under **deletion**.

> `MemoryRecordOutput` does carry a `MemoryRecordStatus`, but it is a batch-write result
> (SUCCEEDED/FAILED), **not a record lifecycle state**, and must not be cited as
> invalidation.

**Conclusion: there is no customer-visible INVALID status.** An audit trail is yours to
keep (candidate table plus Kinesis streaming into a data lake). Zep's Fact Invalidation
is by contrast a shipped capability: when new data invalidates a prior fact, the time it
became invalid is stored on that fact's edge, and the Context Block carries valid and
invalid dates. **This is a clear Zep advantage over AgentCore.**

### Where AgentCore leads

**1. Isolation is platform-enforced rather than application-disciplined — the most
substantive difference.**

`bedrock-agentcore:actorId` and `bedrock-agentcore:namespace`/`namespacePath` are real
IAM condition keys, composable with `${aws:PrincipalTag/userId}`. Every other product's
scope is a **function argument or a database column**: correct code isolates, incorrect
code leaks.

The difference is not theoretical. Databricks documents the limitation most honestly:
> "Scope is the isolation boundary between users. **Configure the scope in trusted code,
> and never let the model set it. The app service principal can read every scope.**"
([Databricks managed agent memory](https://learn.microsoft.com/en-us/azure/databricks/agents/agent-memory/managed-memory))

"Never let the model set it" hands the security responsibility back to the application;
"the service principal can read every scope" concedes that no per-user boundary exists at
the platform. On AgentCore the same coding error is refused by IAM, because the condition
is evaluated on the AWS side.

**An incident of exactly this class has already occurred.** mem0's **self-hostable
`openmemory/api` component** carries CVE-2026-59705 / EUVD-2026-42126 (CWE-306, CVSS
9.3): routers registered without authentication middleware let an unauthenticated
attacker supply an arbitrary `user_id` to read, write, and delete other users' memories,
or invoke a pause endpoint with `global_pause=true` for denial of service across all users
([ENISA](https://euvd.enisa.europa.eu/vulnerability/EUVD-2026-42126) ·
[GitHub Advisory](https://github.com/advisories/GHSA-xgj7-grxr-prrp)).

> **Scope this precisely**: every authoritative source names only the **self-hostable
> OpenMemory API component**, and **no advisory implicates the hosted mem0 Platform**.
> This is not "mem0 had a critical CVE" but "a self-hosted component was missing
> authentication." CVE-2026-31240 / 31241 are the same class. mem0 also ships optional
> ingestion controls — PII-filtering custom instructions and confidence thresholds —
> which a fair assessment should count.

The value of this case is not to fault a competitor but to show the **structural
difference**: when scope is an application parameter, one missing middleware equals total
privilege escalation; when the boundary is an IAM condition, the same omission is refused.

**2. Pre-filtering architecture — an underrated property.**

The devguide states:
> "**Metadata filters are applied before the vector similarity search runs
> (pre-filtering). This reduces the candidate set first. As a result, the K-nearest
> neighbor (KNN) search operates on a smaller, more relevant subset.**"
([metadata filtering docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/long-term-memory-metadata.html))

With ten operators available (`EQUALS_TO`, `EXISTS`, `NOT_EXISTS`, `BEFORE`, `AFTER`,
`CONTAINS`, `GREATER_THAN`, `GREATER_THAN_OR_EQUALS`, `LESS_THAN`,
`LESS_THAN_OR_EQUALS`; botocore 1.43.58), this means **governance conditions can enter
the retrieval path itself** rather than filtering afterwards.

> **SDK version trap**: releases older than `boto3>=1.43.36` expose only the first three
> operators. This repository's `src/requirements.txt` pins it, but checking capability
> with an older SDK yields the wrong conclusion — this document previously made that
> mistake.

**3. `STRICTLY_CONSISTENT` metadata.** Lets the **application** set metadata values
directly without LLM inference (as against `LLM_INFERRED`). A genuine trusted-write
primitive: governance fields are not model-authored.

**4. A complete managed boundary.** No vector store to run, no external embedding
service, with KMS, VPC, and CloudTrail in place. A self-hosted mem0 deployment needs
Docker plus Qdrant/Postgres plus an external embedding key — three network hops to
persist one fact.

**5. Simple, predictable pricing.** Count-based rather than per-GB: $0.25 per 1,000 events
written, $0.75 per 1,000 records stored per month (built-in strategies) or $0.25 per 1,000
(override and self-managed), $0.50 per 1,000 retrieval calls
([pricing](https://aws.amazon.com/bedrock/agentcore/pricing/), unchanged from mid-2026).
The worked example on that page: 100k events + 10k records + 20k retrievals ≈ $42.50/month.
Self-managed strategies incur your own model charges separately.

**6. A full set of strategies.** userPreference, semantic, summarization, plus
**episodic** (January 2026, with a reflection config), plus built-in override and
`usingSelfManaged`.
> The devguide's long-term-memory page still lists only three and omits episodic — follow
> the [launch blog](https://aws.amazon.com/blogs/machine-learning/build-agents-to-learn-from-experiences-using-amazon-bedrock-agentcore-episodic-memory/)
> instead. The CDK construct marks the strategy enum experimental, which is CDK
> alpha-module status, not service status.

## 2. Governed shared memory: a general absence

After verifying each sharing primitive: **not one of the seven gates a write before it
becomes visible to others.**

- **mem0** — `user_id`/`agent_id`/`run_id` composed at retrieval, with
  `org_id`/`project_id` as tenancy containers. Scope-widening, no review step.
- **Zep** — write to a standalone Graph (current docs say "Graph" vs "User Graph"; the
  "group graph" name is outdated). Ungated.
- **Letta** — `shared_block_ids`: "When one agent updates the block, **all others see the
  change immediately**." Explicitly post-hoc ("Any agent can append learnings"). Read-only
  blocks are the closest thing to a gate in this set, but that is a read/write flag, not a
  review workflow.
- **Databricks** — scope plus Unity Catalog ACLs and audit; the write itself is ungated.
- **Vertex Memory Bank** — `direct_memories_source` lets "your agent **or a
  human-in-the-loop** be responsible for extracting memories," the only managed service
  leaving room for a human step. But that is a hook on **extraction**, not an approval
  before visibility, and pre-extracted facts are capped at 5 per call.
- **Foundry** — scope plus per-item memory CRUD (preview). Microsoft's own
  memory-poisoning guidance is post-hoc and defensive, and notes that "a memory scoped to
  one authenticated user has a very different risk profile from memory scoped to a team,
  tenant, or application."
- **LangGraph/LangMem** — not verified this pass; treated as unverified.

> This blueprint therefore fills an absence that several parties have named independently
> without anyone shipping it. Full basis in the positioning note in
> [roadmap.md](roadmap.md).

## 3. What this blueprint amplifies

Three places where the governance design and the platform reinforce each other rather
than merely coexisting.

**1. Governance conditions enter the retrieval path instead of filtering after it.**
`src/agent/context_builder.py` retrieves shared memory with two metadata filters,
`project_id` and `review_status=approved`. Under pre-filtering, unapproved, rejected, and
superseded records **never enter the similarity contest** — they are not scored and then
discarded. "Only reviewed knowledge is retrievable" thus moves from an application
convention to a structural property of retrieval, and the smaller candidate set brings an
accuracy benefit the devguide calls "measurably better accuracy."

**2. Verbatim publication turns AgentCore's biggest weakness into a non-issue.**
On approval the shared tier writes through `BatchCreateMemoryRecords` with no second
extraction. Two consequences: the reviewer's text is byte-identical to the stored record,
so the audit chain holds; and **AgentCore's extraction quality carries no risk in the
shared tier**, because the shared tier does not use extraction. For the personal tier, any
extraction weakness is bounded by IAM to a single actor. The platform's extraction
uncertainty is confined by the layering to the low-consequence tier.

**3. A discrete status flag for supersession sidesteps both the platform gap and the
field's open problem.**
AgentCore has no invalidation semantics (see the documentation conflict above); Zep does,
but adopting it means changing stacks. This blueprint's approach: when a reviewer approves
a candidate carrying `supersedes`, `BatchUpdateMemoryRecords` flips the old record's
`review_status` to a terminal value, which removes it from the retrievable set — because
retrieval pre-filters on `review_status=approved` — while the record itself is retained
for audit.

This step deliberately **introduces no LLM adjudicator**. The field's record here is poor:
conflict resolution is the lowest-scoring category for at least one graph-based memory
system precisely because the contradiction judgment is an LLM call
([arXiv:2606.01435](https://arxiv.org/html/2606.01435)), and work on stale knowledge
reports that frontier models handle implicit invalidation badly and often accept stale
premises embedded in a question
([arXiv:2605.06527](https://arxiv.org/abs/2605.06527)). This blueprint already has a human
decision point with an audit trail; extending it costs one field and one workflow branch.

**Cost pragmatics.** The governance path adds almost nothing to Memory spend: review
happens on candidates, which live in DynamoDB, and shared records are counted in
"conclusions the team settled," typically a small fraction of personal memory. The real
cost is FM inference — and the shared tier performs no extraction, which removes that
portion entirely.

## 4. Practical guidance: when to choose what

**AgentCore plus this blueprint**: several users share one agent, team knowledge needs
accountability, you are already on AWS, and compliance wants auditable cross-session
authority. The reason is platform-enforced isolation and a gateable write path.

**mem0 or Zep**: single-user or weak-isolation settings, retrieval quality first, hybrid
or exact keyword matching required, no cloud lock-in. Zep additionally has Fact
Invalidation, which AgentCore lacks.

**Layering is the most pragmatic option.** The four knowledge layers permit different
backends per tier: the personal preference tier could run on mem0 or Zep for better
extraction and retrieval while the shared tier keeps the IAM-plus-review properties. The
precedence rule does not weaken when the personal tier changes implementation.

**When exact keyword matching is required (ticket IDs, error codes, SKUs), do not force it
into Memory.** Semantic retrieval is not good at that class. The right home is the
Knowledge Base layer — Bedrock KB supports hybrid — and the layering already reserves a
place for this need. That is the practical return on layering: a capability gap can be
housed instead of distorting one tier's purpose.

## 5. Unverified and to re-check

- Whether AgentCore consolidation has an **undocumented** internal INVALID state. The AWS
  blog and API documentation conflict; this blueprint follows the API documentation and
  does not depend on the behaviour. Worth confirming with the service team.
- No explicit "GA" statement was found for the episodic strategy; treated per the launch
  blog.
- LangGraph/LangMem sharing primitives were not verified this pass.
- Whether the three mem0 CVEs have a fixed release could not be confirmed: the commit
  cited as the fix is the vulnerable HEAD, and primary sources recommend network isolation
  and an authenticating reverse proxy as mitigation.
