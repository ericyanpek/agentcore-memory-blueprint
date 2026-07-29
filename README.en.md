# AgentCore Memory Governance Blueprint

> This is the English translation. The primary document is
> **[README.md](README.md)** (Chinese); where the two differ, the Chinese version
> is authoritative. Full document table under [Repository](#repository).

An AWS reference implementation for a multi-user data analysis agent that:

- writes conversation turns to personal AgentCore short-term memory;
- lets AgentCore extract personal preferences into long-term memory;
- proposes project-level memory candidates through EventBridge;
- requires human review before publishing shared project memory;
- keeps logs, memory, Knowledge Bases, and team Skills as separate knowledge layers;
- exposes an auditable promotion path from memory to documents or Skills.

## What Is Distinctive

Memory is a **governed asset with an authority level**, not a smarter vector store.
Four design judgments; reasoning and counter-evidence in
[design rationale](docs/design-rationale.md):

- **Approved text is stored verbatim, with no second extraction pass.** Correct for
  governance and also optimal for cost and accuracy — a factorial study found
  retrieval method moves accuracy 20 points while write strategy moves 3–8, and
  zero-LLM raw storage matches the extraction pipelines
  ([ICLR 2026](https://arxiv.org/abs/2603.02473)).
- **Knowledge layers are divided by authority, not by cognitive-science vocabulary.**
  Authority is operational: it derives who may write and what overrides what.
  `episodic` only classifies.
- **Retrieval precedence is absolute and travels with the context.** Live data >
  Skills > authoritative documents > reviewed team memory > personal preference.
  Memory never overrides current data — the structural constraint against stale
  memory contaminating a judgment, aimed at experience following and context rot.
- **The human review gate is a scarce anti-poisoning control.** MINJA shows ordinary
  conversation suffices to poison a memory bank and that conventional defences all
  fail; MemoryTrap propagated across sessions and users in Claude Code. This project
  is desktop clients sharing one cloud memory, so shared writes must pass a human.

> Review covers the **team tier only**. Personal long-term memory and short-term
> events are not reviewed — IAM bounds their blast radius, but isolation is not review.

Verified against a real deployment: [experiment report](docs/实验报告.md), 14 checks ·
[desktop integration design](docs/桌面客户端集成设计.md), 8 + 17 checks (including a
mirror test where Alice's and Bob's permissions invert under the same role). Known
gaps: [roadmap](docs/roadmap.md).

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

- **Personal isolation depends on which path is used.** The desktop path enforces it
  in IAM. The AgentCore Runtime role serves every user and therefore relies on
  application-level actor ownership — the most significant open item.
- **The policy gate reads declared labels**, not content; it does not inspect for
  credentials or personal data.
- **Approved facts have no supersession path.** A statement that later becomes false
  stays retrievable until the resource expiry.
- **Governance properties are validated; answer quality is not measured.** No claim
  is made that memory improves output quality.

Per-item severity tables: [实验报告](docs/实验报告.md) section 9 and
[桌面客户端集成设计](docs/桌面客户端集成设计.md) section 11; remediation plan:
[roadmap](docs/roadmap.md).
