# AgentCore Memory AWS Official Sample Catalog

> English translation. Chinese primary: [AWS_SAMPLE_CATALOG.md](AWS_SAMPLE_CATALOG.md).
> Reviewed 2026-08-04. Samples support capability validation and experiment design; they
> are not production compliance evidence.

## 1. Pinned Snapshot

| Item | Value |
|---|---|
| Repository | `awslabs/agentcore-samples` |
| Pinned commit | `fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645` |
| Commit date | 2026-08-03 |
| Memory root | `01-features/04-manage-context-of-your-agent/memory` |
| Previous repository snapshot | `ff11ccbb89d391a7c2478160a1b66c63f0b63e59` (2026-07-22) |
| Verification | Shallow clone current commit, fetch old tree, path existence and name-status comparison |

Pinned entry:
[Memory samples at fa72a1e](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory).

From the prior snapshot, the Memory tree has 9 modified and 1 added file. Changes center
on quickstart, built-in/override/self-managed strategies, record metadata, extraction
management, and an episodic example. The added `02-long-term-memory/requirements.txt`
makes the SDK requirement for metadata/extraction explicit.

## 2. Sample Capability Mapping

| Sample path | Capability | Enterprise question | Adoption | Production gap |
|---|---|---|---|---|
| [`00-getting-started`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/00-getting-started) | CLI/boto3/SDK basics | Minimum resource/toolchain baseline | E00/E01 | No account governance, review, evidence pack |
| [`events-and-sessions`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/01-short-term-memory/01-events-and-sessions) | STM event/session | Persist raw interaction | E01 | Caller must map identity correctly |
| [`actor-session-isolation`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/01-short-term-memory/03-actor-session-isolation) | Actor/session separation | Prevent context mixing | E02/E03 | Organization key is not ownership proof |
| [`built-in-strategies`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/02-long-term-memory/01-built-in-strategies) | Semantic/summary/preference/episodic | Choose extraction | E01 | Model output still needs safety/authority governance |
| [`strategy-overrides`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/02-long-term-memory/02-strategy-overrides) | Custom prompt/model | Control extraction | E04 | Extra model cost, testing, version ownership |
| [`self-managed-strategy`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/02-long-term-memory/03-self-managed-strategy) | Self-managed extraction | Deterministic/custom pipeline | E04 | Customer owns S3/SNS/Lambda/idempotency/operations |
| [`namespaces`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/02-long-term-memory/04-namespaces) | Namespace organization | Tenant/project hierarchy | E02/E03 | Must combine with IAM |
| [`retrieval`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/02-long-term-memory/05-retrieval) | Semantic retrieval/citation | Preserve provenance | E01/E07 | No authority, stale-data, review decision |
| [`record-metadata`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/02-long-term-memory/06-record-metadata) | Indexed keys/filter | Pre-filter governance | E04/E07 | Indexed keys cannot be removed; govern schema |
| [`batch-apis`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/02-long-term-memory/07-batch-apis) | Direct record CRUD | Publish reviewed text verbatim | E07 | Partial failure, publish IAM, audit are custom |
| [`manage-extraction`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/02-long-term-memory/08-manage-extraction) | SKIP/redrive | Prevent extraction/recover failure | E04/E05 | Classify before redrive |
| [`record-streaming`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/02-long-term-memory/09-record-streaming) | Kinesis lifecycle stream | Audit, analytics, replication | E05/E06 | At-least-once, IAM/KMS, cost, consumer ownership |
| [`runtime-integration`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/03-integrations/01-runtime-integration) | Runtime session manager | Attach agent loop | E02/E07 | Avoid hook plus custom-recorder duplicate writes |
| [`identity-integration`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/03-integrations/02-identity-integration) | Identity + Memory | Put user identity in path | E02 | Valid token is not actor business authorization |
| [`guardrails-integration`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/03-integrations/03-guardrails-integration) | Output Guardrail | Layer content controls | E04 | Sample explicitly does not protect save/retrieve |
| [`observability`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/04-observability) | Metrics, alarms, logs | Detect extraction/stream faults | E05 | Enterprise thresholds, central audit, runbooks |
| [`iam-scoped-access`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/05-security/01-iam-scoped-access) | Condition-key least privilege | Platform isolation | E02 | Shared principal needs application ownership check |
| [`kms-encryption`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/05-security/03-kms-encryption) | CMK | Control data key | E04 | Key disable is outage, not deletion |
| [`production-patterns`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/06-production-patterns) | Error/cost/checklist | Move demo to operations | E05/E06 | Recheck all values against current docs |
| [`multi-region-replication`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/06-production-patterns/00-multi-region-replication) | STM dual-write + LTM stream | Build warm standby | E06 | No delete replication, single account, customer RPO/RTO |

## 3. Observed Sample Drift

| ID | Observation | Authoritative conclusion | Treatment |
|---|---|---|---|
| DRIFT-001 | Production checklist says `eventExpiryDuration` is 3–365 days | Current Quotas page says 7–365 | Use 7–365; recheck in E00 |
| DRIFT-002 | CDK README still says long-term records cannot be created directly | Data Plane API and batch sample support `BatchCreateMemoryRecords` | API Reference wins |
| DRIFT-003 | Metadata sample lists only `EQUALS_TO/EXISTS/NOT_EXISTS` | Current service models/API support more filter operators | Contract-test each SDK; do not infer full list from sample |
| DRIFT-004 | Guardrails sample filters model output only | Sample itself says user input can still persist | Check before storage and before injection |
| DRIFT-005 | Multi-region sample skips `MemoryRecordDeleted` and is single-account | Customer-built active-passive example, not native replication | Do not claim strong consistency or complete deletion |
| DRIFT-006 | Prior-to-current snapshot changes strategy, metadata, extraction | Samples continue evolving | Pin every citation to commit, never `main` |

Authority for DRIFT-001:
[AgentCore quotas](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html).
Authority for DRIFT-002:
[BatchCreateMemoryRecords API](https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/API_BatchCreateMemoryRecords.html).

## 4. Official Documentation Snapshot

| Source | Use in blueprint | Priority |
|---|---|---:|
| [Developer Guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory.html) | Concepts, organization, strategy, network, security | 1 |
| [Release Notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html) | Capability timeline | 1 |
| [Data Plane API](https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/Welcome.html) | Request/response, fields, errors | 2 |
| [Service Authorization Reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_bedrock-agentcore.html) | Action, resource, condition key | 2 |
| [Region](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-regions.html) | Memory Region availability | 2 |
| [Quotas](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html) | Resource, TPS, token limits | 2 |
| [Pricing](https://aws.amazon.com/bedrock/agentcore/pricing/) | Event, record, retrieval price | 2 |
| [PrivateLink](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/vpc-interface-endpoints.html) | Control/data endpoint and OAuth limitation | 2 |
| [CloudFormation](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-bedrockagentcore-memory.html) | IaC resource properties | 2 |
| Pinned AWS samples | Executable examples and production hints | 3 |
| Repository experiment | Measured result for this architecture | 4 |
| Blueprint recommendation | Enterprise governance design | 5 |

Resolve conflicts by this priority and register drift here; never silently choose the
convenient statement.

## 5. Conclusions Samples Cannot Support

- sample success does not prove compliance, residency, or least privilege;
- a correctly passed actor/namespace does not prove the caller owns it;
- Guardrails allow does not prove business authorization, truth, or isolation;
- PrivateLink does not prove an API call is authorized;
- multi-Region examples provide no service SLA, strong consistency, or complete delete replication;
- production-checklist numbers do not replace current Region, Quotas, and Pricing;
- Memory Browser is a local diagnostic tool, not an enterprise multi-user governance console.

See [../experiments/README.en.md](../experiments/README.en.md) for experiments and
[CONTROL_BASELINE.en.md](CONTROL_BASELINE.en.md) for controls.
