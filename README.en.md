# AgentCore Memory Governance Blueprint

> This is the English translation. The primary document is
> **[README.md](README.md)** (Chinese); where the two differ, the Chinese version
> is authoritative.
>
> 中文文档：**[实验报告](docs/实验报告.md)** · [桌面客户端集成设计](docs/桌面客户端集成设计.md) · [架构设计](docs/架构设计.md) · [设计取舍依据](docs/设计取舍依据.md) · [下一步演进](docs/下一步演进.md) · [演示手册](docs/演示手册.md)

An AWS reference implementation for a multi-user data analysis agent that:

- writes conversation turns to personal AgentCore short-term memory;
- lets AgentCore extract personal preferences into long-term memory;
- proposes project-level memory candidates through EventBridge;
- requires human review before publishing shared project memory;
- keeps logs, memory, Knowledge Bases, and team Skills as separate knowledge layers;
- exposes an auditable promotion path from memory to documents or Skills.

## What Is Distinctive

Memory here is a **governed asset with an authority level**, not a smarter vector
store. Each property below is locatable in the code and verified end to end against
a real deployment — see the [experiment report](docs/实验报告.md) (14 checks) and the
[desktop integration design](docs/桌面客户端集成设计.md) (8 + 17 checks).

**Isolation is enforced by AWS, not by application code.** One shared IAM role plus a
Cognito Identity Pool session tag derived from the verified `sub` claim gives each
desktop client its own boundary. **Mirror-tested**: the same role grants Alice access
to Alice and denies her Bob, and inverts when Bob signs in — which rules out a policy
that merely happens to be hardcoded. 100 engineers = 1 role + 1 policy; onboarding
requires no AWS-side change.

**The shared write path is closed at the IAM layer.** No agent and no desktop client
holds `BatchCreateMemoryRecords`; team knowledge can only be *proposed*. Capability
that is not exposed does not exist: no MCP tool accepts an `actor_id` or `namespace`
parameter, and no tool writes shared memory directly.

**Approved text is stored verbatim, with no second extraction pass.** What the
reviewer read is what is stored (`src/blueprint/memory.py`). The record also carries
`candidate_id` as metadata pointing back to the audit table, closing the loop from
statement to approver to evidence.

**Context carries source labels and a conflict rule.** `src/agent/context_builder.py`
attaches a citation envelope to every retrieved record (record ID, namespaces, score,
strategy ID, memory ID) and puts `conflict_rule` into the prompt alongside the
precedence order — so precedence is an explicit instruction handed to the model with
the context, not a convention living only in a document: live data > authoritative
documents > reviewed team memory > personal preference, with preferences allowed to
affect presentation only.

**Idempotency and audit are coherent in the details.** Publication uses `candidate_id`
as the `requestIdentifier`; candidate registration uses a conditional write plus a
`workflow_execution_id` comparison, so EventBridge's at-least-once delivery cannot
produce duplicate records. Review tokens live only in server-side DynamoDB and the SNS
notification states explicitly that the token is omitted. Confidence is persisted as
an integer `confidence_basis_points`, avoiding float precision issues.

**Known failure modes are documented rather than hidden.** Both reports record the
**false positives** found after a first run that "passed" everything: asserting only
that a forbidden thing was not visible **passes vacuously** when the data never
existed. The fix was a control assertion (Alice's namespace must be non-empty) and
checking the failure **reason code** rather than only that a call failed.

Why these choices, with the external evidence for and against each:
**[design rationale](docs/design-rationale.md)**. Known gaps and planned work,
including evidence immutability that is still unenforced and the self-approval path:
**[roadmap](docs/roadmap.md)**.

## Architecture

```mermaid
flowchart LR
    U["Project member"] --> A["Data analysis agent<br/>AgentCore Runtime"]
    A --> PM["Personal AgentCore Memory<br/>actor=user ID"]
    A --> O["AgentCore observability<br/>logs and traces"]
    A --> EB["Project EventBridge bus"]
    EB --> SF["Step Functions Standard<br/>memory review"]
    SF --> DDB["DynamoDB<br/>candidate + callback state"]
    SF --> R["Reviewer API<br/>Cognito protected"]
    R --> SF
    SF --> SM["Shared AgentCore Memory<br/>actor=project ID"]
    SM --> A
    SF --> P["Promotion event"]
    P --> KB["Managed Knowledge Base<br/>authoritative documents"]
    P --> SK["Team Skills in Git<br/>executable procedures"]
```

The blueprint deliberately uses **two Memory resources**:

1. `PersonalMemory` is written by the agent runtime. Its actor is the authenticated
   user ID and its strategies extract user preferences and session summaries.
2. `SharedProjectMemory` is written only by the review publisher role. Approval
   directly creates a long-term record in a project namespace, so reviewed text is
   not changed by another extraction model.

This is a stronger isolation boundary than putting personal and shared records into
one resource and relying only on namespace conventions.

## Repository

- `infra/`: AWS CDK stack for Memory, EventBridge, Step Functions, DynamoDB,
  Cognito, SNS, and the reviewer API.
- `src/agent/`: adapter called by an AgentCore-hosted agent after a completed turn.
  It also builds source-labelled context from Knowledge Base, shared memory, and
  personal preferences.
- `src/handlers/`: Lambda handlers for review registration, callback, decision,
  publishing, and audit state.
- `src/blueprint/`: shared domain and AgentCore Memory client code.
- `contracts/`: example EventBridge event contracts.
- `skills/`: an example team Skill showing the final promotion target.
- `tests/`: local tests that do not require an AWS account.

Chinese is the primary language for documentation; English translations are kept in
sync.

| Chinese (primary) | English | Content |
|---|---|---|
| [实验报告](docs/实验报告.md) | [scenario-test-report](docs/scenario-test-report.md) | Validated run of the governance properties, 14 checks |
| [桌面客户端集成设计](docs/桌面客户端集成设计.md) | — | Desktop identity design, 8 + 17 checks |
| [架构设计](docs/架构设计.md) | [architecture](docs/architecture.md) | Trust boundaries, retrieval precedence, information lifecycle |
| [设计取舍依据](docs/设计取舍依据.md) | [design-rationale](docs/design-rationale.md) | Why the distinctive choices were made, with external evidence |
| [下一步演进](docs/下一步演进.md) | [roadmap](docs/roadmap.md) | Prioritized next evolution, including supersession semantics |
| [演示手册](docs/演示手册.md) | [demo-runbook](docs/demo-runbook.md) | End-to-end demonstration |
| [评估记录](docs/评估记录.md) | [sample-review](docs/sample-review.md) | Findings adopted from official samples, and deferred patterns |
| [参考资料](docs/参考资料.md) | [references](docs/references.md) | Verified official AWS sources |
| [安全说明](SECURITY.md) | [SECURITY.en](SECURITY.en.md) | Data handling, dependency audit, security boundaries |

`docs/scenario-test-report.md` is generated by `poc/run_demo_scenario.py` and contains
the full prompts and responses for each turn; the Chinese report is the interpreted
version.

## Event Terminology

There are two different event types:

- **AgentCore Memory event**: an immutable conversational event written with
  `CreateEvent`; it is short-term memory and can trigger asynchronous extraction.
- **AgentCore Memory record**: a long-term item created by extraction or directly
  with `BatchCreateMemoryRecords`.
- **EventBridge domain event**: a routing envelope such as
  `memory.candidate.proposed`; it starts governance workflows.

They are intentionally not interchangeable.

## Quick Start

```bash
python3 -m unittest discover -s tests -v
./poc/build_lambda_layer.sh
cd infra
nvm use
npm install
npm run build
npm test
npx cdk synth
```

`cdk synth` does not call the AWS account. Deployment requires a bootstrapped CDK
environment and permissions to create AgentCore Memory resources.

The shared publisher and metadata-filtered retrieval require the SDK version in
`src/requirements.txt`. Bundle it into each Lambda artifact or a controlled Lambda
layer; do not assume the Python runtime's preinstalled `boto3` has the current
AgentCore service model.

## Deployment Inputs

`projectId` and `environmentName` determine every resource name. They are pinned in
`infra/cdk.json` (`analytics-poc` / `demo` for this POC) and the synth fails if either
is missing. Changing them makes CloudFormation replace the whole stack — retained
Memory resources and DynamoDB tables then block the new stack with `AlreadyExists`, so
override them only when deploying a genuinely separate environment.

```bash
cd infra
npx cdk deploy \
  -c projectId=analytics-poc \
  -c environmentName=demo \
  -c reviewerOrigin=http://localhost:3000
```

After deployment:

1. Create a Cognito reviewer user and add it to the project-specific reviewer group
   emitted by the stack.
2. Subscribe a reviewer to the encrypted SNS topic.
3. Configure the agent runtime with the stack outputs for event bus name and
   personal/shared Memory IDs.
4. Use the runbook to publish a candidate and approve it.

The Knowledge Base ID is an integration parameter rather than a resource created by
this stack. A real Knowledge Base needs an explicit source, chunking strategy, vector
store, ingestion job, and retrieval validation; those decisions should not be hidden
inside a memory demo.

## Scope and Limitations

This is a POC. The boundaries below are deliberate; treating them as production-ready
would misrepresent what has been validated.

- **Review covers the shared tier only.** Personal long-term memory is written by
  AgentCore extraction with no review step. "Memory is reviewed" is true of team
  knowledge, not of personal preferences.
- **Personal isolation depends on which path is used.** The desktop path enforces it
  in IAM. The AgentCore Runtime role serves every user and therefore relies on
  application-level actor ownership — the most significant open item.
- **The policy gate reads declared labels.** It checks a self-reported privacy
  classification and confidence score; it does not inspect content for credentials
  or personal data.
- **Approved facts have no supersession path.** A statement that later becomes false
  stays retrievable until the resource expiry.
- **Governance properties are validated; answer quality is not measured.** No claim
  is made that memory improves output quality.

Full per-item severity tables: [实验报告](docs/实验报告.md) section 9 and
[桌面客户端集成设计](docs/桌面客户端集成设计.md) section 11. Planned remediation in
priority order: [roadmap](docs/roadmap.md).
