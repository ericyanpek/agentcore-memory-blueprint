# AgentCore Memory 最低控制基线

> 主版本：中文。English: [CONTROL_BASELINE.en.md](CONTROL_BASELINE.en.md)。
> 基准日期：2026-08-04。适用于使用 AgentCore Memory 的生产工作负载。

## 1. 规范强度与风险等级

- **MUST**：发布前必须满足；缺失时只能走有期限的正式例外。
- **SHOULD**：默认满足；不采用时必须记录理由和补偿控制。
- **MAY**：按风险与成本选择，不构成最低发布阻断。

| 风险等级 | 示例 | 附加门槛 |
|---|---|---|
| 低 | 无个人数据的内部演示 | 最低 MUST；仅合成数据 |
| 中 | 员工偏好、内部项目上下文 | CMK、私网、删除传播、访问复核 |
| 高 | 客户数据、受监管数据、跨团队共享知识 | 独立账户/资源、双人审批、内容双检、DR/IR 演练 |
| 禁止 | 密钥、token、密码、未经授权的敏感数据 | 不得进入 Memory；先阻断和清理 |

## 2. 控制目录

| ID | 强度 | 控制要求 | 最低证据 | 高风险附加要求 | Owner |
|---|---|---|---|---|---|
| MEM-GOV-001 | MUST | 为每个 Memory 指定业务 owner、数据 owner、环境、Region 和用途 | 资源清单、标签、架构决策记录 | 季度 owner 复核 | 平台 |
| MEM-GOV-002 | MUST | 生产与非生产位于独立账户，发布角色与 Runtime 角色分离 | Organizations 结构、角色 trust/policy | SCP 阻止跨环境写入 | 平台 |
| MEM-GOV-003 | MUST | 个人自动提取与人工审核共享知识使用不同 Memory 或等强资源边界 | IaC、Memory ARN、角色矩阵 | 独立 CMK 与独立日志访问 | 应用 |
| MEM-ID-001 | MUST | actor 从已验证 identity claim 或受控 principal 派生，不接受模型或 body 覆盖 | 映射代码、token 测试、篡改负测 | 双通道身份评审 | 应用 |
| MEM-ID-002 | MUST | 数据面 action 限于精确 Memory ARN，不使用 `bedrock-agentcore:*` | IAM policy、静态扫描 | permission boundary/SCP | 安全 |
| MEM-ID-003 | MUST | 在支持的 API 上用 actor/session/namespace condition key 限定范围 | IAM policy、允许/拒绝实测 | 每季度跨租户探测 | 安全 |
| MEM-ID-004 | MUST | 共享 Runtime principal 增加应用层 actor 归属校验 | 单元测试、端到端负测、审计日志 | 独立授权服务或 session tag | 应用 |
| MEM-ID-005 | MUST | 提案、审批、发布和 break-glass 删除职责分离，禁止自批 | 角色矩阵、API 测试、审批日志 | 双人批准发布/删除 | 数据 owner |
| MEM-NET-001 | MUST | 中高风险工作负载使用 AgentCore control/data interface endpoint | VPC endpoint、DNS、路由、SG | 禁止公网 egress 的负测 | 平台 |
| MEM-NET-002 | MUST | endpoint policy 和 SG 只允许批准的 principal/来源 | policy、reachability/flow log | 专用 endpoint 与子网 | 网络 |
| MEM-DAT-001 | MUST | 写前执行 schema、数据分类、凭据和 PII 检查 | 规则配置、正负样例、阻断日志 | 存储前和读取后双检 | 数据 owner |
| MEM-DAT-002 | MUST | 敏感数据使用 customer managed KMS key，启用轮换并收敛 key policy | Memory 配置、key policy、Config/Security Hub | 独立 key、禁用演练 | 安全 |
| MEM-DAT-003 | MUST | `eventExpiryDuration` 是业务最短值，长期记录有独立保留策略 | 配置、保留矩阵、批准记录 | 法律保留与数据主体流程 | 数据 owner |
| MEM-DAT-004 | MUST | 删除传播覆盖 event、record、流、审计副本、日志和缓存 | 删除 runbook、季度演练证据 | 独立验证者签字 | 数据 owner |
| MEM-DAT-005 | MUST | metadata、日志和 trace 默认不含 secret、token 或原始敏感内容 | 字段清单、脱敏测试、日志抽样 | 自动 DLP 检查 | 安全 |
| MEM-WRT-001 | MUST | 共享知识只能经 schema、证据和人工审核后由专用角色写入 | 状态机、候选记录、IAM、审批证据 | 审核理由必填、证据不可变 | 数据 owner |
| MEM-WRT-002 | MUST | 批量写入检查每条结果并区分瞬时/永久失败 | 单元测试、失败注入、DLQ/告警 | 持久重驱和人工对账 | 应用 |
| MEM-WRT-003 | MUST | 创建、更新、复制和删除使用稳定幂等标识 | 重放测试、无重复记录查询 | 跨 Region 去重账本 | 应用 |
| MEM-RET-001 | MUST | 检索同时受 namespace 和批准状态/数据分类过滤 | 请求日志、过滤测试、越权负测 | 精确 namespace，不使用宽泛 path | 应用 |
| MEM-RET-002 | MUST | 注入模型前标注来源与权威等级，并再次执行内容检查 | prompt 构建测试、trace、阻断测试 | 权威冲突必须拒答或升级 | 应用 |
| MEM-OBS-001 | MUST | correlation ID 贯穿入口、Memory、审批、record 和流消费者 | 一条端到端 trace/日志查询 | 跨账户集中查询 | SRE |
| MEM-OBS-002 | MUST | 告警覆盖错误、限流、提取中断、流失败、积压和异常成本 | 告警清单、测试通知、runbook | 7x24 值班与升级 | SRE |
| MEM-OBS-003 | MUST | 记录主体、actor、session、namespace、action、结果和错误码，内容默认脱敏 | 审计 schema、样例、访问控制 | 不可变集中归档 | 安全 |
| MEM-OBS-004 | MUST | 每个账户/Region 启用并验证 CloudWatch Transaction Search；资源 tracing 状态入证据 | readiness 配置、service trace ID | 跨账户 trace 查询 | 平台 |
| MEM-OBS-005 | MUST | 显式配置 Memory vended log delivery、KMS、保留和 destination policy | delivery 配置、成功/失败 event ID | 独立 CMK 和日志账户 | SRE |
| MEM-OBS-006 | MUST | 每项实验分别交付 Metrics、Logs、Traces，且含成功与受控失败路径 | `observability-evidence.md` | 独立复核证据完整性 | SRE |
| MEM-OBS-007 | MUST | 区分服务遥测与应用 ADOT/OTEL；应用 span 使用 IAM role 且字段白名单脱敏 | instrumentation 配置、span 抽样、role policy | 自动 DLP | 应用 |
| MEM-OBS-008 | MUST | 缺失/不支持的信号标记 `GAP/N/A`，附官方依据、补偿控制、owner 和日期 | 缺口登记与工单 | 发布前关闭所有适用 GAP | 服务 owner |
| MEM-OBS-009 | SHOULD | 需长期分析时使用 Logs -> Firehose -> S3 Tables，并配置 error backup、重试与 schema | pipeline 测试、Iceberg 查询、删除测试 | 跨账户数据平台 | 数据平台 |
| MEM-OBS-010 | MUST | 对 telemetry silence、subscription、transform、delivery、backup 和 table commit 失败告警 | 故障注入、告警历史、runbook | 7x24 升级与重驱对账 | SRE |
| MEM-REL-001 | MUST | 同步调用有超时；读取可降级无记忆；治理写入不得静默成功 | 故障注入、告警、响应契约 | 多 AZ 依赖与容量验证 | SRE |
| MEM-REL-002 | MUST | 明确 STM/LTM RPO/RTO、复制、failover、failback 和删除传播 | DR 设计、演练报告 | 至少年度完整切换 | SRE |
| MEM-QUO-001 | MUST | 发布前采集账户/Region 实际配额并按峰值压测 | quota 快照、负载报告、增额工单 | 30% 以上安全余量 | SRE |
| MEM-CST-001 | MUST | 预算覆盖事件、记录、检索、提取模型、Kinesis、KMS、日志和复制 | 成本模型、预算与告警 | 按租户/业务单元分摊 | FinOps |
| MEM-SDL-001 | MUST | Memory、IAM、KMS、endpoint 和流全部由 IaC 管理并做 drift 检测 | CDK synth、模板、drift 报告 | 签名制品和双人发布 | 平台 |
| MEM-SDL-002 | MUST | 固定 SDK/client 版本并验证所用 API service model | lock/requirements、构建日志、契约测试 | SBOM、漏洞门禁 | 平台 |
| MEM-SDL-003 | MUST | indexed keys、策略、namespace 和保留变更有迁移与回滚 | 变更单、双写/回填计划、回滚记录 | 蓝绿资源迁移演练 | 应用 |
| MEM-IR-001 | MUST | 建立投毒、跨租户、误删、KMS、流和配额事件 runbook | runbook、桌面演练、责任表 | 半年技术演练 | 安全 |
| MEM-IR-002 | MUST | break-glass 角色限时、双批准、告警并事后复核 | role policy、审批、CloudTrail/审计 | 自动到期和独立复核 | 安全 |
| MEM-REV-001 | SHOULD | 每季度复核角色、condition key、namespace 和 owner | 访问复核报告 | 高风险升级为 MUST | 安全 |
| MEM-RED-001 | SHOULD | 用投毒、提示词注入、陈旧事实和跨租户手法做红队验证 | 测试集、结果、整改项 | 高风险升级为 MUST | 安全 |
| MEM-STR-001 | MAY | 启用 `METADATA_ONLY` record streaming 供审计和复制 | 流配置、消费者幂等测试 | 禁止不必要的 `FULL_CONTENT` | 平台 |

condition key 和 action 以
[Service Authorization Reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_bedrock-agentcore.html)
为准；配额以
[AgentCore quotas](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html)
为准。

## 3. 最低证据包

每次生产发布至少包含：

1. 架构图、数据流、账户/Region/租户边界和 RACI；
2. CDK/CloudFormation synth 产物与 IAM/KMS/endpoint policy；
3. 实际 Service Quotas 和成本估算快照；
4. actor、session、namespace、审批与删除的正向/负向测试结果；
5. 完整的 [`observability-evidence.md`](../experiments/observability-evidence.md)，含
   成功/失败路径与 Metrics、Logs、Traces；
6. 告警测试、runbook 和 cleanup/rollback 记录；
7. 未通过控制、例外编号、到期日和补偿控制；
8. 无真实 ARN、账户、token、secret 或客户数据的脱敏确认。

## 4. 发布门禁

| 门禁 | 通过条件 | 阻断条件 |
|---|---|---|
| G1 事实 | Region/API/配额/价格已按日期复核 | 使用未注明日期的 sample 数值 |
| G2 身份 | actor 不可由客户端覆盖，跨租户负测通过 | 共享角色无 actor 归属校验 |
| G3 数据 | 分类、CMK、保留和删除传播有证据 | secret/PII 可无阻断进入 Memory |
| G4 写入 | 共享写经证据、审批、职责分离 | agent/模型拥有共享直写 |
| G5 运营 | 三类信号、关联、告警、配额、成本、故障与 cleanup 通过 | 任一适用信号为 GAP、写失败静默、无删除/恢复 runbook |
| G6 供应链 | IaC、SDK 固定、测试和 drift 检查通过 | 控制台漂移或 `service:*` |

任何 MUST 失败即阻断；只有获批且未到期的例外可以临时放行。高风险工作负载不得以“POC”
为理由绕过身份、数据分类、加密或审计控制。

## 5. 例外模板

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

- 例外 **MUST** 有不超过 90 天的到期日，不得自动续期。
- 例外 **MUST** 说明具体风险、影响范围和可验证补偿控制。
- 高风险数据的身份、secret 阻断和审计控制 **MUST NOT** 通过例外永久豁免。

## 6. 控制验证频率

| 频率 | 验证 |
|---|---|
| 每次发布 | IaC、IAM、SDK、单元/契约/负向测试 |
| 每月 | 成本、配额、告警、drift、过期例外 |
| 每季度 | 访问复核、删除传播、owner、跨租户探测 |
| 每半年 | 投毒/越权事件演练与 break-glass |
| 每年 | 完整 DR/failback 和数据生命周期审计 |

实施步骤见[../experiments/README.md](../experiments/README.md)，架构背景见
[ENTERPRISE_GOVERNANCE_BLUEPRINT.md](ENTERPRISE_GOVERNANCE_BLUEPRINT.md)。
