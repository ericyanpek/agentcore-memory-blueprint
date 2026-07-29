# Official AgentCore Memory Sample Review

> Translation. The primary document is [评估记录.md](评估记录.md) (Chinese).

## Review Scope

The review used the AWS Labs repository at commit
`ff11ccbb89d391a7c2478160a1b66c63f0b63e59` (2026-07-22):

- [Memory sample root](https://github.com/awslabs/agentcore-samples/tree/ff11ccbb89d391a7c2478160a1b66c63f0b63e59/01-features/04-manage-context-of-your-agent/memory)
- short-term and long-term memory;
- Runtime, identity, Guardrails, and Memory Browser integrations;
- observability and IAM/KMS security;
- error handling, cost, multi-region, and production checklists.

Commit-pinned links are used so this blueprint remains traceable even when the
sample repository changes.

## Adopted in the Blueprint

| Sample finding | Blueprint decision |
|---|---|
| [Batch record APIs](https://github.com/awslabs/agentcore-samples/blob/ff11ccbb89d391a7c2478160a1b66c63f0b63e59/01-features/04-manage-context-of-your-agent/memory/02-long-term-memory/07-batch-apis/README.md) | Approval writes the reviewed statement directly with `BatchCreateMemoryRecords`. `candidate_id` is the `requestIdentifier`; partial failures are inspected and classified. |
| [Structured metadata](https://github.com/awslabs/agentcore-samples/blob/ff11ccbb89d391a7c2478160a1b66c63f0b63e59/01-features/04-manage-context-of-your-agent/memory/02-long-term-memory/06-record-metadata/README.md) | Shared Memory declares stable indexed keys. Retrieval combines exact namespace scope with `project_id` and approved-status filters. |
| [Retrieval and citations](https://github.com/awslabs/agentcore-samples/blob/ff11ccbb89d391a7c2478160a1b66c63f0b63e59/01-features/04-manage-context-of-your-agent/memory/02-long-term-memory/05-retrieval/README.md) | Context includes a citation envelope built from record ID, namespaces, score, strategy ID, and Memory ID. |
| [Namespace organization](https://github.com/awslabs/agentcore-samples/blob/ff11ccbb89d391a7c2478160a1b66c63f0b63e59/01-features/04-manage-context-of-your-agent/memory/02-long-term-memory/04-namespaces/README.md) | Every namespace starts and ends with `/`. Exact `namespace` targets one project; hierarchical `namespacePath` is reserved for explicit aggregate reads. |
| [Error handling](https://github.com/awslabs/agentcore-samples/blob/ff11ccbb89d391a7c2478160a1b66c63f0b63e59/01-features/04-manage-context-of-your-agent/memory/06-production-patterns/01-error-handling.md) | Only throttling, service errors, and classified transient record failures are retried. Memory reads degrade to empty context; governed writes fail visibly. |
| [IAM-scoped access](https://github.com/awslabs/agentcore-samples/tree/ff11ccbb89d391a7c2478160a1b66c63f0b63e59/01-features/04-manage-context-of-your-agent/memory/05-security/01-iam-scoped-access) | Shared publish/read permissions include the exact project namespace condition. The docs distinguish namespace organization from IAM authorization. |

Direct record creation is the largest correction to the original design. The old
flow was approval -> `CreateEvent` -> asynchronous semantic extraction. That allowed
a second model to rewrite approved content and delayed availability. The new flow is
approval -> direct long-term record, which is deterministic and auditable.

## Adapted, Not Copied

### Personal Conversation Integration

The [Runtime integration sample](https://github.com/awslabs/agentcore-samples/tree/ff11ccbb89d391a7c2478160a1b66c63f0b63e59/01-features/04-manage-context-of-your-agent/memory/03-integrations/01-runtime-integration)
uses Strands `AgentCoreMemorySessionManager` to rehydrate recent turns and persist new
messages through lifecycle hooks. Use it when the demo agent uses Strands.
`TurnRecorder` remains a framework-neutral adapter for sanitized governance events
and a fallback for runtimes without those hooks; do not enable two writers for the
same turn.

### Identity

Cognito `sub` is the stable personal actor for the trusted server-side pattern.
The [federated identity sample](https://github.com/awslabs/agentcore-samples/tree/ff11ccbb89d391a7c2478160a1b66c63f0b63e59/01-features/04-manage-context-of-your-agent/memory/05-security/02-cognito-federated-identity)
uses the Cognito Identity Pool `identityId` instead because IAM policy variables bind
to that identity. These are two distinct patterns, not interchangeable ID rules.

### Guardrails and Extraction

The [Guardrails sample](https://github.com/awslabs/agentcore-samples/tree/ff11ccbb89d391a7c2478160a1b66c63f0b63e59/01-features/04-manage-context-of-your-agent/memory/03-integrations/03-guardrails-integration)
filters model output only and explicitly warns that this does not protect storage.
A production agent must evaluate input before memory writes and recalled content
before prompt injection. `extractionMode="SKIP"` is appropriate for tool, system,
debug, import, or sensitive turns that may remain in short-term memory but must not
become personal long-term records.

### Memory Browser

The [Memory Browser sample](https://github.com/awslabs/agentcore-samples/tree/ff11ccbb89d391a7c2478160a1b66c63f0b63e59/01-features/04-manage-context-of-your-agent/memory/03-integrations/04-memory-browser)
is a useful local, read-only diagnostic base. It accepts a Memory ID, actor ID, and
session ID; displays short-term events and reconstructed turns; discovers long-term
namespace templates from configured strategies; and retrieves records from a chosen
namespace.

It is not a governance console:

- one Memory resource is configured at a time, while this blueprint deliberately
  separates personal and shared Memory resources;
- namespace discovery depends on strategies, so the strategy-free shared Memory
  requires its exact namespace to be entered manually;
- long-term browsing uses semantic retrieval with a wildcard-like query rather than
  a paginated inventory view;
- record metadata, strategy ID, candidate ID, evidence links, and review status are
  not rendered;
- add, delete, and general search endpoints are placeholders;
- it has no candidate queue, Step Functions execution view, or approve/reject flow;
- the FastAPI backend uses the operator's local AWS credentials and has no user
  authentication or project authorization. Binding to localhost limits exposure but
  does not make it suitable for multi-user deployment.

For the POC, reuse the event/turn rendering and namespace-template resolution, but
replace the single free-form configuration with explicit Personal and Shared
resource views. Browse and semantic search must be separate operations. The shared
view should show record ID, indexed metadata, candidate/evidence references, and
review state; the review view should read the candidate table and use the existing
Cognito-protected decision API. Production deployment also requires authenticated
operator roles, project-scoped authorization, audit logging, and a separate
break-glass deletion workflow with propagation.

## Deferred Production Extensions

| Pattern | Reason to defer |
|---|---|
| `METADATA_ONLY` record streaming to Kinesis | Valuable for promotion pipelines, replication, and analytics, but adds cost, IAM/KMS surface, at-least-once consumers, and stream alarms. |
| Cross-region replication | Requires an explicit RTO/RPO and data-residency design. STM needs controlled dual-write; LTM needs idempotent record replication. |
| Full Memory Browser | Useful for operations and deletion workflows, but needs separate operator authorization and privacy controls. |
| Self-managed extraction strategy | Useful if candidate generation itself moves into AgentCore Memory. The current EventBridge proposal contract is easier to explain and keeps review policy independent of extraction internals. |

## Operational Gaps Before Production

- Package `boto3>=1.43.36` from `src/requirements.txt`. Local `boto3 1.42.94`
  supports batch creation but its service model rejects record `metadata`; relying on
  the Lambda runtime SDK is unsafe.
- Add CloudWatch alarms in `AWS/Bedrock-AgentCore` for data-plane errors and latency.
  If streaming is enabled, alarm on `StreamPublishingFailure` and `StreamUserError`.
- Enable and protect ingestion logs under
  `/aws/bedrock-agentcore/memory/<memoryId>`.
- Add a durable buffer for failed personal-memory writes. Retrieval may degrade to no
  memory; write loss must not be silent.
- Add deletion propagation and retention tests across Memory, audit data, logs,
  Knowledge Base documents, and Skills.
