# Roadmap: Next Evolution

> Translation. The primary document is [下一步演进](下一步演进.md) (Chinese).
> Related: [design-rationale.md](design-rationale.md) ·
> [architecture.md](architecture.md) · [AWS 官方背书](AWS官方背书.md)

Items are ordered by whether they close a gap between what the documentation claims
and what the code enforces (items 1–2), extend the governance model into a dimension it
does not yet cover or make it actually get used (items 3–6), harden the validation
methodology (item 7), or come from the AWS Well-Architected Agentic AI Lens rather than
from self-review (items 8–9, grouped separately because their basis is an external
framework).

Each item states the current behaviour, the target behaviour, and the affected files.
Severity uses the same scale as the production-gap tables in
[实验报告](实验报告.md) and [桌面客户端集成设计](桌面客户端集成设计.md).

---

## 1. Enforce evidence immutability at the proposal gate — severity: high

**Current behaviour.** `src/blueprint/domain.py` validates only that
`evidence_ref` begins with `trace://`, `s3://`, or `log://`. It does not require an
S3 reference to pin a `versionId`, to point at the audit bucket, or to sit under the
proposer's own prefix.

`bridge/server.py` returns a version-pinned reference from
`memory_capture_evidence`, and `docs/桌面客户端集成设计.md` section 6 documents that
pinning is what makes evidence tamper-evident. However, pinning is currently a
property of the *capture helper*, not a *precondition for acceptance*. A proposal
carrying an unpinned reference is accepted; the object behind it can then be
overwritten, since overwriting the same key is permitted by design (deletion is
denied, overwriting is not). A reviewer following the reference after approval would
resolve to the latest version.

This is a documentation-versus-code gap: the immutability property is claimed
unconditionally but holds only when the client cooperates.

**Target behaviour.** Reject at validation time any `s3://` evidence reference that
does not (a) carry a `versionId` query parameter, (b) name the configured evidence
bucket, and (c) fall under the proposer's own `evidence/user:<sub>/` prefix. Bucket
name and prefix derive from server-side configuration and the authenticated `sub`,
never from the request body.

**Files.** `src/blueprint/domain.py` (validation), `src/handlers/propose_candidate.py`
(pass the expected bucket), `tests/test_domain.py`, `bridge/validate_bridge.py`
(the well-formed-proposal fixture currently uses an unpinned reference and must be
updated, or the new rule will reject it).

---

## 2. Separate proposing from approving — severity: high

**Current behaviour.** `src/handlers/reviewer_api.py` authorizes on reviewer group
membership only. There is no check that the approver is not the proposer, and
proposals and reviews are served from the same Cognito user pool. A user in the
reviewer group can propose a statement and approve it.

Because human review is the control that the rest of the design depends on, a
self-approval path reduces the two-party guarantee to a one-party one.

**Target behaviour.** Reject a decision whose `reviewer_id` matches the candidate's
`proposer_actor_id`, returning a distinct status code so the refusal is
distinguishable from an authorization failure in logs and tests. For deployments
with too few reviewers to make this practical, make the rule a deployment parameter
that defaults to enforcing separation, and record the exception explicitly.

**The platform has already shown this boundary can move down into IAM.** The approach above
is an application-layer check; testing confirms AgentCore splits submission and adjudication
into two independent actions on Registry, so IAM can enforce the separation instead of code
being trusted to:

| Credential | Attempt to propose | Attempt to approve |
|---|---|---|
| Holds only `SubmitRegistryRecordForApproval` | allowed | **AccessDeniedException** |
| Holds only `UpdateRegistryRecordStatus` | **AccessDeniedException** | allowed |

For this project that means the proposal Lambda and the review Lambda should hold
non-overlapping action sets, making self-approval impossible at the IAM layer rather than
merely refused by application code. This is standard AWS practice and not expensive, but it
requires splitting the current single reviewer Lambda — hence a direction rather than an
immediate change.

**Files.** `src/handlers/reviewer_api.py`, `tests/test_reviewer_api.py`,
`infra/lib/memory-governance-stack.ts` (splitting the Lambda and its policies), the
Permissions section of `docs/architecture.md`.

Related: reviewer group membership is enforced in Lambda code rather than at the
API Gateway authorizer, which validates the token but not the group claim. Moving
the group check into a request authorizer would remove the dependency on handler
dispatch order.

---

## 3. State the policy gate's actual scope, then extend it — severity: medium

**Current behaviour.** `docs/architecture.md` states that candidates containing raw
credentials, restricted data, or direct personal information are rejected before
human review. The implemented gate is
`privacy_classification != "restricted" and confidence >= 0.70`
(`src/blueprint/domain.py`) — a self-declared label and a self-declared score. There
is no content inspection. A credential labelled `internal` with confidence 0.9
reaches the review queue.

The experiment's finding that a 0.98-confidence restricted candidate is still
blocked demonstrates that **classification outranks confidence**. It does not
demonstrate content detection.

**Target behaviour, in two steps.** First, correct the documentation to describe a
declared-classification gate, because the current wording overstates it. Second, add
actual pre-review inspection: pattern matching for credential shapes and a Bedrock
Guardrail policy applied both before storage and before injecting memory into a
prompt. Guardrails are already listed as a production gap in both reports; this
gives them a specific insertion point.

**Files.** `docs/architecture.md` and `docs/架构设计.md` (wording), `src/blueprint/domain.py`
(inspection), `src/handlers/propose_candidate.py` (Guardrail invocation).

---

## 4. Supersession: give approved facts a validity lifecycle — severity: medium

This is the largest capability gap and the one with no partial implementation.

**Current behaviour.** An approved shared record is immutable and effectively
permanent within the 90-day resource expiry. There is no way to mark it as no longer
true. If the curated-churn-view constraint that the experiment approves is corrected
next quarter, the old record remains retrievable and indistinguishable from a current
one. Record-level TTL does not solve this: an expiring record and a fresh record rank
identically until the moment it disappears.

**What the platform provides.** This is implementable without leaving AgentCore:

- `BatchUpdateMemoryRecords` accepts `memoryRecordId`, `content`, `metadata`,
  `namespaces`, and `timestamp`, so an existing record's metadata can be rewritten.
- `DeleteMemoryRecord` and `BatchDeleteMemoryRecords` exist for hard removal.
- Memory record streaming publishes create, update, and delete events to Kinesis,
  including deletions caused by consolidation de-duplication and superseding.

**Filtering capability available.** Metadata filters support ten operators:
`EQUALS_TO`, `EXISTS`, `NOT_EXISTS`, `BEFORE`, `AFTER`, `CONTAINS`, `GREATER_THAN`,
`GREATER_THAN_OR_EQUALS`, `LESS_THAN`, `LESS_THAN_OR_EQUALS` (botocore 1.43.58 service
model). **Mind the SDK version**: releases older than the `boto3>=1.43.36` pinned in this
repo's `src/requirements.txt` expose only the first three, so range filters written
against an older SDK are rejected by local validation.

Because `BEFORE`/`AFTER` exist, a validity window **can** be expressed as a timestamp
filter. The blueprint still models supersession as a **discrete status flag**, for audit
reasons rather than capability ones:

- Add `superseded_by` and set `review_status` to a terminal value such as
  `superseded` on the old record via `BatchUpdateMemoryRecords`.
- Retrieval already filters `review_status = approved`
  (`src/agent/context_builder.py`), so a superseded record leaves the retrievable set
  with no change to the query path.
- Keep both records. The audit trail requires knowing what the team believed and
  when, which a hard delete destroys.

**Use the status name AgentCore already has rather than inventing one.** The approval state
machine on AgentCore Registry already has a terminal state called `DEPRECATED`, and testing
confirms the platform itself treats it as terminal — any status change on a record in that
state is refused:

```
Cannot update registry record in DEPRECATED status (terminal state)
```

What is worth borrowing here is not the API but **its modelling choice for supersession**:
superseded knowledge is not deleted but moved into a state that can no longer change, so it
leaves the currently-valid set while staying in the audit record. That runs in the same
direction as the "keep both records" argument above and supplies an official vocabulary — so
this project should adopt `DEPRECATED` rather than coin `superseded`, on the grounds that one
concept inside one service should have one name.

**Borrow the name and the terminal semantics only, not the transition rules.** Testing
Registry's transition matrix surfaced two behaviours that do not suit knowledge governance:
`REJECTED → APPROVED` is permitted (a rejection can be silently overridden with no
re-review), and replaying `APPROVED → APPROVED` succeeds. This project's one-time callback
token returns 409 on replay (check 11 in [实验报告](实验报告.md)), which is stricter than
Registry and should not be relaxed to match it.

**Route the decision through the existing review workflow, not through a model.**
Add an optional `supersedes: <record_id>` field to the candidate contract. Approving
such a candidate publishes the new record and, in the same workflow branch, flips the
old record to `DEPRECATED`. The reviewer decides what supersedes what.

This last point is deliberate. Automated contradiction detection is the weakest
component in comparable systems: reported conflict-resolution scores are the lowest
category for at least one graph-based memory system precisely because the
contradiction judgment is an LLM call
([arXiv:2606.01435](https://arxiv.org/html/2606.01435)), and work on stale-knowledge
handling reports that frontier models handle implicit invalidation — a fact
negated with no explicit contradiction — poorly, and often accept stale premises
embedded in a question
([arXiv:2605.06527](https://arxiv.org/abs/2605.06527)). The blueprint already has a
human decision point with an audit trail; extending it costs one field and one
workflow branch, and avoids adding an unreliable adjudicator.

For comparison, the reference design for full temporal modelling is Zep/Graphiti's
bi-temporal edge model, which separates when a fact was true from when the system
learned it, and invalidates rather than deletes
([arXiv:2501.13956](https://arxiv.org/abs/2501.13956)). Zep's current product docs
document Fact Invalidation directly: when new data invalidates a prior fact, the time it
became invalid is stored on that fact's edge. **AgentCore has no equivalent**, which is
why this project must implement supersession itself.

One factual discrepancy worth stating plainly: an AWS machine-learning blog says
consolidation "marks the outdated memories as INVALID instead of instantly deleting
them," maintaining an immutable audit trail. But the API reference's `MemoryRecord`
carries only `content`, `createdAt`, `memoryRecordId`, `memoryStrategyId`, `namespaces`,
and `metadata` — **no status or validity field** — and memory record streaming defines
exactly three event types (`MemoryRecordCreated`/`MemoryRecordUpdated`/
`MemoryRecordDeleted`), with consolidation superseding documented under **deletion**.
AWS's own blog and API documentation therefore disagree. This blueprint follows the API
documentation: it **relies on no platform-side INVALID semantics**, and keeps the audit
trail in the candidate table and via Kinesis streaming. (`MemoryRecordOutput` does carry
a `MemoryRecordStatus`, but that is a batch-write result of SUCCEEDED/FAILED, not a
record lifecycle state, and must not be cited as invalidation.)

**Files.** `contracts/memory-candidate-proposed.json`, `src/blueprint/domain.py`,
`src/blueprint/memory.py` (an update path alongside the publish path),
`src/handlers/publish_shared.py`, `infra/lib/memory-governance-stack.ts` (the
publisher role needs `BatchUpdateMemoryRecords` under the same exact-namespace
condition), `dashboard/` (surface superseded records distinctly).

---

## 5. When to propose, and what qualifies — severity: high

**Current behaviour.** The proposal contract itself is complete: five `category`
values, confidence, privacy classification, `promotion_hint`, and an immutable
`evidence_ref` are all enforced in `src/blueprint/domain.py`. But **nothing tells the
model when to propose or what is worth proposing.**

`memory_propose_shared` is an ordinary MCP tool, so the model decides when to call it
based solely on the tool's description. The judgment criteria are now in that
description (change 1 below), but **the trigger still has no mechanism**: no hook
evaluates a completed turn for anything worth proposing, and the single Skill under
`skills/` is unrelated to proposal judgment. Proposing therefore still depends on the
user asking, or on the model noticing unprompted.

This is a usability gap rather than a security one, but its reach is larger: **if
nobody proposes, the whole governance mechanism idles** — the review queue stays empty
and shared memory never accumulates. The candidates in the experiment report were
produced by a script calling the API directly, not proposed by an agent.

**Target behaviour, two independent changes.**

1. **Convey the judgment criteria to the model — done.** The
   `memory_propose_shared` docstring now defines each `category` (`fact` is an
   observation that holds independently of any one task; `decision` includes what it
   rules out; `constraint` is a definitional trap that silently produces wrong answers
   when violated; `incident` is a confirmed failure with its cause; `procedure_hint` is
   a reusable operational step), and states explicitly what should **not** be proposed:
   the model's own formatting or tooling preferences, details specific to one task,
   restated documentation, and unverified guesses. It also says confidence must not be
   inflated to force a submission through, when `restricted` is required, and to call
   `memory_capture_evidence` first for a version-pinned reference.
   `bridge/validate_bridge.py` gained an assertion that the **semantics** — not merely
   the names — appear in the description returned by `tools/list`, so the change cannot
   silently regress.
2. **Capture evidence automatically with a hook — not done.** The model must still call
   `memory_capture_evidence` for an `s3://` reference before calling
   `memory_propose_shared`; skipping the first step means the proposal is rejected on
   evidence validation — safe but poor ergonomics (already recorded in
   [桌面客户端集成设计](桌面客户端集成设计.md) section 11). A hook that captures evidence
   at the end of each turn keeps evidence always ready, leaving the model only the
   judgment of whether a statement is worth proposing.

The division of labour: change 1 addresses the judgment itself (done), change 2 removes
the prerequisite burden (outstanding).

**Remaining files.** `.mcp.json` and hook configuration (automatic evidence capture);
optionally `skills/`, to give the same criteria to runtimes that do not read MCP tool
descriptions.

> `poc/runtime_agent.py` is deliberately excluded: it has no proposal tool at all, and
> its system prompt only governs consuming shared memory. The proposal capability exists
> only in the desktop bridge.

---

## 6. Freshness signalling and context budget — severity: medium

**Current behaviour.** `src/agent/context_builder.py` requests a fixed `topK` and
injects what returns. Record age is available — `RetrieveMemoryRecords` returns
`createdAt` per record — but is not used for ranking, display, or review triggers.
There is no cap on how much memory enters the prompt.

**Target behaviour.** Three separable changes:

- **Surface age at injection.** Label each injected shared record with its
  `createdAt` so the model and any human reading a trace can see that a statement is
  eight months old. This is a presentation change with no retrieval cost.
- **Trigger re-review by age.** Emit a periodic event listing approved records past a
  configurable age into the reviewer queue for confirmation or supersession. This
  makes item 4 operational rather than reactive.
- **Bound the context budget.** Make the number of injected records a configured
  parameter with a documented default, since the retention-versus-consolidation
  trade-off is budget-dependent
  ([arXiv:2607.17545](https://arxiv.org/html/2607.17545v1)).

Deliberate non-goal: automatic deletion by age. Decay belongs in ranking and in
review triggers, not in silent removal of audited records.

---

## 7. Close the remaining vacuous assertions — severity: medium

Both reports document a methodological lesson: security assertions must verify that
what should be blocked is blocked *and* that what should exist exists, and must check
the **reason** for a failure rather than only its occurrence. Several checks do not
yet meet that standard.

- `bridge/validate_bridge.py`: the evidence-tamper assertions test
  `!= "ALLOWED"`, which any `ClientError` satisfies — including a misspelled bucket
  or `NoSuchBucket`. Assert `== "AccessDenied"`.
- `bridge/validate_bridge.py`: the non-reviewer refusal asserts only
  `ok is False`, which a DNS failure, a 404, or a 500 also satisfies. Assert the 403.
- `bridge/validate_bridge.py`: the empty-namespace cross-user check is retained
  alongside the direct permission probe that replaced it. The probe is the real test;
  keeping the weaker check inflates the count.
- `bridge/server.py`: `AccessDeniedException` is reported to the user as a
  cross-user or shared-write violation regardless of cause, so a KMS or
  configuration error is narrated as an attempted boundary crossing. Report the
  actual error code.
- `infra/test/`: the CDK tests are largely `JSON.stringify(template).toContain(...)`
  substring checks. The strongest claim in the README — that the runtime role holds
  no write action on shared memory — has no test. Add assertions for that, for the
  absence of `Resource: "*"` on any `bedrock-agentcore:` action, for KMS encryption
  on both DynamoDB tables, and for the `RETAIN` removal policies the deployment notes
  depend on.

---

## 8. Add a timeout escalation path for review — severity: high

**Basis.** This item comes from the AWS Well-Architected Agentic AI Lens rather than from
self-review. [AGENTSEC04-BP02](https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentsec04-bp02.html)
names the absence directly as an anti-pattern:

> "Implementing approval workflows **without timeout policies or escalation paths**, so
> agent execution stalls indefinitely when reviewers are unavailable."

And states the implementation requirement:

> "In Step Functions, TimeoutSeconds or HeartbeatSeconds on the task state waiting for the
> approval token triggers a timeout transition, and **Catch clauses route timed-out
> executions to an escalation state** (notify secondary reviewers, escalate to management,
> or **default to a safe fallback, typically blocking the operation**)."

**Current behaviour.** `WaitForHumanReview` sets a 7-day `taskTimeout`
(`infra/lib/memory-governance-stack.ts`) but has no `addCatch`. On timeout the execution
fails with an uncaught error and the candidate **stays at `PENDING_REVIEW` forever** — no
terminal status is written, so the review queue keeps showing it as pending while the
workflow is dead. One execution was stranded this way during development, and it blocked
CloudFormation cleanup.

**Target behaviour.** Add `addCatch` for `States.Timeout` routing to a new `MarkTimedOut`
terminal state that writes an explicit status (for example `REVIEW_TIMED_OUT`). The safe
fallback is rejection, not admission — unapproved knowledge must not reach shared memory.
The callback record should be settled at the same time so no `WAITING` row lingers.

**Affected files.** `infra/lib/memory-governance-stack.ts` (`createReviewWorkflow`),
`src/handlers/mark_status.py`, `infra/test/memory-governance-stack.test.ts`.

---

## 9. Score against the AGENTSEC01 maturity model and close the gaps — severity: medium

**Basis.** [AGENTSEC01 Secure agent memory and state](https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentsec01.html)
publishes a five-level maturity model, which serves as an external yardstick rather than a
self-invented score.

**Current standing.** Item by item, this blueprint sits **between Level 3 and Level 5**:

| Level | Requirement | This blueprint |
|---|---|---|
| 3 | Hierarchical namespace schemas with per-actor and per-session placeholders | Present |
| 3 | Multi-layer validation: schema checks plus Guardrails policy and PII filtering plus contextual grounding checks | **Schema and declared labels only**; no Guardrails, no PII filtering, no grounding checks |
| 4 | KMS-backed HMAC integrity verification on every read | **Absent** |
| 4 | All write paths share one validation pipeline, including tool outputs and inter-agent messages | Partial: the shared path has a gate, personal writes do not |
| 4 | CloudWatch anomaly detection plus an EventBridge hallucination circuit breaker | **Absent** |
| 5 | Routine red-team exercises simulating poisoning and propagation | **Absent** |
| 5 | Memory governance is codified and auditable | Present — this is the core of the project |

**The inversion worth naming.** Level 5 governance is in place while Level 3 Guardrails and
Level 4 integrity verification are missing. Governance runs deep; content safety and
runtime integrity remain shallow — the same finding as section 9 of
[实验报告](实验报告.md) ("the policy gate reads declared labels, it does not inspect
content"), now confirmed by an external yardstick.

**Target behaviour.** In priority order: Guardrails and PII filtering first (Level 3, which
also narrows the policy-gate scope in item 3), then red-teaming (Level 5, reusing the
[MINJA](https://arxiv.org/abs/2503.03704) and
[GhostWriter](https://arxiv.org/abs/2607.06595) techniques to measure poisoning
resistance). Per-read HMAC verification (Level 4) is costly and should be evaluated only
after the threat model is explicit.

**Affected files.** `src/blueprint/domain.py` (gate),
`infra/lib/memory-governance-stack.ts` (Guardrails integration), a new red-team validation
script.

---

## Also worth doing

- **Remove `USER_PASSWORD_AUTH`.** `infra/lib/memory-governance-stack.ts` enables
  both `userPassword` and `userSrp`. SRP alone is sufficient, and the password flow
  is unnecessary attack surface. The bridge's use of password auth is already
  recorded as a POC gap; moving it to an authorization-code flow with PKCE removes
  the need for the flow entirely.
- **Reconsider the evidence-bucket deny statement.** The policy uses `NotPrincipal`
  with `AccountRootPrincipal`. AWS guidance recommends `ArnNotEquals` on
  `aws:PrincipalArn` for this pattern; the current form exempts more than intended.
  The version-pinned reference from item 1 is the mechanism actually providing
  immutability, and the bucket policy should not be described as if it were.
- **Validate `session_key` in the bridge.** It is client-supplied and reaches the
  summarization strategy's `{sessionId}` namespace template unvalidated. The blast
  radius is confined to the caller's own subtree by the retrieval condition, but the
  claim that no tool accepts a namespace parameter holds only at the level of
  parameter names.
- **Constrain the reviewer API's candidate listing.** It scans; a status GSI is the
  documented follow-up once candidate volume grows.
- **Split shared memory by write path.** Human-authored procedural knowledge and
  LLM-extracted team facts are different governance objects and plausibly warrant
  different gates. Anthropic documents `CLAUDE.md` as source-controlled procedural
  memory operating alongside agent-written memory; Thomson Reuters describes
  promoting a proven method into a reviewable `SKILL.md` gated behind a knowledge
  manager's approval and versioned
  ([Thomson Reuters](https://blogs.thomsonreuters.com/legal-blog/fiduciary-standards-for-legal-agentic-memory-systems/)).
  The `skills/` directory already represents the destination; the distinction is not
  yet stated as an explicit governance boundary in `docs/architecture.md`.

---

## Positioning note

Shared-scope primitives exist across the ecosystem — group graphs, shared memory
blocks, multi-scope tags, namespace tuples — but they widen read and write scope
rather than gating the write. Managed offerings provide post-hoc curation, such as
memory CRUD interfaces and delete APIs, which correct a bad record after it lands.
An automated pre-write gate combined with human approval and IAM-enforced isolation
was not found as a native capability in any surveyed product as of July 2026.

The absence is being named independently: a computer-architecture perspective on
multi-agent memory identifies a missing *agent memory access protocol* defining
read/write semantics, permissions, scope, and granularity as one of two absent
protocol pieces
([SIGARCH](https://www.sigarch.org/multi-agent-memory-from-a-computer-architecture-perspective-visions-and-challenges-ahead/)),
and the Thomson Reuters position above arrives at approval-gated, versioned
procedural memory from a professional-duty argument rather than a platform one.

This is context for prioritization, not a claim of novelty: the governance model is
the contribution, and items 1 through 4 are what make it hold under adversarial
reading rather than cooperative reading.
