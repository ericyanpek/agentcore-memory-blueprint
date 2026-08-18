# AgentCore Memory Minimum Control Baseline

> English translation. Chinese primary: [CONTROL_BASELINE.md](CONTROL_BASELINE.md).
> Baseline date: 2026-08-04. Applies to production workloads using AgentCore Memory.

## 1. Requirement Strength and Risk

- **MUST**: required before release; absence requires a time-bounded formal exception.
- **SHOULD**: default requirement; rejection needs rationale and compensating control.
- **MAY**: selected by risk and cost; not a minimum release blocker.

| Risk | Example | Additional gate |
|---|---|---|
| Low | Internal demo without personal data | Minimum MUST; synthetic data only |
| Medium | Employee preferences and internal context | CMK, private path, deletion propagation, access review |
| High | Customer/regulated data or cross-team shared knowledge | Separate account/resource, dual approval, dual content checks, DR/IR exercise |
| Prohibited | Keys, tokens, passwords, unauthorized sensitive data | Must not enter Memory; block and remediate |

## 2. Control Catalog

| ID | Strength | Requirement | Minimum evidence | High-risk addition | Owner |
|---|---|---|---|---|---|
| MEM-GOV-001 | MUST | Assign business owner, data owner, environment, Region, and purpose to each Memory | Inventory, tags, architecture decision | Quarterly owner review | Platform |
| MEM-GOV-002 | MUST | Separate production/non-production accounts and deployment/Runtime roles | Organizations layout, trust/policies | SCP blocks cross-environment writes | Platform |
| MEM-GOV-003 | MUST | Separate personal extraction and reviewed shared knowledge with different Memory or equivalent resource boundary | IaC, Memory ARN, role matrix | Separate CMK and log access | Application |
| MEM-ID-001 | MUST | Derive actor from validated identity claim or controlled principal; reject model/body override | Mapping code, token tests, tampering test | Dual-channel identity review | Application |
| MEM-ID-002 | MUST | Scope data actions to exact Memory ARNs; no `bedrock-agentcore:*` | IAM policy, static scan | Permission boundary/SCP | Security |
| MEM-ID-003 | MUST | Constrain supported APIs with actor/session/namespace condition keys | IAM policy, allow/deny test | Quarterly cross-tenant probe | Security |
| MEM-ID-004 | MUST | Add application actor ownership checks for shared Runtime principals | Unit tests, E2E negative test, audit | Separate authorization service or session tag | Application |
| MEM-ID-005 | MUST | Separate proposal, approval, publish, and break-glass delete; prohibit self-approval | Role matrix, API test, approval log | Dual approval for publish/delete | Data owner |
| MEM-NET-001 | MUST | Use AgentCore control/data interface endpoints for medium/high risk | Endpoint, DNS, route, SG | Public-egress denial test | Platform |
| MEM-NET-002 | MUST | Limit endpoint policy and SG to approved principals/sources | Policy, reachability/flow log | Dedicated endpoint and subnet | Network |
| MEM-DAT-001 | MUST | Run schema, classification, credential, and PII checks before write | Rules, positive/negative samples, block log | Check before storage and after retrieval | Data owner |
| MEM-DAT-002 | MUST | Use rotating customer managed KMS key for sensitive data with scoped key policy | Memory config, key policy, Config/Security Hub | Dedicated key and disable exercise | Security |
| MEM-DAT-003 | MUST | Set shortest `eventExpiryDuration`; define separate LTM retention | Config, retention matrix, approval | Legal hold and data-subject workflow | Data owner |
| MEM-DAT-004 | MUST | Propagate deletion through events, records, streams, audit copies, logs, caches | Runbook, quarterly exercise | Independent verifier signs | Data owner |
| MEM-DAT-005 | MUST | Keep secrets, tokens, and raw sensitive data out of metadata/logs/traces by default | Field list, redaction test, sample | Automated DLP | Security |
| MEM-WRT-001 | MUST | Shared knowledge passes schema, evidence, human review, and dedicated publisher | State machine, candidate, IAM, approval | Required reason and immutable evidence | Data owner |
| MEM-WRT-002 | MUST | Inspect every batch result and classify transient/permanent failure | Unit test, injection, DLQ/alarm | Durable redrive and reconciliation | Application |
| MEM-WRT-003 | MUST | Use stable idempotency identity for create/update/replicate/delete | Replay test and duplicate query | Cross-Region dedupe ledger | Application |
| MEM-RET-001 | MUST | Filter retrieval by namespace and approved status/classification | Request log, filter and denial tests | Exact namespace, no broad path | Application |
| MEM-RET-002 | MUST | Label source/authority and inspect content before prompt injection | Prompt test, trace, block test | Conflict must refuse or escalate | Application |
| MEM-OBS-001 | MUST | Carry correlation ID across ingress, Memory, review, record, consumer | End-to-end trace/log query | Cross-account central query | SRE |
| MEM-OBS-002 | MUST | Alarm on errors, throttling, extraction stops, stream failures, backlog, cost | Alarm list, test notification, runbook | 24x7 escalation | SRE |
| MEM-OBS-003 | MUST | Audit principal, actor, session, namespace, action, result, error with redaction | Audit schema, sample, access control | Immutable central archive | Security |
| MEM-OBS-004 | MUST | Enable and verify CloudWatch Transaction Search per account/Region; evidence resource tracing state | Readiness config and service trace ID | Cross-account trace query | Platform |
| MEM-OBS-005 | MUST | Explicitly configure Memory vended log delivery, KMS, retention, destination policy | Delivery config and success/failure event IDs | Separate CMK and log account | SRE |
| MEM-OBS-006 | MUST | Deliver separate Metrics, Logs, Traces with success and controlled failure for every experiment | `observability-evidence.md` | Independent evidence review | SRE |
| MEM-OBS-007 | MUST | Separate service telemetry from application ADOT/OTEL; use IAM role and redacted allowlist attributes | Instrumentation, span sample, role policy | Automated DLP | Application |
| MEM-OBS-008 | MUST | Mark missing/unsupported signals `GAP/N/A` with official basis, compensation, owner, date | Gap register and issue | Close every applicable GAP pre-release | Service owner |
| MEM-OBS-009 | SHOULD | For long-term analytics use Logs -> Firehose -> S3 Tables with error backup, retry, schema | Pipeline test, Iceberg query, deletion test | Cross-account data platform | Data platform |
| MEM-OBS-010 | MUST | Alarm on telemetry silence and subscription, transform, delivery, backup, table-commit failure | Injection, alarm history, runbook | 24x7 escalation and reconciliation | SRE |
| MEM-REL-001 | MUST | Set timeouts; reads may degrade without memory; governed writes cannot silently succeed | Fault injection, alarm, response contract | Multi-AZ dependency/capacity validation | SRE |
| MEM-REL-002 | MUST | Define STM/LTM RPO/RTO, replication, failover/failback, deletion propagation | DR design and exercise | Annual full switch | SRE |
| MEM-QUO-001 | MUST | Capture actual account/Region quotas and load test peak before release | Quota snapshot, report, increase request | At least 30% headroom | SRE |
| MEM-CST-001 | MUST | Budget events, records, retrieval, extraction model, Kinesis, KMS, logs, replication | Cost model, budget, alarms | Tenant/business allocation | FinOps |
| MEM-SDL-001 | MUST | Manage Memory, IAM, KMS, endpoint, stream with IaC and drift detection | CDK synth, template, drift report | Signed artifacts and dual release | Platform |
| MEM-SDL-002 | MUST | Pin SDK/client and verify used API service model | Lock/requirements, build log, contract test | SBOM and vulnerability gate | Platform |
| MEM-SDL-003 | MUST | Migrate/rollback indexed keys, strategy, namespace, retention changes | Change, dual-write/backfill, rollback | Blue/green resource exercise | Application |
| MEM-IR-001 | MUST | Maintain poisoning, cross-tenant, deletion, KMS, stream, quota runbooks | Runbooks, tabletop, RACI | Semiannual technical exercise | Security |
| MEM-IR-002 | MUST | Time-bound, dual-approve, alert, and review break-glass role | Policy, approval, CloudTrail/audit | Automatic expiry and independent review | Security |
| MEM-REV-001 | SHOULD | Quarterly review roles, conditions, namespaces, owners | Access review report | Becomes MUST for high risk | Security |
| MEM-RED-001 | SHOULD | Red-team poisoning, injection, stale facts, cross-tenant behavior | Test set, results, remediation | Becomes MUST for high risk | Security |
| MEM-STR-001 | MAY | Use `METADATA_ONLY` record stream for audit and replication | Stream config, idempotency test | Avoid unnecessary `FULL_CONTENT` | Platform |

Use the [Service Authorization Reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_bedrock-agentcore.html)
for condition keys/actions and
[AgentCore quotas](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html)
for quotas.

## 3. Minimum Evidence Pack

Every production release includes at least:

1. architecture, data flow, account/Region/tenant boundaries, and RACI;
2. CDK/CloudFormation synth plus IAM/KMS/endpoint policies;
3. actual Service Quotas and cost estimate snapshot;
4. positive/negative actor, session, namespace, approval, and deletion tests;
5. complete [`observability-evidence.en.md`](../experiments/observability-evidence.en.md)
   with success/failure paths and Metrics, Logs, Traces;
6. alarm test, runbooks, and cleanup/rollback record;
7. failed controls, exception ID, expiry, and compensating controls;
8. confirmation that evidence contains no real ARN, account, token, secret, or customer data.

## 4. Release Gates

| Gate | Pass | Block |
|---|---|---|
| G1 facts | Region/API/quota/price reviewed with date | Undated sample values used |
| G2 identity | Actor immutable by client and cross-tenant test passes | Shared role lacks actor ownership check |
| G3 data | Classification, CMK, retention, deletion evidence | Secret/PII enters Memory without block |
| G4 write | Shared write has evidence, review, separation | Agent/model has shared direct write |
| G5 operations | Three signals, correlation, alarms, quota, cost, faults, cleanup pass | Applicable signal at GAP, silent writes, or no deletion/recovery runbook |
| G6 supply chain | IaC, SDK pinning, tests, drift pass | Console drift or `service:*` |

Any failed MUST blocks release; only an approved, unexpired exception can temporarily
allow it. A high-risk workload cannot use "POC" to bypass identity, classification,
encryption, or audit controls.

## 5. Exception Template

```yaml
exception_id: MEM-EXC-YYYY-NNN
control_ids: [MEM-XXX-NNN]
workload: <name>
environment: <prod/nonprod>
data_class: <low/medium/high>
reason: <why the control cannot be met>
risk: <specific failure and blast radius>
compensating_controls:
  - <control and evidence>
owner: <accountable role>
approvers:
  - security: <role>
  - data_owner: <role>
created_at: YYYY-MM-DD
expires_at: YYYY-MM-DD
exit_plan: <milestone and issue link>
evidence_uri: <immutable internal reference>
```

- Exceptions **MUST** expire within 90 days and never auto-renew.
- Exceptions **MUST** state specific risk, blast radius, and testable compensation.
- Identity, secret blocking, and audit controls for high-risk data **MUST NOT** receive permanent exception.

## 6. Control Validation Frequency

| Frequency | Validation |
|---|---|
| Every release | IaC, IAM, SDK, unit/contract/negative tests |
| Monthly | Cost, quota, alarm, drift, expired exceptions |
| Quarterly | Access, deletion propagation, owner, cross-tenant probes |
| Semiannual | Poisoning/authorization incident and break-glass exercise |
| Annual | Full DR/failback and data-lifecycle audit |

See [../experiments/README.en.md](../experiments/README.en.md) for implementation and
[ENTERPRISE_GOVERNANCE_BLUEPRINT.en.md](ENTERPRISE_GOVERNANCE_BLUEPRINT.en.md) for architecture.
