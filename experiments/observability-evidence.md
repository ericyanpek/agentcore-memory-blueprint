# Observability 实验证据

> 主版本：中文。English: [observability-evidence.en.md](observability-evidence.en.md)。
> 每个 E00-E07 实验复制一份并填写。不得写入真实凭据、token、secret、敏感 prompt 或客户数据。

## 1. 实验身份

| 字段 | 值 |
|---|---|
| Experiment / run ID | `<E0X/run-id>` |
| Resource type / ARN | `<type>/<redacted-arn>` |
| Account alias / Region | `<redacted>/<region>` |
| UTC time range | `<start>/<end>` |
| Caller role | `<role-name-only>` |
| Sample commit / app version | `<sha>/<version>` |
| Data class | `synthetic` |

## 2. Readiness

| 检查 | 状态 | 证据 |
|---|---|---|
| CloudWatch Transaction Search | `ENABLED / DISABLED / N/A` | `<reference>` |
| OpenTelemetry span ingestion | `ENABLED / DISABLED / N/A` | `<reference>` |
| Resource tracing | `ENABLED / DISABLED / UNSUPPORTED` | `<reference>` |
| Vended log delivery | `CONFIGURED / MISSING / UNSUPPORTED` | `<destination/config>` |
| Application ADOT/OTEL | `CONFIGURED / NOT_REQUIRED / GAP` | `<reference>` |

## 3. 功能路径

| 路径 | 输入摘要 | 预期 | 实际 | 结果 |
|---|---|---|---|---|
| Success | `<redacted>` | `<behavior>` | `<behavior>` | `PASS / FAIL` |
| Controlled failure | `<redacted>` | `<exact error/outcome>` | `<error/outcome>` | `PASS / FAIL` |

关联标识：

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

状态：`PASS / FAIL / GAP / N/A`。若为 `GAP/N/A`，填写官方依据、补偿控制、owner 和日期：
`<reason / compensation / owner / due-date>`。

## 5. Logs

| Path | Destination / group / prefix | Event ID | Redaction checked | Retention / KMS | Evidence |
|---|---|---|---|---|---|
| Success | `<value>` | `<value>` | `YES / NO` | `<days>/<key-alias>` | `<reference>` |
| Controlled failure | `<value>` | `<value>` | `YES / NO` | `<days>/<key-alias>` | `<reference>` |

状态：`PASS / FAIL / GAP / N/A`。未配置 log delivery 必须写 `GAP`，不得解释为没有错误。

## 6. Traces

| Path | Trace / root span | Required child spans | Missing links | Evidence |
|---|---|---|---|---|
| Success | `<value>` | `<value>` | `<none-or-list>` | `<reference>` |
| Controlled failure | `<value>` | `<value>` | `<none-or-list>` | `<reference>` |

状态：`PASS / FAIL / GAP / N/A`。区分 service-provided spans 与 application ADOT/OTEL spans：
`<service result / application result>`。

## 7. Data Governance and Pipeline

| 检查 | 结果 | 证据 / 缺口 |
|---|---|---|
| Sensitive fields redacted | `PASS / FAIL` | `<reference>` |
| IAM roles least privilege | `PASS / FAIL` | `<reference>` |
| KMS and key policy | `PASS / FAIL / N/A` | `<reference>` |
| Retention and deletion | `PASS / FAIL` | `<reference>` |
| Firehose/S3 backup/table delivery | `PASS / FAIL / N/A` | `<reference>` |
| Pipeline failure alarm | `PASS / FAIL / N/A` | `<reference>` |
| Cleanup | `COMPLETE / FAILED` | `<reference>` |

## 8. 结论

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

只有成功与受控失败都能区分、适用信号有证据、关联链路成立且数据治理通过，才可将本实验
Observability 标为 `PASS`。详细规范见
[跨服务可观测性蓝图](../docs/OBSERVABILITY_BLUEPRINT.md)。

