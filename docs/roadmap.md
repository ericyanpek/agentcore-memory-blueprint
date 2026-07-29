# Roadmap: Next Evolution

> Translation. The primary document is [下一步演进](下一步演进.md) (Chinese).
> Related: [design-rationale.md](design-rationale.md) ·
> [architecture.md](architecture.md)

Items are ordered by whether they close a gap between what the documentation claims
and what the code enforces (items 1–2), extend the governance model into a dimension it
does not yet cover or make it actually get used (items 3–6), or harden the validation
methodology (item 7).

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

**Files.** `src/handlers/reviewer_api.py`, `tests/test_reviewer_api.py`, the
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

**Design constraint that shapes the solution.** Retrieval metadata filters support
only `EQUALS_TO`, `EXISTS`, and `NOT_EXISTS` (verified against the
`bedrock-agentcore` service model, API version 2024-02-28). There are no range
operators, so a validity window cannot be expressed as a filter over timestamps.
Supersession must therefore be modelled as a **discrete status flag**, not as a date
comparison:

- Add `superseded_by` and set `review_status` to a terminal value such as
  `superseded` on the old record via `BatchUpdateMemoryRecords`.
- Retrieval already filters `review_status = approved`
  (`src/agent/context_builder.py`), so a superseded record leaves the retrievable set
  with no change to the query path.
- Keep both records. The audit trail requires knowing what the team believed and
  when, which a hard delete destroys.

**Route the decision through the existing review workflow, not through a model.**
Add an optional `supersedes: <record_id>` field to the candidate contract. Approving
such a candidate publishes the new record and, in the same workflow branch, flips the
old record's status. The reviewer decides what supersedes what.

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

For comparison, the reference design for full temporal modelling is Graphiti's
bi-temporal edge model, which separates when a fact was true from when the system
learned it, and invalidates rather than deletes
([arXiv:2501.13956](https://arxiv.org/abs/2501.13956)). A status flag is the
subset of that model expressible under `EQUALS_TO`-only filtering.

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
based solely on the tool's docstring. There is no hook in the repository (nothing
evaluates a completed turn), the single Skill under `skills/` is unrelated to proposal
judgment, and `poc/runtime_agent.py`'s system prompt never mentions proposing. The five
`category` **names** are visible to the model through validation errors
(`CATEGORIES` in `bridge/server.py`), but their **meaning is never conveyed** — the
model cannot tell what counts as a `constraint` versus an `incident`, and is never told
that personal preferences and one-off task details should not be proposed.

This is a usability gap rather than a security one, but its reach is larger: **if
nobody proposes, the whole governance mechanism idles** — the review queue stays empty
and shared memory never accumulates. The candidates in the experiment report were
produced by a script calling the API directly, not proposed by an agent.

**Target behaviour, two independent changes.**

1. **Convey the judgment criteria to the model.** The five enum values already imply
   the criteria; write their semantics into the tool description or a dedicated Skill:
   `fact` and `decision` must be independently understandable and useful to others;
   `constraint` covers hard limits such as metric-definition traps; `incident` covers
   confirmed failures that actually occurred; `procedure_hint` covers reusable
   operational steps. State equally clearly what should **not** be proposed: personal
   preferences, one-off task details, unverified guesses. This is the cheapest step.
2. **Capture evidence automatically with a hook.** Today the model must call
   `memory_capture_evidence` for an `s3://` reference before calling
   `memory_propose_shared`; skipping the first step means the proposal is rejected on
   evidence validation — safe but poor ergonomics (already recorded in
   [桌面客户端集成设计](桌面客户端集成设计.md) section 11). A hook that captures evidence
   at the end of each turn keeps evidence always ready, leaving the model only the
   judgment of whether a statement is worth proposing.

The division of labour: change 2 removes the prerequisite burden, change 1 addresses
the judgment itself.

**Files.** `bridge/server.py` (the `memory_propose_shared` docstring), `skills/` (a new
proposal-judgment Skill), `poc/runtime_agent.py` (system prompt), `.mcp.json` and hook
configuration (automatic evidence capture).

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
