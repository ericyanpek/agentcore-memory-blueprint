# AgentCore Memory Enterprise Governance Handoff Report

> English translation. Chinese primary: [HANDOFF_REPORT.md](HANDOFF_REPORT.md).
> Completed: 2026-08-05.

## 1. Work Completed

| Deliverable | Content |
|---|---|
| [README.md](README.md) | Enterprise entry and Region/quota/price snapshot |
| [Enterprise blueprint](docs/ENTERPRISE_GOVERNANCE_BLUEPRINT.en.md) | Mental model, planes, architecture, boundaries, RACI, maturity, Gateway contract |
| [Control baseline](docs/CONTROL_BASELINE.en.md) | 42 MUST/SHOULD/MAY controls, evidence, gates, exception |
| [Observability blueprint](docs/OBSERVABILITY_BLUEPRINT.en.md) | Service telemetry, application ADOT/OTEL, three signals, analytics and pipeline governance |
| [Experiment path](experiments/README.en.md) | E00–E07, positive/negative tests, cost, cleanup |
| [Observability evidence template](experiments/observability-evidence.en.md) | Metrics, Logs, Traces, success/failure, data-governance evidence per experiment |
| [Sample catalog](docs/AWS_SAMPLE_CATALOG.en.md) | Pinned commit, mapping, production gaps, six drift items |
| This report | Unverified assumptions, cross-service conflicts, next owners |

Every new document has an English/Chinese pair and is added to structural alignment checks.

## 2. Source Snapshot

| Source | Snapshot |
|---|---|
| Research date | 2026-08-04 through 2026-08-05 |
| AWS samples | `fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645`, committed 2026-08-03 |
| Prior sample baseline | `ff11ccbb89d391a7c2478160a1b66c63f0b63e59`, committed 2026-07-22 |
| Official docs | Sources above plus AgentCore Observability, Knowledge Bases observability, Firehose Iceberg, S3 Tables |
| Local evidence | 14 cloud scenario checks, 8 Identity Pool checks, 17 bridge checks, CDK/Python tests |

Fact priority: Developer Guide / Release Notes > API Reference / Service Authorization
Reference > pinned AWS samples > local experiment > blueprint recommendation.

## 3. Unverified Assumptions

| Assumption | Status | Validation | Suggested owner |
|---|---|---|---|
| Memory data-plane CloudTrail coverage/fields support complete access audit | No explicit page equivalent to Gateway found | Call each API in sandbox and query CloudTrail/Lake | Observability |
| Control/data PrivateLink fits target Region and DNS architecture | Designed from docs only | Execute E03 with flow-log and endpoint-policy evidence | Network |
| Cross-account Memory and KMS policy fit target landing zone | Not tested | Two sandbox accounts execute E02/E03 | Identity/Security |
| Exact CMK coverage boundary for metadata | Samples prohibit secrets; product boundary needs confirmation | Obtain AWS Support confirmation; keep prohibition | Security |
| More metadata filters work across target SDK/Region | Repository model tested; sample lists three | E00 SDK contract test | Application |
| Harness managed Memory deletion/switch/ownership fits retirement | Documented, but repository does not use Harness | Harness blueprint lifecycle experiment | Harness |
| Customer-driven replication meets business RPO/RTO | Official sample exists but not run here | E06 fault and failback exercise | SRE |
| Guardrails dual checks have acceptable false-positive/negative rates | Architecture requirement only | E04 representative synthetic dataset | Security/Data |
| Transaction Search, Memory log delivery, and service spans work and correlate in target accounts | Designed from official docs; no account access | E00/E05 readiness and success/failure paths | Observability |
| Runtime/Harness, Gateway, built-in tools, and KB service/application telemetry correlate E2E | Cross-service fields defined; not tested | Each service owner uses common evidence template | Service owner |
| Logs -> Firehose -> S3 Tables redaction, error backup, deletion, cost meet requirements | Architecture defined; not deployed | Data-platform sandbox pipeline fault/deletion test | Data Platform |

## 4. Items to Align with Gateway Blueprint

The workspace does not contain the Gateway versions listed in the handoff:
`docs/ENTERPRISE_GOVERNANCE_BLUEPRINT.md`, `docs/CONTROL_BASELINE.md`,
`experiments/README.md`, or `docs/AWS_SAMPLE_CATALOG.md`. Gateway control IDs,
terminology, and risk levels could not be compared line by line. The Gateway contract in
the Memory documents is a Memory-owner proposal for Gateway-owner review.

| Topic | Memory position | Gateway confirmation |
|---|---|---|
| Final authorization | Gateway authorizes tool; Memory IAM authorizes data API | Gateway does not claim data authorization |
| Bypass prevention | SCP/IAM constrains direct SDK path | Which paths source/target restrictions cover |
| Identity propagation | Stable subject maps to actor; model cannot choose | Standard subject/claim/header contract |
| Policy scope | Policy intercepts Gateway, not direct Memory SDK | Gateway states the boundary |
| Guardrails | Gateway and Memory I/O rules cannot drift | Rule owner, version, failure mode |
| Session | Gateway MCP/HTTP session differs from Memory session | ID correlation, end, revocation |
| Trace | Gateway request ID joins Memory event/record | OTEL attributes and cross-account query |
| Deletion | Gateway target delete does not delete Memory data | Resource/user retirement propagation |
| Quota/cost | Budget Gateway rate and Memory quota separately | End-to-end admission owner |
| Error model | Preserve original Memory classification | Gateway wrapping/loss of errors |

## 5. Recommended Next Agents

1. **Gateway owner**: review section 4 against the Gateway blueprint and unify terms, IDs, risk.
2. **Identity owner**: define JWT/workload/OBO/3LO mapping to actor/session tags and cross-account mode.
3. **Observability owner**: use the new blueprint to validate Transaction Search, Memory
   log delivery, service/application spans, CloudTrail data plane, and unified redaction.
4. **Policy owner**: define intercepted Policy/Guardrails paths and direct-Memory compensation.
5. **Runtime/Harness owner**: prove user identity survives shared roles and align session lifecycle.
6. **Landing-zone aggregator**: merge controls, remove conflicts, build full-stack responsibility and E2E tests.

## 6. Work Not Performed

- No AWS resource was deployed, modified, or deleted.
- E00–E07 were not run; each is "designed, pending authorization."
- No customer data, token, secret, or account ARN was accessed.
- No claim that CloudTrail data plane, cross-account, PrivateLink, or DR passed.
- Transaction Search, log delivery, ADOT, Firehose, and S3 Tables were not enabled, and no cloud evidence was collected.
- No commit or pull request was created.

Start the next experiment with E00 and recheck Region, Quotas, Pricing, SDK, and sample commit.
