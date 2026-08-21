# AgentCore Cross-Service Observability Blueprint

> English translation. Chinese primary: [OBSERVABILITY_BLUEPRINT.md](OBSERVABILITY_BLUEPRINT.md).
> Facts reviewed: 2026-08-05. This is a design and experiment standard; it does not claim
> enablement or validation in any AWS account.

## 1. Scope and Acceptance Principle

This blueprint covers AgentCore Runtime/Harness, Memory, Gateway, built-in tools,
application code calling those resources, and Bedrock Knowledge Bases. Every experiment
must answer:

1. whether function succeeds as expected and produces one controlled failure as expected;
2. what evidence Metrics, Logs, and Traces provide independently;
3. whether telemetry has redaction, encryption, retention, least privilege, and cost control;
4. whether request, session, or trace ID can cross-locate the evidence.

A Console chart is not sufficient acceptance evidence. If log delivery is absent, tracing
is not enabled, or spans cannot be queried, record a telemetry gap rather than conclude
that there were no errors.

## 2. Three-Layer Telemetry Model

```text
Service-provided telemetry
  AgentCore Runtime / Memory / Gateway / built-in tools
  -> CloudWatch service metrics
  -> explicitly enabled vended logs where supported
  -> service spans after CloudWatch Transaction Search and tracing are enabled

Application telemetry
  Agent / proxy / orchestrator / review workflow
  -> ADOT / OpenTelemetry instrumentation
  -> CloudWatch GenAI Observability and/or an approved OTEL backend

Long-term analytical archive
  CloudWatch Logs subscription
  -> Amazon Data Firehose
  -> Amazon S3 Tables (Apache Iceberg)
  -> Athena / Redshift / Spark / QuickSight
```

Service telemetry cannot explain custom business steps, prompt version, routing rationale,
retry, or approval state. Application ADOT/OTEL cannot replace service errors, throttles,
and resource dimensions. Join both with controlled correlation identifiers, and never put
raw secrets, tokens, sensitive prompts, or full tool payloads in logs or span attributes.

## 3. Metrics, Logs, and Traces

| Signal | Question answered | Minimum evidence | Does not prove |
|---|---|---|---|
| Metrics | Did it happen, at what scale/trend/SLO? | namespace, metric, dimensions, statistic, window, delay | Single-failure cause or cross-step causality |
| Logs | What did one execution do and why fail? | destination, group/prefix, event ID, retention, KMS | Full call graph or aggregate trend |
| Traces | What causal path crossed agent, Gateway, tool, Memory? | trace ID, root/child spans, missing edges | Log governance or long-term trend |

Experiments fill all three independently. When a resource does not support a signal,
record the official basis, compensating application telemetry, and owner. Do not substitute
another signal and mark the missing one passed.

## 4. One-Time Account and Region Readiness

1. **MUST** confirm CloudWatch Transaction Search and OpenTelemetry span ingestion in
   every target account and Region. This is a prerequisite for AgentCore service
   spans/traces, not a property automatically enabled by one Gateway.
2. **MUST** record the default Metrics, Logs, and Spans state per resource. AWS currently
   says metrics are default for all AgentCore resources, while starred logs/spans require
   explicit enablement.
3. **MUST** explicitly configure required vended log delivery for Memory and Gateway.
   Select CloudWatch Logs, Amazon S3, or Firehose according to current service support.
4. **MUST** set a customer managed KMS key for sensitive CloudWatch Logs workloads,
   explicit retention, resource policy, and access audit.
5. **MUST** use IAM roles, not long-lived access keys, to send telemetry to an OTEL backend.
6. **SHOULD** provide cross-account query in a central observability account while
   preserving minimum source-account troubleshooting.

AWS currently states that Runtime creates a service-provided log group by default; Memory
and Gateway do not configure log destinations automatically; built-in tools do not provide
service logs by default and need application output plus a destination. Recheck these
defaults against current documentation and actual resource configuration before release.

## 5. Resource Test Matrix

| Resource | Success path | Controlled failure | Metrics | Logs | Traces / application compensation |
|---|---|---|---|---|---|
| Runtime / Harness | Successful call and session completion | timeout, model or tool error | invocation, latency, error, usage | service/application logs | agent root and model/tool child spans; ADOT business steps |
| Memory | Write, read, extraction, or TTL behavior | wrong ID, denial, capacity boundary | operation, latency, error | query after Memory delivery is enabled | Memory operation span; redacted actor/session correlation |
| Gateway | `initialize`, `tools/list`, `tools/call` | target, permission, or input failure | invocation, latency, error, throttle | Gateway application log delivery | Gateway/tool spans; preserve downstream error class |
| built-in tools | Successful Browser/Code Interpreter result | input, permission, or execution failure | per-tool call, error, latency | application logs when service logs are absent | tool span with parent; record data/cost boundary |
| Knowledge Bases | ingestion, retrieve, retrieve-and-generate | ingestion failure or empty retrieval | KB runtime and ingestion metrics | ingestion delivery and application logs | join from caller trace; do not claim Gateway trace |

Metric names, namespaces, and dimensions evolve. Discover them from current AWS
documentation or the actual CloudWatch resource in the target Region; do not infer exact
names from this table. Knowledge Bases has separate runtime metrics and ingestion logs.
Its Console "Observability" does not mean AgentCore Gateway logs or traces are configured.

## 6. Evidence Gate for Every Experiment

Every E00-E07 experiment uses
[observability-evidence.en.md](../experiments/observability-evidence.en.md) and:

- **MUST** record account alias, Region, redacted resource ARN, UTC window, and caller;
- **MUST** execute one success path and one controlled failure path;
- **MUST** give location, ID, observed value, and ingestion delay for Metrics, Logs, Traces;
- **MUST** record actual Transaction Search, resource tracing, and log delivery states;
- **MUST** join available signals by request/session/trace ID and list every missing link;
- **MUST** check redaction, KMS, retention, IAM role, and cleanup;
- **MUST** mark absent or unconfigured signals `GAP` with owner and due date.

## 7. Correlation and Field Standard

The application creates a `correlation_id` that the model cannot override and propagates it
where protocols permit. Platform request ID, runtime session ID, trace/span IDs, Memory
event/record IDs, and Gateway target/tool names remain separate fields rather than one
unparseable string.

```text
event_time, account_id, region, environment,
resource_type, resource_arn, agent_name,
trace_id, span_id, parent_span_id,
request_id, runtime_session_id, correlation_id,
gateway_id, target_name, tool_name,
operation, outcome, error_code,
latency_ms, model_id, input_tokens, output_tokens,
estimated_cost, prompt_version, payload_redacted
```

Classify `actor_id`, `session_id`, URL, prompt, and tool arguments. Prefer stable
tokenization/HMAC values for joins instead of raw text. Never record AWS credentials,
OAuth tokens, API keys, or passwords.

## 8. Logs, Firehose, and S3 Tables

```text
AgentCore vended/application logs
  -> CloudWatch Logs
  -> subscription filter
  -> Amazon Data Firehose
  -> transform: allowlist + redact + normalize + partition keys
  -> Amazon S3 Tables (Apache Iceberg)
  -> Athena / Redshift / Spark / QuickSight
```

| Component | Primary responsibility | Must not be treated as |
|---|---|---|
| CloudWatch Logs | Near-real-time troubleshooting, Insights, metric filters, alarms, subscriptions | Sole long-term correlation warehouse |
| Firehose | Buffer, transform, compress, route, retry, deliver | Query engine or system of record |
| S3 Tables | Managed Iceberg tables and long-term structured cross-resource trends | Live tail, alarm engine, or SIEM |

Stop at CloudWatch Logs for routine troubleshooting only. Add Firehose and S3 Tables when
cross-month quality, reliability, and cost analysis is required. Firehose directly supports
Iceberg tables hosted in Amazon S3 Tables. Production design must configure S3 error
backup, retry, CloudWatch error logging, schema version, and Lake Formation/IAM. Partition
by date, environment, and resource type, never high-cardinality trace ID.

## 9. Data Governance and Lifecycle

- **MUST** allowlist and redact before subscription or in the Firehose transform; transform failure must not fall back to raw text.
- **MUST** separately define retention/deletion for CloudWatch, S3 error backup, Iceberg snapshots, and query results.
- **MUST** verify encryption at rest and key policy for Logs, backup bucket, S3 Tables, and query results.
- **MUST** separate least-privilege delivery, transform, and analyst roles.
- **MUST** prove deletion removes underlying files, snapshots, and backups according to policy, not only an Iceberg delete marker.
- **SHOULD** enable S3 Tables compaction, snapshot expiration, and unreferenced-file cleanup.
- **SHOULD** run automated DLP sampling for high-risk fields and handle hits as security incidents.

## 10. Alarms, Cost, and Pipeline Self-Monitoring

| Alarm | Starting criterion | Purpose |
|---|---|---|
| Error rate | Exceeds business SLO over 5 minutes | Detect systemic failure |
| p95/p99 latency | Exceeds SLO for multiple periods | Separate model, Gateway, tool, Memory slowdown |
| Throttling/quota | Record first event, alarm on persistence | Prevent capacity-driven user failure |
| Tool/target failure | One target/tool rises abnormally | Avoid aggregate success hiding a local fault |
| Memory/session failure | TTL, session-not-found, extraction failure rises | Validate lifecycle |
| KB ingestion/empty retrieval | Job failure or abnormal empty retrieval | Separate ingestion, permission, retrieval quality |
| Pipeline failure | subscription, transform, delivery, backup, table commit fails | Prevent healthy service with missing evidence |
| Telemetry silence | Business traffic exists while one signal is zero | Detect collection drift |

Set thresholds from business SLOs and baseline. Cost covers at least model tokens,
Gateway/tool invocation, Memory operation, CloudWatch ingest/storage/query, Firehose
delivery/transform, S3 Tables storage/maintenance, and analytical scan.

## 11. Responsibility and Release Conditions

| Responsibility | Owner | Release evidence |
|---|---|---|
| Transaction Search and cross-account CloudWatch | Platform/SRE | account/Region readiness screenshot or API output |
| resource tracing and log delivery | Service owner | configuration, destination policy, success/failure event |
| application ADOT/OTEL and correlation | Application | instrumentation test, trace graph, field inventory |
| redaction, KMS, retention, IAM | Security/data owner | policy, sample, deletion test, access review |
| Firehose/S3 Tables and cost | Data platform/FinOps | pipeline test, error backup, budget and alarm |

Any applicable Metrics, Logs, or Traces evidence at `GAP`, or inability to distinguish
success from failure, blocks production. An experiment may remain `BLOCKED` for design
work, but functional success is not operational readiness.

## 12. Official Sources

- [AgentCore observability configuration](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-configure.html)
- [AgentCore generated observability data](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-service-provided.html)
- [Get started with AgentCore Observability](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-get-started.html)
- [Knowledge Bases managed observability](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-observability.html)
- [Knowledge Bases ingestion logging](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-bases-logging.html)
- [Firehose Apache Iceberg destination](https://docs.aws.amazon.com/firehose/latest/dev/apache-iceberg-destination.html)
- [Amazon S3 Tables](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-tables.html)
