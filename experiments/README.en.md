# AgentCore Memory Enterprise Experiment Path

> English translation. Chinese primary: [README.md](README.md).
> Design baseline: 2026-08-04. Official samples pinned to
> `fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645` (2026-08-03).
> **This path has not been executed and proves no deployment in a customer account.**

## 1. Execution Rules

1. Use synthetic data only in an approved sandbox; never learn by creating in production.
2. Give every experiment an isolated prefix, cost tags, and cleanup owner.
3. Record account, Region, CLI/SDK, quota, price, and sample commit before resources.
4. Run positive and negative tests; an empty read only proves isolation after data exists.
5. Redact every ARN, account, token, secret, and customer value from evidence.
6. Create with IaC; convert successful exploratory CLI into reproducible templates.
7. Treat any cleanup failure as experiment failure and open an issue.
8. Use [observability-evidence.en.md](observability-evidence.en.md) for every experiment
   and record Metrics, Logs, Traces independently. Mark absent/unsupported signals
   `GAP/N/A`; "no errors" is not evidence.

Official sample root:
[AgentCore Memory samples](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory).

## 2. Common Prerequisites

- temporary IAM role; no long-lived IAM user keys;
- AWS CLI v2, Python 3.12, `boto3>=1.43.36,<2`;
- a target Region that supports AgentCore Memory;
- sandbox budget and maximum experiment duration;
- writable local evidence directory and approved central log location;
- a readiness record for CloudWatch Transaction Search, span ingestion, resource tracing,
  and vended log delivery in each target account/Region;
- no real conversation, customer identifier, credential, or internal secret.

Record before starting:

```yaml
experiment_id: E0X
sample_commit: fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645
aws_account_alias: <redacted-alias>
region: <approved-region>
started_at: <UTC>
operator_role: <role-name-only>
cli_version: <value>
boto3_version: <value>
quota_snapshot: <evidence-path>
pricing_checked_at: <date>
data_class: synthetic
```

## 3. E00: Sources, Region, Toolchain, Quota, and Cost

| Field | Content |
|---|---|
| Purpose | Confirm service availability, SDK model, quota, price, and evidence location before creation |
| Sample | [`00-getting-started`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/00-getting-started) |
| Account / Region | Sandbox; one approved Region supporting Memory |
| Resources | None |
| Positive | CLI discovers `bedrock-agentcore-control`/`bedrock-agentcore`; SDK supports metadata, batch, stream APIs |
| Negative | Old SDK rejects required field; unsupported Region rejects explicitly |
| Success | Commit, version, Region, quota, price, budget, cleanup owner captured |
| Controls | MEM-GOV-001, MEM-QUO-001, MEM-CST-001, MEM-SDL-002 |
| Logs / Trace / Audit | Versions and read-only output without credentials |
| Observability evidence | Mark Metrics/Logs/Traces `N/A-readiness`; preserve Transaction Search, span ingestion, log delivery capability, and application ADOT decision |
| Cost | USD 0; read-only queries |
| Cleanup | No resources; remove sensitive environment output |
| Decision | Primary Region, SDK floor, cost-estimate method |

Steps:

1. Date-check [Region](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-regions.html),
   [quota](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html),
   and [pricing](https://aws.amazon.com/bedrock/agentcore/pricing/).
2. Record `aws --version`, Python, boto3, CDK, and AgentCore client.
3. Read actual account/Region Service Quotas; do not substitute documentation defaults.
4. Estimate monthly lower/upper cost from turns, events, records, retrievals, retention.

## 4. E01: Minimum Function and Resource Lifecycle

| Field | Content |
|---|---|
| Purpose | Verify Memory create, events, asynchronous extraction, retrieval, deletion |
| Sample | [`01-events-and-sessions`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/01-short-term-memory/01-events-and-sessions), [`01-built-in-strategies`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/02-long-term-memory/01-built-in-strategies) |
| Account / Region | Sandbox; E00 Region |
| Resources | One test Memory, minimum strategy, test CMK or approved key |
| Positive | Create/Get, CreateEvent/ListEvents, await extraction, Retrieve, Delete |
| Negative | Invalid expiry, duplicate name, wrong memoryId, read after delete |
| Success | STM immediate; LTM within deadline; deleted resource inaccessible |
| Controls | MEM-GOV-001, MEM-DAT-003, MEM-REL-001, MEM-SDL-001 |
| Logs / Trace / Audit | Control/data results, extraction wait, delete confirmation |
| Observability evidence | Record metric, log event, and trace for successful write/read and wrong memoryId; missing log delivery is an explicit `GAP` |
| Cost | Small event/record/retrieval charge; record actual estimate |
| Cleanup | `try/finally` delete Memory; handle retained key/log as planned |
| Decision | Retention, strategy, polling deadline, deletion semantics |

Never replace bounded state polling with fixed sleep. Extraction timeout is failure; a
historical record must not satisfy the current run.

## 5. E02: Identity, Least Privilege, and Cross-Service Calls

| Field | Content |
|---|---|
| Purpose | Prove identity binding for actor/session/namespace and least privilege |
| Sample | [`iam-scoped-access`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/05-security/01-iam-scoped-access), [`cognito-federated-identity`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/05-security/02-cognito-federated-identity) |
| Account / Region | Sandbox; single account then optional cross-account |
| Resources | Memory, two identities, read/write/publish roles, test policy |
| Positive | Alice reads/writes own event/namespace; publisher writes shared namespace |
| Negative | Alice reads Bob; body overrides actor; reader batch-writes; publisher reads personal |
| Success | Denials are exact `AccessDeniedException`/403 and allow path has real data |
| Controls | MEM-ID-001 through MEM-ID-005, MEM-RET-001 |
| Logs / Trace / Audit | STS identity, policy version, error, redacted actor/namespace |
| Observability evidence | Record Metrics/Logs/Traces for allow and AccessDenied paths and prove only redacted actor/namespace joins appear |
| Cost | E01 plus minor Cognito/log use |
| Cleanup | Delete identities, policies, Memory, temporary configuration |
| Decision | Choose `sub`, identityId, or principal tag as actor |

For shared Runtime roles, test direct permission and application ownership. An empty Bob
result alone is not isolation evidence.

## 6. E03: Private Network, Multi-Account, and Tenant Boundary

| Field | Content |
|---|---|
| Purpose | Verify PrivateLink, DNS, endpoint policy, tenant boundary, no bypass |
| Sample | [`actor-session-isolation`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/01-short-term-memory/03-actor-session-isolation), [`namespaces`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/02-long-term-memory/04-namespaces) |
| Account / Region | Network and workload sandboxes; same Region |
| Resources | Control/data endpoints, SG, private DNS, Memory, test roles |
| Positive | Approved SigV4 principal privately accesses exact actor/namespace |
| Negative | Public path, wrong VPC/source, broad namespacePath, unapproved account, OAuth endpoint pseudo-authorization |
| Success | Flow log proves private path; bypass fails; IAM remains final authorization |
| Controls | MEM-NET-001, MEM-NET-002, MEM-ID-002, MEM-ID-003 |
| Logs / Trace / Audit | Flow log, DNS resolution, endpoint policy, AccessDenied |
| Observability evidence | Join service signal, flow log, and application trace for private success and bypass denial; list cross-account missing links |
| Cost | Endpoint hours/data and logs; clean immediately |
| Cleanup | Delete endpoints, ENIs/SG, Memory, roles; confirm no ENI remains |
| Decision | Endpoint account/share model and SigV4/OAuth choice |

PrivateLink proves a network path, not user authorization. Endpoint policy cannot use an
OAuth user as principal for OAuth calls.

## 7. E04: Data and Security Controls

| Field | Content |
|---|---|
| Purpose | Verify classification, CMK, pre/post checks, Guardrails boundary, deletion |
| Sample | [`kms-encryption`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/05-security/03-kms-encryption), [`guardrails-integration`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/03-integrations/03-guardrails-integration), [`manage-extraction`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/02-long-term-memory/08-manage-extraction) |
| Account / Region | Security-approved sandbox |
| Resources | CMK Memory, classification/blocking, Guardrail, audit store |
| Positive | Allowed write/extract/retrieve; `SKIP` creates no LTM; deletion propagates |
| Negative | Synthetic secret/PII, poison instruction, bad key policy, key disable, log leakage |
| Success | Prohibited content blocked pre-storage; retrieved content rechecked; deletion evidenced |
| Controls | MEM-DAT-001 through MEM-DAT-005, MEM-RET-002, MEM-IR-001 |
| Logs / Trace / Audit | Match type and hash/ID only; no synthetic secret text |
| Observability evidence | Give all three signals for allow and synthetic-secret block, then sample logs/spans for absence of test plaintext |
| Cost | Guardrails, KMS, logs, event/record |
| Cleanup | Delete record/Memory/Guardrail; retain summary; schedule key deletion |
| Decision | Prohibited classes, STM-but-SKIP classes, deletion SLO |

## 8. E05: Observability, Audit, and Fault Injection

| Field | Content |
|---|---|
| Purpose | Prove correlation, metrics, ingestion logs, stream alarms, convergence |
| Sample | [`observability`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/04-observability), [`error-handling`](https://github.com/awslabs/agentcore-samples/blob/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/06-production-patterns/01-error-handling.md), [`record-streaming`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/02-long-term-memory/09-record-streaming) |
| Account / Region | Sandbox plus central-log test account |
| Resources | Log group/delivery, Transaction Search readiness, alarms, Kinesis, consumer, DLQ, Memory |
| Positive | Request/session/trace IDs join metric, log, span, event/record/stream; alarm notification arrives |
| Negative | Throttle, wrong namespace, KMS deny, consumer failure, delivery/transform failure, duplicate stream |
| Success | Metrics/Logs/Traces distinguish success/failure; every fault reaches alarm/runbook; writes visible; consumer idempotent |
| Controls | MEM-OBS-001 through MEM-OBS-010, MEM-WRT-002, MEM-WRT-003 |
| Logs / Trace / Audit | Complete evidence template, E2E query, alarm history, DLQ/redrive |
| Observability evidence | Separate service telemetry and application ADOT; verify Transaction Search, Memory log delivery, KMS/retention, pipeline alarm |
| Cost | CloudWatch, Kinesis, Lambda, KMS; record duration |
| Cleanup | Drain/archive evidence then delete stream, consumer, DLQ, alarms, Memory |
| Decision | Sampling, retention, content level, escalation thresholds |

## 9. E06: Capacity, Quota, Cost, and Recovery

| Field | Content |
|---|---|
| Purpose | Find peak boundary and verify backoff, budget, replication, failover/failback |
| Sample | [`cost-optimization`](https://github.com/awslabs/agentcore-samples/blob/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/06-production-patterns/02-cost-optimization.md), [`multi-region-replication`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/06-production-patterns/00-multi-region-replication) |
| Account / Region | Sandbox; two approved Regions |
| Resources | Primary/replica Memory, Kinesis, consumer, load generator, budget |
| Positive | Target-load SLO; STM dual-write, LTM replication, read switch, failback |
| Negative | 429, target outage, duplicate event, lag/backlog, deletion gap |
| Success | Stable backoff; measured RPO/RTO; budget alarm; deletion gap controlled |
| Controls | MEM-REL-001, MEM-REL-002, MEM-QUO-001, MEM-CST-001 |
| Logs / Trace / Audit | Load, error, latency, iterator age, cost, recovery timeline |
| Observability evidence | Give all three signals for normal load and 429/Region fault; verify telemetry-silence and pipeline-failure alarms |
| Cost | Dual Region Memory, dual write, Kinesis, Lambda, logs with hard cap |
| Cleanup | Restore primary, stop dual-write/stream, delete both Memories and replication |
| Decision | Actual RPO/RTO, headroom, multi-Region value, delete replication |

The official sample does not replicate deletes and demonstrates one account. Test that
limit; never report sample success as cross-Region strong consistency.

## 10. E07: Full Admission of a Low-Risk Enterprise Use Case

| Field | Content |
|---|---|
| Purpose | Complete identity, personal memory, candidate, review, shared retrieval, retirement |
| Sample | Official samples above plus local [`run_demo_scenario.py`](../poc/run_demo_scenario.py) and [`validate_bridge.py`](../bridge/validate_bridge.py) |
| Account / Region | Isolated pre-production; target business Region |
| Resources | Full CDK stack, two Memories, identity, approval, evidence bucket, alarms |
| Positive | Personal recall, cross-session, review, verbatim publish, cross-user sharing |
| Negative | Cross-user, restricted/low confidence, self-review, replay, no evidence, timeout, deletion |
| Success | Evidence for every applicable MUST; no P0/P1 gap; cleanup/rollback succeeds |
| Controls | All applicable MUST in [CONTROL_BASELINE](../docs/CONTROL_BASELINE.en.md) |
| Logs / Trace / Audit | One redacted pack joins request, approval, and record |
| Observability evidence | Complete template for E2E success and permission denial; any applicable `GAP` blocks admission |
| Cost | Compare estimate and actual, explain variance, set production budget |
| Cleanup | Execute retirement; retain required summary; prove cloud deletion |
| Decision | Admit/deny, residual risk, exception, owner, phased production plan |

E07 uses a realistic low-risk process with synthetic data. Do not run in production or
with customer data without explicit authorization.

## 11. Evidence Pack Template

```yaml
experiment_id: E0X
status: PASS | FAIL | BLOCKED
sample_commit: fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645
account_alias: <redacted>
region: <region>
resources:
  - type: <type>
    logical_id: <non-sensitive-id>
tests:
  positive:
    - expected: <expected>
      actual: <actual>
      result: PASS | FAIL
  negative:
    - expected_error: <exact-code>
      actual_error: <exact-code>
      result: PASS | FAIL
control_ids: [MEM-XXX-NNN]
evidence:
  metrics: [<namespace/metric/dimensions/reference>]
  logs: [<immutable-reference>]
  traces: [<immutable-reference>]
  audit: [<immutable-reference>]
  observability_template: <observability-evidence.en.md path>
cost:
  estimated_usd: <value>
  actual_usd: <value-or-pending>
cleanup:
  status: COMPLETE | FAILED
  verified_at: <UTC>
decisions:
  - <ADR reference>
open_risks:
  - <risk and owner>
```

## 12. Acceptance and Stop Conditions

- Stop and invoke incident response on any cross-tenant read, shared direct write, secret persistence, or audit leak.
- Keep experiment `FAIL` after any cleanup failure until an independent query proves cleanup.
- A negative test failing because of DNS, configuration, or absent resources does not prove authorization.
- Re-record quota, price, Region, and sample commit at experiment start.
- Production admission fails if any applicable Metrics, Logs, or Traces is `GAP`, or
  success and failure cannot be distinguished.
- E07 may be requested only after E00–E06 and evidence for every MUST pass.

See [../docs/CONTROL_BASELINE.en.md](../docs/CONTROL_BASELINE.en.md) for controls and
[../docs/AWS_SAMPLE_CATALOG.en.md](../docs/AWS_SAMPLE_CATALOG.en.md) for sample mapping,
and [../docs/OBSERVABILITY_BLUEPRINT.en.md](../docs/OBSERVABILITY_BLUEPRINT.en.md) for
cross-service signals.
