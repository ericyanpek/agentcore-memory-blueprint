# Roadmap: Next Evolution

> Translation. The primary document is [下一步演进](下一步演进.md) (Chinese).
> Related: [design-rationale.md](design-rationale.md) ·
> [architecture.md](architecture.md) · [AWS 官方背书](AWS官方背书.md)

The items form four groups: items 1–2 close gaps between documented claims and enforced
constraints; items 3–6 extend governance coverage and adoption paths; item 7 hardens the
validation methodology; and items 8–9 address gaps identified by the AWS Well-Architected
Agentic AI Lens.

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

**Current behaviour.** An approved shared record is immutable and **permanent** — there is
no way to mark it as no longer true. `eventExpiryDuration` applies per event at write time,
and a shared record created directly by `BatchCreateMemoryRecords` has no source event, so
it is never reached; `MemoryRecordCreateInput` carries no expiry field either. Record-level
removal exists only through an explicit `DeleteMemoryRecord` / `BatchDeleteMemoryRecords`.
If the curated-churn-view constraint the experiment approves is corrected next quarter, the
old record stays retrievable and indistinguishable from a current one.

**Target behaviour.** Model supersession as a **discrete status flag** rather than a time
window, adjudicated by a reviewer rather than a model:

1. Add an optional `supersedes: <record_id>` field to the candidate contract.
2. On approving such a candidate, publish the new record in the same workflow branch and use
   `BatchUpdateMemoryRecords` to write `superseded_by` onto the old one, flipping its
   `review_status` to the terminal value `DEPRECATED`.
3. The retrieval path needs no change — it already pre-filters on
   `review_status = approved`, so a superseded record leaves the retrievable set on its own.
4. Both records are kept. An audit trail has to show what the team once believed, and from
   when.

The status value reuses AgentCore Registry's existing `DEPRECATED` (measured to be terminal
platform-side) rather than inventing `superseded` — one concept should have one name within
one service. **Only the naming and the terminal semantics are borrowed, not the transition
rules**: Registry permits `REJECTED → APPROVED`, whereas this project's single-use callback
token is stricter and should not align with it.

Why a discrete flag rather than timestamp filtering, why no automatic contradiction
detection, and the comparison with Zep's bi-temporal edge model are in
[design-rationale](design-rationale.md). The disagreement between official sources about the
`INVALID` status is in
[the README](../README.en.md#platform-fact-snapshot-rechecked-2026-08-18).

**Files.** `contracts/memory-candidate-proposed.json`, `src/blueprint/domain.py`,
`src/blueprint/memory.py` (an update path alongside the publish path),
`src/handlers/publish_shared.py`, `infra/lib/memory-governance-stack.ts` (the publisher role
needs `BatchUpdateMemoryRecords` under the same exact-namespace condition), `dashboard/`
(surface superseded records distinctly). `superseded_by` is already declared as an indexed
key: a key can be added later but never removed, and adding one does not backfill, so
declaring it early keeps records approved in the meantime filterable once the mechanism
ships.

---

## 5. When to propose, and what qualifies — severity: high

**This item determines whether the governance path receives any input and is no less
important than the approval stages.** The approval chain is complete while the capture
trigger is missing. Every candidate in the experiment report was produced by a script, and
the `skills/` directory has only ever been added to, never modified.
**With no proposals, the whole governance mechanism idles.**

**Current behaviour.** The proposal contract is complete (five `category` values, confidence,
privacy classification, and an immutable `evidence_ref` are all enforced in
`src/blueprint/domain.py`), but nothing tells the model **when** to propose.
`memory_propose_shared` is an ordinary MCP tool, so the model decides when to call it.

**Target behaviour, four changes.**

1. **The criteria are in the tool description — done.** The `memory_propose_shared` docstring
   defines each of the five `category` values and lists what should not be proposed (the
   model's own tooling preferences, details specific to one task, restated documentation,
   unverified guesses). `bridge/validate_bridge.py` asserts those semantics actually appear
   in the `tools/list` response, so the change cannot silently regress.
2. **Capture evidence automatically with a hook — not done.** The model must currently call
   `memory_capture_evidence` before proposing, and skipping it means rejection at evidence
   validation — safe but poor ergonomics. A hook that captures evidence at the end of each
   turn keeps evidence ready, leaving the model only the judgment of whether a statement is
   worth proposing.
3. **A proposal-judgment Skill — not done.** Add a memory Skill under `skills/` that
   recognises the moment something was finally pinned down after several rounds of
   clarification and prompts the user to propose. This path also preserves the attribution
   chain: the statement comes from the person who has it, the `evidence_ref` points at that
   real conversation, and `proposer_actor_id` is still derived server-side from the token's
   `sub`.
4. **A scheduled agent directs attention without producing proposals — not done.** It can
   discover which questions keep recurring but **must not propose**: a proposal would be
   signed either by the agent itself (breaking attributability) or by some user (forgery),
   and its evidence could only point at aggregate statistics rather than a conversation
   anyone can revisit. Its output should be a topic list, handed to change 3.

**The privacy boundary holds by construction, not by access control.** The scheduled agent's
data source is the retrieval metrics (CloudWatch logs) rather than Memory, so it never needs
the cross-actor read of anyone's personal memory — exactly the permission the IAM condition
keys deliberately withhold. The metrics contain only per-token hashes and hit counts;
sensitive content is hashed before it reaches the log. The reviewed shared tier is not subject
to this: it is already visible to the team, so scanning it for deduplication and promotion
candidates raises no privacy question.

**Two hard constraints.** First, **prompt frequency is itself a habituation risk** — asking
"worth writing this down?" every turn teaches the user to dismiss it reflexively, the same
mechanism as the reviewer fatigue recorded in the README's limitations; the value of change 4
is making prompts rare, because rarity is what gives them precision. Second, **cold-start
ordering** — the retrieval metrics hold no data yet, so change 3 must ship on model judgment
first and tolerate a noisy period, switching to a metrics gate once enough accumulates; the
reverse does not work.

**Remaining files.** `.mcp.json` and hook configuration; `skills/` for the proposal-judgment
Skill; `poc/analyze_retrieval_metrics.py` (a topic-list output).

> **Fix three instrumentation defects first, or change 4 rests on bad data.** First,
> `fingerprint_query` tokenises on `[a-z0-9]+`, which is **ineffective for Chinese**, and the
> desktop path is used mostly in Chinese. Second, it detects only similarly worded repeats,
> not the same question asked differently (catching that means storing embeddings, which are
> no longer irreversible). Third, the instrumentation exists only in
> `src/agent/context_builder.py` — **the desktop bridge is not instrumented, and that is where
> the traffic is** — and both sides must use an identical algorithm, or cross-path repeat
> detection silently fails. That is a correctness problem.

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

- **Not adopting a `DRAFT` state, and the reason is recorded here.** Registry's state
  machine begins at `DRAFT` so a proposer can create a record and choose when to submit it
  for approval. Aligning with that was considered and rejected as unnecessary: on the
  desktop side `memory_capture_evidence` is already a step separate from proposing, and
  `memory_propose_shared` requires an `evidence_ref` pointing at an immutable record, so
  "accumulate evidence, then submit" is already satisfied by the tool boundary. Adding a
  state would complicate both the state machine and the review queue without buying a new
  capability.

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

This is context for prioritization, not a claim of novelty: the contribution lies in the
governance model, and items 1 through 4 are what make it hold under adversarial
reading rather than cooperative reading.
