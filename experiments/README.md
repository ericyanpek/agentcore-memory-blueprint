# AgentCore Memory 企业实验路线

> 主版本：中文。English: [README.en.md](README.en.md)。
> 设计基准：2026-08-04。官方 sample 固定到
> `fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645`（2026-08-03）。
> **本路线尚未执行，不代表已部署或已验证任何客户账户。**

## 1. 运行原则

1. 只在批准的 sandbox 账户使用合成数据；生产账户禁止边学边建。
2. 每个实验使用独立前缀、成本标签和 cleanup owner。
3. 先记录账户、Region、CLI/SDK、配额、价格和 sample commit，再创建资源。
4. 每项必须同时做正向和负向测试；“没有读到数据”必须先证明数据确实存在。
5. 所有 ARN、账户、token、secret 和客户数据在证据包中脱敏。
6. 资源创建使用 IaC；探索性 CLI 成功后必须回写成可重复模板。
7. 任何 cleanup 失败都视为实验失败并产生工单。
8. 每项实验使用 [observability-evidence.md](observability-evidence.md)，分别记录 Metrics、
   Logs、Traces；未配置或不支持的信号标记 `GAP/N/A`，不得用“无错误”替代证据。

官方样例根目录：
[AgentCore Memory samples](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory)。

## 2. 通用前置条件

- 临时 IAM role；禁止 IAM user 长期密钥；
- AWS CLI v2、Python 3.12、`boto3>=1.43.36,<2`；
- 目标 Region 支持 AgentCore Memory；
- sandbox 账户预算和最大实验时长；
- 可写的本地证据目录，以及批准的集中日志位置；
- 每个目标账户/Region 的 CloudWatch Transaction Search、span ingestion、resource tracing
  和 vended log delivery readiness 记录；
- 不使用真实用户对话、客户标识、凭据或内部 secret。

开始前记录：

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

## 3. E00：来源、Region、工具链、配额和成本基线

| 字段 | 内容 |
|---|---|
| 目的 | 在创建资源前确认服务可用性、SDK 模型、当前配额、价格和证据位置 |
| Sample 来源 | [`00-getting-started`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/00-getting-started) |
| 账户 / Region | sandbox；一个已批准且支持 Memory 的 Region |
| 创建资源 | 无 |
| 正向测试 | CLI 能发现 `bedrock-agentcore-control`/`bedrock-agentcore`；SDK 包含 metadata、batch、stream API |
| 负向测试 | 旧 SDK 对所需字段失败；不支持 Region 的调用被明确拒绝 |
| 成功标准 | 固定 commit、版本、Region、配额、价格、预算和 cleanup owner 均入证据包 |
| 对应控制 | MEM-GOV-001、MEM-QUO-001、MEM-CST-001、MEM-SDL-002 |
| 日志 / Trace / 审计 | 命令版本与只读查询输出；不得包含凭证 |
| Observability 证据 | Metrics/Logs/Traces 记为 `N/A-readiness`；保存 Transaction Search、span ingestion、log delivery 能力与应用 ADOT 决策 |
| 成本 | USD 0；只读查询 |
| Cleanup | 无资源；删除临时输出中的敏感环境信息 |
| 架构决策 | 选定主 Region、SDK 下限和成本估算口径 |

步骤：

1. 核对 [Region](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-regions.html)、
   [配额](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html)
   和[价格](https://aws.amazon.com/bedrock/agentcore/pricing/)的日期。
2. 记录 `aws --version`、Python、boto3、CDK 和 AgentCore client 版本。
3. 在 Service Quotas 读取实际账户/Region 配额，不用文档默认值替代。
4. 以预计回合、事件、记录、检索和保留期形成月成本上下界。

## 4. E01：最小功能与资源生命周期

| 字段 | 内容 |
|---|---|
| 目的 | 验证 Memory 创建、短期事件、异步长期提取、检索和删除 |
| Sample 来源 | [`01-events-and-sessions`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/01-short-term-memory/01-events-and-sessions)、[`01-built-in-strategies`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/02-long-term-memory/01-built-in-strategies) |
| 账户 / Region | sandbox；E00 选定 Region |
| 创建资源 | 1 个测试 Memory、最小策略、临时 CMK 或批准的测试 key |
| 正向测试 | Create/Get、CreateEvent/ListEvents、等待提取、Retrieve、Delete |
| 负向测试 | 非法 expiry、重复名称、错误 memoryId、删除后读取 |
| 成功标准 | STM 可立即读；LTM 在限定等待期出现；删除后资源不可访问 |
| 对应控制 | MEM-GOV-001、MEM-DAT-003、MEM-REL-001、MEM-SDL-001 |
| 日志 / Trace / 审计 | control/data API 结果、提取等待时长、删除确认 |
| Observability 证据 | 成功写读与错误 memoryId 分别记录 metric、log event、trace；缺失 log delivery 明确为 `GAP` |
| 成本 | 少量事件、记录和检索；记录实际账单估算 |
| Cleanup | `try/finally` 删除 Memory；确认 retained key/日志处理符合计划 |
| 架构决策 | 事件保留期、策略类型、轮询上限和资源删除语义 |

禁止以固定 sleep 代替有超时的状态轮询。异步提取超时应记录为失败，不得把历史记录误判为
本轮结果。

## 5. E02：身份、最小权限和跨服务调用

| 字段 | 内容 |
|---|---|
| 目的 | 证明 actor/session/namespace 绑定到身份，且读写角色最小化 |
| Sample 来源 | [`iam-scoped-access`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/05-security/01-iam-scoped-access)、[`cognito-federated-identity`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/05-security/02-cognito-federated-identity) |
| 账户 / Region | sandbox；单账户先验证，再可选跨账户调用 |
| 创建资源 | Memory、两个测试身份、读/写/发布角色、测试策略 |
| 正向测试 | Alice 读写自己的 event/namespace；发布器写共享 namespace |
| 负向测试 | Alice 读 Bob；body 覆盖 actor；读角色批量写；发布器读个人 |
| 成功标准 | 越权均为明确 `AccessDeniedException`/403，且允许路径有非空数据 |
| 对应控制 | MEM-ID-001 至 MEM-ID-005、MEM-RET-001 |
| 日志 / Trace / 审计 | STS identity、策略版本、错误码、actor/namespace 脱敏记录 |
| Observability 证据 | 允许与 AccessDenied 路径分别记录 Metrics/Logs/Traces，证明 actor/namespace 仅以脱敏关联值出现 |
| 成本 | E01 费用 + Cognito/日志的微量使用 |
| Cleanup | 删除测试身份、role policy、Memory 和临时配置 |
| 架构决策 | `sub`、Identity Pool identityId 或 principal tag 中哪一个是 actor |

若 Runtime 使用共享 role，增加直接权限探测与应用归属校验两层测试；只证明“Bob 返回空”
不构成隔离证据。

## 6. E03：私网、多账户和多租户边界

| 字段 | 内容 |
|---|---|
| 目的 | 验证 PrivateLink、DNS、endpoint policy、租户边界和禁止绕过 |
| Sample 来源 | [`actor-session-isolation`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/01-short-term-memory/03-actor-session-isolation)、[`namespaces`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/02-long-term-memory/04-namespaces) |
| 账户 / Region | 网络 sandbox + 工作负载 sandbox；同 Region |
| 创建资源 | control/data interface endpoint、SG、私有 DNS、Memory、测试角色 |
| 正向测试 | 允许的 SigV4 principal 仅经私网访问精确 actor/namespace |
| 负向测试 | 公网路径、错误 VPC/source、宽 namespacePath、未批准账户、OAuth endpoint 假授权 |
| 成功标准 | flow log 证明私网路径；绕过路径失败；授权仍由 IAM 决定 |
| 对应控制 | MEM-NET-001、MEM-NET-002、MEM-ID-002、MEM-ID-003 |
| 日志 / Trace / 审计 | VPC flow log、DNS 解析、endpoint policy、AccessDenied |
| Observability 证据 | 私网成功与绕过拒绝分别关联 service signal、flow log 和应用 trace；列出跨账户 missing link |
| 成本 | interface endpoint 小时/流量 + 日志；实验后立即清理 |
| Cleanup | 删除 endpoint、ENI/SG、Memory、测试 role，确认无残留 ENI |
| 架构决策 | endpoint 所属账户、共享方式、SigV4/OAuth 取舍 |

PrivateLink 只证明网络路径，不证明用户授权。OAuth 经 endpoint 时不能依赖 endpoint policy
按 OAuth 用户做 principal 限制。

## 7. E04：数据和安全控制

| 字段 | 内容 |
|---|---|
| 目的 | 验证分类、CMK、写前/读后检查、Guardrails 边界和删除传播 |
| Sample 来源 | [`kms-encryption`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/05-security/03-kms-encryption)、[`guardrails-integration`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/03-integrations/03-guardrails-integration)、[`manage-extraction`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/02-long-term-memory/08-manage-extraction) |
| 账户 / Region | 安全批准的 sandbox |
| 创建资源 | CMK Memory、分类/阻断组件、测试 Guardrail、审计存储 |
| 正向测试 | 允许内容写入/提取/检索；`SKIP` 事件不产生 LTM；删除传播完成 |
| 负向测试 | synthetic secret/PII、投毒指令、错误 key policy、禁用 key、日志泄露 |
| 成功标准 | 禁止内容在存储前阻断；召回内容在注入前再检；删除有全链路证据 |
| 对应控制 | MEM-DAT-001 至 MEM-DAT-005、MEM-RET-002、MEM-IR-001 |
| 日志 / Trace / 审计 | 只保存命中类型和 hash/ID；不保存测试 secret 原文 |
| Observability 证据 | 允许与 synthetic secret 阻断路径分别给出三类信号，并抽样确认 log/span 未含测试原文 |
| 成本 | Guardrails、KMS、日志、事件/记录费用 |
| Cleanup | 删除测试记录/Memory/Guardrail；按计划保留审计摘要；安排 key 删除窗口 |
| 架构决策 | 哪些分类禁止写、哪些可 STM 但 `SKIP` LTM、删除 SLO |

## 8. E05：可观测性、审计和故障注入

| 字段 | 内容 |
|---|---|
| 目的 | 证明 correlation、指标、摄取日志、流告警和失败收敛 |
| Sample 来源 | [`observability`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/04-observability)、[`error-handling`](https://github.com/awslabs/agentcore-samples/blob/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/06-production-patterns/01-error-handling.md)、[`record-streaming`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/02-long-term-memory/09-record-streaming) |
| 账户 / Region | sandbox + 集中日志测试账户 |
| 创建资源 | log group/delivery、Transaction Search readiness、alarms、Kinesis、consumer、DLQ、测试 Memory |
| 正向测试 | request/session/trace ID 关联 metric、log、span、event/record/stream；告警测试通知到达 |
| 负向测试 | 限流、错误 namespace、KMS deny、consumer 失败、delivery/transform 失败、重复流事件 |
| 成功标准 | Metrics/Logs/Traces 区分成功/失败；每种失败进入正确告警/runbook；写失败不静默；消费幂等 |
| 对应控制 | MEM-OBS-001 至 MEM-OBS-010、MEM-WRT-002、MEM-WRT-003 |
| 日志 / Trace / 审计 | 完整 evidence template、端到端查询、告警历史、DLQ/redrive 记录 |
| Observability 证据 | 区分 service telemetry 与应用 ADOT；验证 Transaction Search、Memory log delivery、KMS/retention 和 pipeline alarm |
| 成本 | CloudWatch、Kinesis、Lambda、KMS；记录实验实际时长 |
| Cleanup | 排空/归档证据后删流、consumer、DLQ、alarms、Memory |
| 架构决策 | 采样率、保留期、`METADATA_ONLY`/`FULL_CONTENT`、升级阈值 |

## 9. E06：容量、配额、成本和恢复

| 字段 | 内容 |
|---|---|
| 目的 | 找到峰值边界并验证退避、预算、复制、failover 和 failback |
| Sample 来源 | [`cost-optimization`](https://github.com/awslabs/agentcore-samples/blob/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/06-production-patterns/02-cost-optimization.md)、[`multi-region-replication`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/06-production-patterns/00-multi-region-replication) |
| 账户 / Region | sandbox；两个批准 Region |
| 创建资源 | 主/备 Memory、Kinesis、consumer、负载发生器、预算 |
| 正向测试 | 目标负载内 SLO；STM 双写、LTM 流复制、切读和 failback |
| 负向测试 | 429、目标 Region 中断、重复事件、延迟/积压、删除不传播 |
| 成功标准 | 退避稳定；RPO/RTO 被测量；预算告警触发；已知删除缺口有控制 |
| 对应控制 | MEM-REL-001、MEM-REL-002、MEM-QUO-001、MEM-CST-001 |
| 日志 / Trace / 审计 | 负载曲线、错误率、延迟、iterator age、成本和恢复时间线 |
| Observability 证据 | 正常负载与 429/Region 故障分别给出三类信号，验证 telemetry silence 和 pipeline failure 告警 |
| 成本 | 双 Region Memory、双写、Kinesis、Lambda、日志；设硬上限 |
| Cleanup | 恢复主 Region 后停止双写、停流、删两个 Memory 和复制资源 |
| 架构决策 | 实际 RPO/RTO、容量余量、是否值得多 Region、删除复制方案 |

官方 sample 明确不复制删除且仅演示单账户。实验必须验证这一限制，不能把 sample 运行成功
写成“跨 Region 强一致”。

## 10. E07：低风险企业用例完整准入

| 字段 | 内容 |
|---|---|
| 目的 | 以合成项目知识走完身份、个人记忆、候选、审核、共享检索和退役 |
| Sample 来源 | 上述官方样例组合 + 本仓库 [`run_demo_scenario.py`](../poc/run_demo_scenario.py) 与 [`validate_bridge.py`](../bridge/validate_bridge.py) |
| 账户 / Region | 隔离的预生产账户；业务目标 Region |
| 创建资源 | 完整 CDK stack、两个 Memory、身份、审批、证据桶、日志/告警 |
| 正向测试 | 个人召回、跨会话、候选审批、逐字发布、跨用户共享 |
| 负向测试 | 跨用户、restricted/低置信度、自批、重放、无证据、超时、删除传播 |
| 成功标准 | 所有适用 MUST 有证据；无 P0/P1 缺口；cleanup/rollback 成功 |
| 对应控制 | [CONTROL_BASELINE](../docs/CONTROL_BASELINE.md) 的全部适用 MUST |
| 日志 / Trace / 审计 | 一个脱敏 evidence pack 可从请求追到审批与 record |
| Observability 证据 | 对端到端成功与权限拒绝各完成模板；任一适用信号为 `GAP` 时不得准入 |
| 成本 | 预估与实际对比，解释偏差并设生产预算 |
| Cleanup | 执行退役 runbook；保留必要审计摘要，证明云资源删除 |
| 架构决策 | 是否准入、剩余风险、例外、owner、生产分阶段计划 |

E07 使用真实但低风险的企业流程结构，数据必须是合成的。未经明确授权不得把该实验切到
生产账户或真实客户数据。

## 11. 证据包模板

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
  observability_template: <observability-evidence.md path>
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

## 12. 验收与停止条件

- 任一跨租户读取、共享直写、secret 落库或审计泄露立即停止实验并按事件处理。
- 任一资源 cleanup 失败，实验状态保持 `FAIL`，直至独立查询确认清理。
- 负向测试若因 DNS、配置或资源不存在而失败，不得算作授权控制通过。
- 配额、价格、Region 与 sample commit 在实验开始时重新记录。
- 任一适用的 Metrics、Logs 或 Traces 为 `GAP`，或成功/失败路径不能区分，生产准入失败。
- 只有 E00–E06 通过且所有 MUST 有证据，E07 才可申请执行。

控制定义见[../docs/CONTROL_BASELINE.md](../docs/CONTROL_BASELINE.md)，样例映射见
[../docs/AWS_SAMPLE_CATALOG.md](../docs/AWS_SAMPLE_CATALOG.md)，跨服务信号规范见
[../docs/OBSERVABILITY_BLUEPRINT.md](../docs/OBSERVABILITY_BLUEPRINT.md)。
