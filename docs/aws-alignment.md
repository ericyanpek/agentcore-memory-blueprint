# AWS Grounding and Implementation Mapping

> Translation. The primary document is [AWS 官方背书](AWS官方背书.md) (Chinese).
> Related: [architecture.md](architecture.md) · [design-rationale.md](design-rationale.md) ·
> [实验报告](实验报告.md) · [desktop-client-integration.md](desktop-client-integration.md) ·
> [roadmap.md](roadmap.md)

This document maps each design claim in the blueprint to AWS documentation, with the
verbatim quote, the implementation location, and the measured evidence.

## On the word "grounding"

A Well-Architected Lens is not an a-priori specification. Patterns reach a Lens after
solution architects hit the same problem repeatedly in the field, distil it, and see it
validated. **A Lens is a post-hoc codification of practice, not a precondition for it.**

So this is not "AWS specified it and the project complied." There are three distinct
relationships:

| Layer | Content |
|---|---|
| **Codified by AWS** | Human review, namespace isolation, IAM condition keys, deterministic risk classification — the Lens states these, and this project is a runnable reference implementation |
| **AWS built the primitive but did not wire it to Memory** | "Memory governance is codified and auditable" is the Level 5 goal of AGENTSEC01. AgentCore **already has a full approval state machine on its Registry resource** (`SubmitRegistryRecordForApproval` / `UpdateRegistryRecordStatus`), but the Memory resource is not connected to it. This layer is customer-built |
| **AWS is silent** | Admission control for shared memory, the retrieval precedence order, version-pinned evidence — no official source; these are the project's engineering judgements |

Layers two and three are where the actual contribution sits. The value of layer one is
narrower: it shows these choices are not personal preference but run in the same direction
as AWS's own framework.

---

## 1. Human review is the only path into shared memory

### AWS grounding

**"AGENTSEC04-BP02 Human-in-the-loop for critical decisions"**
(AWS Well-Architected Agentic AI Lens)
https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentsec04-bp02.html

Level of risk exposed if this best practice is not established: **High**.

Four verbatim passages, each matching a piece of this implementation:

> "For agents embedded in step-function-driven workloads, AWS Step Functions
> **.waitForTaskToken callback pattern introduces an approval step**."

> "**Reviewers don't typically call Step Functions APIs directly. The approval app holds
> the credentials**, and the reviewer interacts with the app."

> "You **log human approval decisions with timestamps and reviewer identities**, creating
> an auditable record of human oversight for compliance purposes."

> "**Store the full decision context in durable storage such as Amazon S3** before sending
> the approval notification... Make the context available through **the same authenticated
> interface** the reviewer uses to approve or deny."

**"Discover service integration patterns in Step Functions"**
https://docs.aws.amazon.com/step-functions/latest/dg/connect-to-resource.html

> "Callback tasks provide a way to pause a workflow until a task token is returned.
> **A task might need to wait for a human approval**."

The integration table on that same page lists **`.waitForTaskToken` as Not supported for
Bedrock AgentCore** — which is why the approval layer has to be built rather than
configured.

### This implementation

| Requirement | Location |
|---|---|
| `waitForTaskToken` approval step | `infra/lib/memory-governance-stack.ts:470` (`IntegrationPattern.WAIT_FOR_TASK_TOKEN`) |
| Task token held server-side | `src/handlers/request_review.py:21` writes it to DynamoDB; `src/handlers/reviewer_api.py:66,87` pop it before responding |
| Reviewer identity and timestamp recorded | `_decide()` in `src/handlers/reviewer_api.py` writes `reviewer_id` and `decided_at` |
| Authenticated review interface | Cognito-protected Review API, re-checking reviewer group membership on every request |

### Measured evidence

From `build/bridge-validation.json` and `build/scenario-results.json`:

```
[PASS] Reviewer in the project group reads the queue without task tokens
       HTTP 200, 3 pending, task_token exposed=False
[PASS] Review API rejects unauthenticated access          → HTTP 401
[PASS] A consumed review token cannot be replayed         → HTTP 409
[PASS] Non-reviewer is refused the review queue
       ok=False detail=You are not in the project reviewer group, so you cannot read the review queue.
```

The refusal is explicit rather than a silently filtered list — a non-reviewer is told they
lack the group, not handed an empty queue.

`task_token exposed=False` is the testable form of AWS's "reviewers don't call Step
Functions APIs directly."

---

## 2. The policy gate uses deterministic rules, not an LLM

### AWS grounding

From the same AGENTSEC04-BP02. This passage argues the point more sharply than the project
originally did:

> "**Risk classification itself can't rely on an LLM exposed to the same untrusted content
> as the request being evaluated**, because adversarial content could influence the
> classifier into marking the request as low-risk. Use **deterministic logic (policy
> engines, rule-based classifiers) as the authoritative signal**, with LLM-assisted
> classification as an optional input that a deterministic layer re-checks."

**"AGENTREL02-BP05 Establish tiered human oversight and approval workflows"**
https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentrel02-bp05.html

> "You have a **first-pass automated review layer that filters policy-violating actions
> before human reviewers see them**."

### This implementation

`src/blueprint/domain.py:101-105` — a pure boolean decision, no model involved:

```python
@property
def eligible_for_review(self) -> bool:
    return (
        self.privacy_classification != "restricted"
        and self.confidence >= 0.70
    )
```

Ineligible candidates land as `REJECTED_POLICY` at `domain.py:120` and never enter the
review queue.

### Measured evidence

```
[PASS] Restricted-classification candidate is blocked before human review
       status=REJECTED_POLICY (blocked at 0.98 confidence — privacy outranks confidence)
[PASS] Low-confidence candidate is blocked before human review
       status=REJECTED_POLICY (0.70 threshold)
```

---

## 3. Isolation by actorId and namespace, enforced by IAM

### AWS grounding

**"Actions, resources, and condition keys for Amazon Bedrock AgentCore"**
(Service Authorization Reference)
https://docs.aws.amazon.com/service-authorization/latest/reference/list_bedrock-agentcore.html

Condition keys confirmed on that page: **`bedrock-agentcore:actorId`** (on `CreateEvent`),
**`bedrock-agentcore:namespace`** (on `BatchCreateMemoryRecords` and
`BatchUpdateMemoryRecords`), and **`bedrock-agentcore:sessionId`** (on `CreateEvent`).

This project depends on the first two. Secondary sources also mention a `strategyId`
condition key, but it **could not be confirmed** on that official page, so it is not cited.

**"Memory organization in AgentCore Memory"**
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-organization.html

> "You can create IAM policies to **restrict memory access by the scopes you define, such
> as actor, session, and namespace**. Use the scopes as context keys in your IAM policies."

The policy example on that page also uses **`bedrock-agentcore:namespacePath`** for
hierarchical prefix matching (`StringLike` against `summaries/agent1/*`) alongside exact
`namespace` matching. This project currently uses only `namespace`; if subtree-level
authorization is needed later, `namespacePath` is the documented way to do it.

One more line from the same page bears on the two-resource design: namespaces mean "all
long-term memories are scoped to their specific namespace, keeping them organized and
**preventing any conflicts with other users or sessions**," with a trailing slash to
"prevent prefix collisions in multi-tenant applications."

**"Capability 5. Providing secure access, usage, and implementation of generative AI
agents"** (AWS Prescriptive Guidance, generative AI security reference architecture)
https://docs.aws.amazon.com/prescriptive-guidance/latest/security-reference-architecture-generative-ai/gen-auto-agents.html

> "**Secure agent memory through the Amazon Bedrock AgentCore Memory namespace structure
> for logical data isolation.**"

> "**Prevent memory poisoning by ensuring that users can't modify their session ID or
> actor ID.** Don't include ActorID or SessionID values in system prompts where users
> could manipulate them."

### This implementation

| Requirement | Location |
|---|---|
| Desktop credentials scoped by `actorId` | `poc/validate_identity_pool.py:122`, condition value `user:${aws:PrincipalTag/userId}` |
| Runtime retrieval confined to user namespaces | `infra/lib/memory-governance-stack.ts:397` |
| Shared memory pinned to one project namespace | `infra/lib/memory-governance-stack.ts:405`, `poc/validate_identity_pool.py` |
| A client cannot declare its actor | `bridge/server.py` — no tool accepts an `actor_id` parameter; identity comes only from the verified token's `sub` |

### Measured evidence

`build/identity-pool-validation.json` (8/8) — one shared IAM role, permissions fully
mirrored:

```
[PASS] Alice writes her own short-term memory              → ALLOWED
[PASS] Alice writes into Bob's actor (impersonation)       → AccessDeniedException
[PASS] Alice reads Bob's events                            → AccessDeniedException
[PASS] Alice retrieves Bob's preference namespace          → AccessDeniedException
[PASS] Alice writes shared memory directly, bypassing review → AccessDeniedException
```

Mirror control: signing in as Bob inverts the result — Bob reads Bob and is denied Alice.
Both callers share the same ARN
(`assumed-role/agentcore-memory-desktop-client-role/CognitoIdentityCredentials`), proving
the difference comes from the session tag rather than from a hardcoded policy.

**This claim is the clearest case of documentation and measurement being complementary**:
the official page says the condition keys exist; the test proves they actually deny.
Neither alone would be sufficient.

---

## 4. Memory is not authoritative truth and must not override current data

### AWS grounding

**"Secure agent memory and state" (AGENTSEC01)**
https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentsec01.html

> "**Every write path into memory**, including user inputs, tool outputs, inter-agent
> messages, and consolidation, **passes through a layered validation pipeline before data
> reaches the store**."

The first entry under "common issues to watch for" argues directly for two resources rather
than one resource plus a namespace convention:

> "**Shared namespaces treated as the default rather than an explicit design decision**,
> so one affected session can read or overwrite context that belongs to a different user
> or tenant."

**"Encrypt your Amazon Bedrock AgentCore Memory"**
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/storage-encryption.html

AWS documentation defines the threat itself:

> "**Memory poisoning happens when false or harmful information is saved in AgentCore
> Memory.** Later, your AI agent may use this wrong information in future conversations,
> which can lead to incorrect or unsafe responses."

### Partial support, not full support

The **six-level total order** (live data > Skills > authoritative documents > approved team
memory > personal preferences > model inference) **has no AWS source**. AWS argues the
direction — memory is candidate context, not authoritative truth — but never enumerates a
complete ordering. That is this project's engineering judgement; see section 2 of
[design-rationale.md](design-rationale.md).

---

## 5. Verbatim publication: approved text is stored as approved

### AWS grounding

**"Self-managed strategy"**
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-self-managed-strategies.html

> "A self-managed strategy in combination with the batch operations
> (**BatchCreateMemoryRecords**, BatchUpdateMemoryRecords, BatchDeleteMemoryRecords), let
> you **directly ingest these extracted records** into Amazon Bedrock AgentCore memory for
> search capabilities."

Bypassing platform extraction to write long-term records directly is therefore a documented,
supported path rather than a workaround.

The same page describes a self-managed strategy as a five-step flow: **configure triggers →
receive notifications and payload → extract → consolidate (deduplicate and resolve
conflicts) → store back via the batch APIs**. This project's governance pipeline is
isomorphic to it, with two differences: the policy gate and human review are inserted
between steps three and four, and what step five stores is **the text the reviewer
approved** rather than a model's extraction. AWS lists custom algorithms as one purpose of
the strategy:

> "Implement custom extraction and consolidation algorithms"

This project spends that freedom on governance rather than on extraction quality.

That page also confirms the correction noted at the end of this document: the only
operations touching memory record state are `BatchCreateMemoryRecords`,
`BatchUpdateMemoryRecords`, and `BatchDeleteMemoryRecords` — **no `INVALID` status
appears**.

**"Locking objects with Object Lock"** (S3)
https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html

> "S3 Object Lock uses a **write-once-read-many (WORM)** model to store objects... In
> compliance mode, a protected object version **can't be overwritten or deleted by any
> user, including the root user** in your AWS account."

### This implementation

`src/blueprint/memory.py:66-70` — `requestIdentifier` uses `candidate_id` as the
idempotency key, and `content.text` is the approved string itself.

### The boundary worth stating

The **requirement** that approved text be stored verbatim has no AWS source. AWS provides
the API that makes it possible but never says it should be done. The external support for
that claim comes from arXiv:2603.02473 (raw chunked storage with zero LLM calls matches or
beats lossy alternatives); see section 1 of [design-rationale.md](design-rationale.md).

---

## What AWS does not cover

Listed plainly, so the project does not overclaim:

| Design element | Status |
|---|---|
| **A native approval gate on memory writes** | Not provided by AgentCore Memory — but state this precisely: the **Registry resource in the same service does have one** (see section 3 of [design-rationale.md](design-rationale.md)). The accurate claim is not "AWS has no approval primitive" but "AWS already built one and Memory is not wired to it." The EventBridge → Step Functions pipeline here is customer-built |
| **"Team knowledge" as a governance category** | AWS documents shared namespaces but not the approval curation that decides what qualifies to enter one |
| **The retrieval precedence total order** | No AWS source |
| **`evidence_ref` pinning an S3 versionId as memory provenance** | S3 Object Lock's WORM semantics are fully documented, but AWS never frames versionId pinning as a provenance mechanism for AI memory |
| **Identity Pool session tags plus a single shared role to scope actorId** | Both components are documented separately, but AWS does not recommend the combination for AgentCore Memory. This pairing is original to the project |

## A correction to an earlier statement

The claim that "AgentCore marks stale memories `INVALID` rather than deleting them"
originates in an **AWS machine learning blog**, but **the status cannot be found in the
developer guide or the API reference** — memory records carry no status field, and the batch
operations are only create/update/delete. This is a disagreement between official AWS
sources rather than a pure citation error.

**How it is handled: follow the API documentation and do not depend on the behaviour.** The
blueprint's supersession mechanism uses its own discrete status flag (see item 4 of
[roadmap.md](roadmap.md)) and does not assume a platform-side `INVALID`. Any citation should surface the disagreement rather
than quote the blog alone.

## Not citable as an AWS position

The "Secure Your AI Agents on AWS" series on repost.aws (Parts 1–3) is relevant and
reasonably good, but the page states plainly:

> "This is a personal post. The views are my own and do not represent AWS."

The author is an AWS Technical Account Manager writing personally, so **it cannot stand as
an official AWS position**.

## Source summary

| AWS source | Claim it supports | Strength |
|---|---|---|
| [AGENTSEC04-BP02](https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentsec04-bp02.html) | Human review, token non-exposure, reviewer identity, S3 decision context, deterministic risk classification | Strong |
| [Service Authorization Reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_bedrock-agentcore.html) | `actorId` / `namespace` condition keys exist | Strong |
| [AGENTSEC01](https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentsec01.html) | Pre-write validation, shared namespaces should not be the default, maturity model | Strong |
| [GenAI security reference architecture](https://docs.aws.amazon.com/prescriptive-guidance/latest/security-reference-architecture-generative-ai/gen-auto-agents.html) | Namespace isolation, users must not modify actorId, KMS encryption | Strong |
| [Step Functions integration patterns](https://docs.aws.amazon.com/step-functions/latest/dg/connect-to-resource.html) | `waitForTaskToken` is the human approval mechanism | Strong |
| [Memory organization](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-organization.html) | Scopes used as IAM context keys | Strong |
| [AGENTREL02-BP05](https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentrel02-bp05.html) | Automated first-pass filter ahead of human review | Strong |
| [Self-managed strategy](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-self-managed-strategies.html) | `BatchCreateMemoryRecords` for direct ingestion | Strong |
| [storage-encryption](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/storage-encryption.html) | AWS's own definition of memory poisoning | Strong |
| [S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html) | WORM and version immutability | Strong |
| [Generative AI Lens](https://docs.aws.amazon.com/wellarchitected/latest/generative-ai-lens/generative-ai-lens.html) | "automated checks, human review... governance policies" | Partial |
