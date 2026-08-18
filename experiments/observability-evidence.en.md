# Observability Experiment Evidence

> English translation. Chinese primary: [observability-evidence.md](observability-evidence.md).
> Copy and complete for every E00-E07 experiment. Never include real credentials, tokens,
> secrets, sensitive prompts, or customer data.

## 1. Experiment Identity

| Field | Value |
|---|---|
| Experiment / run ID | `<E0X/run-id>` |
| Resource type / ARN | `<type>/<redacted-arn>` |
| Account alias / Region | `<redacted>/<region>` |
| UTC time range | `<start>/<end>` |
| Caller role | `<role-name-only>` |
| Sample commit / app version | `<sha>/<version>` |
| Data class | `synthetic` |

## 2. Readiness

| Check | Status | Evidence |
|---|---|---|
| CloudWatch Transaction Search | `ENABLED / DISABLED / N/A` | `<reference>` |
| OpenTelemetry span ingestion | `ENABLED / DISABLED / N/A` | `<reference>` |
| Resource tracing | `ENABLED / DISABLED / UNSUPPORTED` | `<reference>` |
| Vended log delivery | `CONFIGURED / MISSING / UNSUPPORTED` | `<destination/config>` |
| Application ADOT/OTEL | `CONFIGURED / NOT_REQUIRED / GAP` | `<reference>` |

## 3. Functional Paths

| Path | Input summary | Expected | Actual | Result |
|---|---|---|---|---|
| Success | `<redacted>` | `<behavior>` | `<behavior>` | `PASS / FAIL` |
| Controlled failure | `<redacted>` | `<exact error/outcome>` | `<error/outcome>` | `PASS / FAIL` |

Correlation identifiers:

```text
correlation_id:
request_id:
runtime_session_id:
trace_id:
memory_event_or_record_id:
gateway_target_or_tool:
kb_ingestion_job_id:
```

## 4. Metrics

| Path | Namespace / metric | Dimensions / statistic | Observed value | Ingestion delay | Evidence |
|---|---|---|---|---|---|
| Success | `<value>` | `<value>` | `<value>` | `<duration>` | `<reference>` |
| Controlled failure | `<value>` | `<value>` | `<value>` | `<duration>` | `<reference>` |

Status: `PASS / FAIL / GAP / N/A`. For `GAP/N/A`, give official basis, compensation,
owner, and date: `<reason / compensation / owner / due-date>`.

## 5. Logs

| Path | Destination / group / prefix | Event ID | Redaction checked | Retention / KMS | Evidence |
|---|---|---|---|---|---|
| Success | `<value>` | `<value>` | `YES / NO` | `<days>/<key-alias>` | `<reference>` |
| Controlled failure | `<value>` | `<value>` | `YES / NO` | `<days>/<key-alias>` | `<reference>` |

Status: `PASS / FAIL / GAP / N/A`. Missing log delivery is `GAP`, never evidence of no errors.

## 6. Traces

| Path | Trace / root span | Required child spans | Missing links | Evidence |
|---|---|---|---|---|
| Success | `<value>` | `<value>` | `<none-or-list>` | `<reference>` |
| Controlled failure | `<value>` | `<value>` | `<none-or-list>` | `<reference>` |

Status: `PASS / FAIL / GAP / N/A`. Distinguish service-provided spans from application
ADOT/OTEL spans: `<service result / application result>`.

## 7. Data Governance and Pipeline

| Check | Result | Evidence / gap |
|---|---|---|
| Sensitive fields redacted | `PASS / FAIL` | `<reference>` |
| IAM roles least privilege | `PASS / FAIL` | `<reference>` |
| KMS and key policy | `PASS / FAIL / N/A` | `<reference>` |
| Retention and deletion | `PASS / FAIL` | `<reference>` |
| Firehose/S3 backup/table delivery | `PASS / FAIL / N/A` | `<reference>` |
| Pipeline failure alarm | `PASS / FAIL / N/A` | `<reference>` |
| Cleanup | `COMPLETE / FAILED` | `<reference>` |

## 8. Conclusion

```yaml
functional_result: PASS | FAIL | BLOCKED
observability_readiness:
  metrics: PASS | FAIL | GAP | N/A
  logs: PASS | FAIL | GAP | N/A
  traces: PASS | FAIL | GAP | N/A
  application_adot: PASS | FAIL | GAP | N/A
cross_signal_correlation: PASS | FAIL
observability_gaps:
  - gap: <description>
    owner: <role>
    due_at: <date>
cost_impact: <estimate-or-measured>
next_action: <specific action>
```

Observability is `PASS` only when success and controlled failure are distinguishable,
applicable signals have evidence, correlation works, and data governance passes. See the
[cross-service observability blueprint](../docs/OBSERVABILITY_BLUEPRINT.en.md).

