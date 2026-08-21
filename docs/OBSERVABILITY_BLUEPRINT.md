# AgentCore 跨服务可观测性蓝图

> 主版本：中文。English: [OBSERVABILITY_BLUEPRINT.en.md](OBSERVABILITY_BLUEPRINT.en.md)。
> 事实复核日期：2026-08-05。本文是设计与实验规范，不代表已在任何 AWS 账户启用或验证。

## 1. 范围与验收原则

本蓝图覆盖 AgentCore Runtime/Harness、Memory、Gateway、built-in tools、调用这些资源的
应用代码，以及 Bedrock Knowledge Bases。每项实验必须同时回答：

1. 功能是否按预期成功，并能按预期产生一个受控失败；
2. Metrics、Logs、Traces 分别提供了什么证据；
3. 遥测是否经过脱敏、加密、保留、最小权限和成本控制；
4. 证据能否由 request、session 或 trace ID 交叉定位。

Console 图表不能单独作为验收证据。未配置 log delivery、未启用 tracing 或查询不到 span
时，结论应记录为“遥测缺口”，不得据此判断“没有错误”。

## 2. 三层遥测模型

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

服务遥测不能解释自定义业务步骤、prompt 版本、路由理由、重试或审批状态；应用 ADOT/OTEL
不能替代服务自身的错误、限流和资源维度。两者必须用受控关联标识连接，且不得把原始 secret、
token、敏感 prompt 或完整 tool payload 写入日志或 span attributes。

## 3. Metrics、Logs 与 Traces

| 信号 | 回答的问题 | 最低证据 | 不足以证明 |
|---|---|---|---|
| Metrics | 是否发生、规模、趋势和 SLO 如何 | namespace、metric、dimensions、统计、时间窗、延迟 | 单次失败原因与跨步骤因果 |
| Logs | 某次处理做了什么、为什么失败 | destination、group/prefix、event ID、retention、KMS | 完整调用链与总体趋势 |
| Traces | 一次请求跨 agent、Gateway、tool、Memory 的因果链 | trace ID、root/child spans、缺失边 | 日志内容治理与长期趋势 |

实验必须分别填写三类证据。某类信号不受资源支持时，记录官方依据、补偿性应用遥测和 owner，
不得用另一类信号代替后将该项标为通过。

## 4. 一次性账户与 Region 准备

1. **MUST** 在每个目标账户和 Region 确认 CloudWatch Transaction Search 已启用，并确认
   OpenTelemetry spans ingestion 状态。它是查看 AgentCore service spans/traces 的前提，
   不是某个 Gateway 自动开启的属性。
2. **MUST** 逐资源记录 Metrics、Logs、Spans 的默认状态。AWS 当前说明所有 AgentCore
   资源默认提供 metrics，但带星号的 logs/spans 需要显式启用。
3. **MUST** 对 Memory 和 Gateway 显式配置需要的 vended log delivery。支持的目标按当前
   服务文档选择 CloudWatch Logs、Amazon S3 或 Firehose。
4. **MUST** 为 CloudWatch Logs 设置 customer managed KMS key（敏感工作负载）、明确保留期、
   resource policy 和访问审计。
5. **MUST** 使用 IAM role 向 OTEL backend 发送遥测，不使用长期 access key。
6. **SHOULD** 在集中 observability 账户建立跨账户查询；源账户仍保留最小排障能力。

AWS 当前说明 Runtime 创建时默认建立 service-provided log group；Memory 和 Gateway 不会
自动配置日志目标；built-in tools 不默认提供服务日志，需由应用代码输出并配置目标。上线前
必须以当日文档和实际资源配置复核这些默认值。

## 5. 资源测试矩阵

| 资源 | 成功路径 | 受控失败 | Metrics | Logs | Traces / 应用补偿 |
|---|---|---|---|---|---|
| Runtime / Harness | 成功调用与会话完成 | timeout、模型或工具错误 | invocation、latency、error、usage | service/application logs | agent root、model/tool child spans；业务步骤用 ADOT |
| Memory | 写入、读取、提取或 TTL 行为 | 错误 ID、权限拒绝、容量边界 | operation、latency、error | Memory delivery 明确启用后查询 | Memory operation span；关联 actor/session 的脱敏值 |
| Gateway | `initialize`、`tools/list`、`tools/call` | target、权限或输入失败 | invocation、latency、error、throttle | Gateway application log delivery | Gateway/tool spans；保留原始下游错误分类 |
| built-in tools | Browser/Code Interpreter 正常结果 | 输入、权限或运行失败 | 每工具调用、错误、延迟 | 服务不默认提供时使用应用日志 | tool span 与父 span；记录数据/成本边界 |
| Knowledge Bases | ingestion、retrieve、retrieve-and-generate | ingestion 失败或空召回 | KB 运行与 ingestion 指标 | ingestion delivery 与应用日志 | 由调用应用 trace 关联；不冒充 Gateway trace |

指标名称、namespace 和 dimensions 会演进，必须从目标 Region 的当前 AWS 文档或 CloudWatch
实际资源发现后写入证据，不从本表推断精确名称。Knowledge Bases 有独立的运行指标和
ingestion logs；其 Console “Observability” 不表示 AgentCore Gateway 日志或 trace 已配置。

## 6. 每次实验的证据门禁

每个 E00-E07 实验都使用
[observability-evidence.md](../experiments/observability-evidence.md)，并满足：

- **MUST** 记录账户别名、Region、resource ARN 脱敏值、UTC 时间窗和调用身份；
- **MUST** 执行一条成功路径和一条受控失败路径；
- **MUST** 分别给出 Metrics、Logs、Traces 的位置、ID、观察值与摄取延迟；
- **MUST** 记录 Transaction Search、resource tracing 和 log delivery 的实际状态；
- **MUST** 用 request/session/trace ID 关联可用信号，并列出每个 missing link；
- **MUST** 检查 redaction、KMS、retention、IAM role 和 cleanup；
- **MUST** 将不存在或未配置的信号标为 `GAP`，指定 owner 和完成日期。

## 7. 关联与字段规范

应用产生一个不可由模型覆盖的 `correlation_id`，并在可用的协议字段中传播。平台返回的
request ID、runtime session ID、trace ID、span ID、Memory event/record ID 和 Gateway
target/tool 名称作为独立字段保留，不拼接进一个不可解析字符串。

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

`actor_id`、`session_id`、URL、prompt 和 tool 参数按数据分类处理；需要关联时优先使用稳定
tokenization/HMAC 值，而不是原文。禁止记录 AWS credentials、OAuth token、API key 或密码。

## 8. 日志、Firehose 与 S3 Tables

```text
AgentCore vended/application logs
  -> CloudWatch Logs
  -> subscription filter
  -> Amazon Data Firehose
  -> transform: allowlist + redact + normalize + partition keys
  -> Amazon S3 Tables (Apache Iceberg)
  -> Athena / Redshift / Spark / QuickSight
```

| 组件 | 主要职责 | 不应被当作 |
|---|---|---|
| CloudWatch Logs | 近实时排障、Logs Insights、metric filters、告警与订阅 | 唯一的长期关联分析仓库 |
| Firehose | 缓冲、转换、压缩、路由、重试与投递 | 查询引擎或记录系统 |
| S3 Tables | 托管 Iceberg 表、长期结构化趋势与跨资源分析 | 实时日志 tail、告警或 SIEM |

只有日常排障时可停在 CloudWatch Logs。需要跨月质量、可靠性和成本分析时，再引入 Firehose
与 S3 Tables。Firehose 直接支持向 hosted in Amazon S3 Tables 的 Iceberg tables 投递；
生产设计必须配置 S3 error backup、重试、CloudWatch error logging、schema version 和
Lake Formation/IAM 权限。按日期、环境和资源类型分区，禁止按高基数 trace ID 分区。

## 9. 数据治理与生命周期

- **MUST** 在订阅前或 Firehose transform 中采用字段白名单和脱敏；转换失败不得回退为原文。
- **MUST** 分别定义 CloudWatch、S3 error backup、Iceberg snapshot 和查询结果的保留/删除。
- **MUST** 对 Logs、backup bucket、S3 Tables 和查询结果验证 encryption at rest 与 key policy。
- **MUST** 将 delivery role、transform role、analyst role 分离并使用最小权限。
- **MUST** 验证删除不仅产生 Iceberg delete marker，还按政策清理底层文件、snapshot 和备份。
- **SHOULD** 启用 S3 Tables compaction、snapshot expiration 和 unreferenced-file cleanup。
- **SHOULD** 对高风险字段做自动 DLP 抽样，并将命中作为安全事件处理。

## 10. 告警、成本与管道自监控

| 告警 | 起步判据 | 目的 |
|---|---|---|
| Error rate | 5 分钟内超过业务 SLO | 发现系统性失败 |
| p95/p99 latency | 连续多个周期超过 SLO | 分离模型、Gateway、tool 或 Memory 变慢 |
| Throttling/quota | 首次记录，持续后告警 | 防止容量导致用户失败 |
| Tool/target failure | 单个 target/tool 异常升高 | 防止整体成功率掩盖局部故障 |
| Memory/session failure | TTL、session-not-found 或提取失败增长 | 验证生命周期 |
| KB ingestion/empty retrieval | job 失败或空召回异常 | 区分摄取、权限与检索质量 |
| Pipeline failure | subscription、transform、delivery、backup 或 table commit 失败 | 防止服务正常但证据丢失 |
| Telemetry silence | 有业务流量但某信号长时间为零 | 发现采集配置漂移 |

阈值必须按业务 SLO 和基线确定。成本模型至少覆盖 model token、Gateway/tool invocation、
Memory operation、CloudWatch ingest/storage/query、Firehose delivery/transform、S3 Tables
storage/maintenance 与分析查询扫描量。

## 11. 职责与发布条件

| 责任 | Owner | 发布证据 |
|---|---|---|
| Transaction Search、跨账户 CloudWatch | 平台/SRE | account/Region readiness 截图或 API 结果 |
| resource tracing 与 log delivery | 服务 owner | 配置、destination policy、成功/失败事件 |
| 应用 ADOT/OTEL 与关联字段 | 应用团队 | instrumentation test、trace graph、字段清单 |
| redaction、KMS、retention、IAM | 安全/数据 owner | policy、抽样、删除测试、访问复核 |
| Firehose/S3 Tables 与成本 | 数据平台/FinOps | pipeline test、error backup、预算与告警 |

任何适用的 Metrics、Logs 或 Traces 证据为 `GAP`，或成功/失败路径不能区分，都阻断生产发布。
实验环境可以保留 `BLOCKED` 状态继续设计，但不得将功能成功等同于可运营。

## 12. 官方来源

- [AgentCore observability configuration](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-configure.html)
- [AgentCore generated observability data](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-service-provided.html)
- [Get started with AgentCore Observability](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-get-started.html)
- [Knowledge Bases managed observability](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-observability.html)
- [Knowledge Bases ingestion logging](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-bases-logging.html)
- [Firehose Apache Iceberg destination](https://docs.aws.amazon.com/firehose/latest/dev/apache-iceberg-destination.html)
- [Amazon S3 Tables](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-tables.html)
