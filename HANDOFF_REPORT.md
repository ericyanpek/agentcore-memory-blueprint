# AgentCore Memory 企业治理蓝图 Handoff 报告

> 主版本：中文。English: [HANDOFF_REPORT.en.md](HANDOFF_REPORT.en.md)。
> 完成日期：2026-08-05。

## 1. 本次完成内容

| 交付物 | 内容 |
|---|---|
| [README.md](README.md) | 增加企业治理入口及 Region、配额、价格事实快照 |
| [企业治理蓝图](docs/ENTERPRISE_GOVERNANCE_BLUEPRINT.md) | 心智模型、双平面、目标架构、责任边界、RACI、成熟度、Gateway 契约 |
| [最低控制基线](docs/CONTROL_BASELINE.md) | 42 条 MUST/SHOULD/MAY 控制、证据、门禁、例外模板 |
| [可观测性蓝图](docs/OBSERVABILITY_BLUEPRINT.md) | 服务遥测、应用 ADOT/OTEL、三类信号、长期分析与管道治理 |
| [企业实验路线](experiments/README.md) | E00–E07 递进实验、正负测试、成本和 cleanup |
| [Observability 证据模板](experiments/observability-evidence.md) | 每次实验的 Metrics、Logs、Traces、成功/失败与数据治理证据 |
| [官方样例目录](docs/AWS_SAMPLE_CATALOG.md) | 固定 commit、能力映射、生产差距、6 项漂移 |
| 本报告 | 未验证假设、跨服务冲突和后续 owner |

所有新增文档均提供英文翻译，并加入仓库双语结构检查。

## 2. 来源快照

| 来源 | 快照 |
|---|---|
| 调研日期 | 2026-08-04 至 2026-08-05 |
| AWS samples | `fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645`，提交日期 2026-08-03 |
| 旧 samples 基线 | `ff11ccbb89d391a7c2478160a1b66c63f0b63e59`，提交日期 2026-07-22 |
| 官方文档 | 上述来源，以及 AgentCore Observability、Knowledge Bases observability、Firehose Iceberg、S3 Tables |
| 本地证据 | 14 项云端场景检查、8 项 Identity Pool 检查、17 项 bridge 检查、CDK 和 Python 单测 |

事实优先级：Developer Guide / Release Notes > API Reference / Service Authorization
Reference > 固定 AWS samples > 本地实验 > 本蓝图架构建议。

## 3. 尚未验证的假设

| 假设 | 当前状态 | 验证方式 | 建议 owner |
|---|---|---|---|
| Memory data plane 的 CloudTrail 覆盖与字段可满足完整访问审计 | 未找到与 Gateway 同等明确的官方数据事件页面 | 在 sandbox 调用每个数据面 API 后查询 CloudTrail/Lake | Observability |
| control/data PrivateLink 在目标企业 Region 和 DNS 架构下符合预期 | 仅按官方文档设计 | 执行 E03，保留 flow log 与 endpoint policy 证据 | Network |
| 跨账户 Memory 访问和 KMS policy 模式满足目标 landing zone | 未实测 | 两 sandbox 账户执行 E02/E03 | Identity/Security |
| metadata 是否由 Memory CMK 覆盖的边界 | samples 警告不要放 secret，但产品加密边界需进一步确认 | 向 AWS Support 获取书面确认；保持禁止 secret | Security |
| 更多 metadata filter 操作符在目标 SDK/Region 全部可用 | 本仓库服务模型实测，sample 仅列三个 | E00 契约测试实际 SDK | Application |
| Harness managed Memory 的删除、切换和 owner 模型适合企业退役 | 官方文档有行为说明，本仓库未使用 Harness | Harness 蓝图做生命周期实验 | Harness |
| customer-driven multi-Region 复制达到业务 RPO/RTO | 官方 sample 可执行但未在本次运行 | E06 故障和 failback 演练 | SRE |
| Guardrails 双检的误报/漏报可接受 | 仅有架构要求 | E04 使用代表性合成数据集测量 | Security/Data |
| Transaction Search、Memory log delivery 和 service spans 在目标账户可用且关联完整 | 已按官方文档设计，未访问账户 | E00/E05 记录 readiness 并执行成功/失败路径 | Observability |
| Runtime/Harness、Gateway、built-in tools 与 KB 的 service/app telemetry 能端到端关联 | 跨服务字段规范已定义，未实测 | 各服务 owner 使用统一 evidence template | 服务 owner |
| Logs -> Firehose -> S3 Tables 的脱敏、error backup、删除和成本满足要求 | 架构已定义，未部署 | 数据平台 sandbox 做管道故障与删除实验 | Data Platform |

## 4. 与 Gateway 蓝图待统一项

当前 workspace 未包含 handoff 所列 Gateway 文件：
`docs/ENTERPRISE_GOVERNANCE_BLUEPRINT.md`、`docs/CONTROL_BASELINE.md`、
`experiments/README.md`、`docs/AWS_SAMPLE_CATALOG.md` 的 Gateway 版本。因此本次无法逐条
比对 Gateway 控制 ID、术语和风险等级；Memory 文档中的 Gateway 契约是 Memory owner 的
提案，需 Gateway owner 复核。

| 议题 | Memory 侧立场 | 待 Gateway 确认 |
|---|---|---|
| 最终授权 | Gateway 决定工具可调用；Memory IAM 决定数据 API | Gateway 是否明确不声称数据授权 |
| 防绕过 | 直接 SDK path 必须由 SCP/IAM 收敛 | Gateway target/source 限制覆盖哪些调用面 |
| 身份传播 | 稳定 subject 映射为 actor，禁止模型指定 | subject/claims/header 的标准契约 |
| Policy 范围 | Policy 拦截 Gateway 调用，不自动拦截 Memory SDK | Gateway 文档是否清楚描述该边界 |
| Guardrails | Gateway 与 Memory I/O 检查不可漂移 | 规则 owner、版本和失败模式 |
| 会话 | Gateway MCP/HTTP session 与 Memory session 不等价 | ID 关联、结束和吊销事件 |
| Trace | Gateway request ID 必须关联 Memory event/record | OTEL 属性名和跨账户查询 |
| 删除 | Gateway target 删除不自动删除 Memory 数据 | 资源/用户退役事件如何传播 |
| 配额/成本 | Gateway 限流和 Memory 配额分别预算 | 谁执行端到端 admission control |
| 错误模型 | 保留 Memory 原始错误分类 | Gateway 是否会包装/丢失错误码 |

## 5. 建议下一个 Agent 处理

1. **Gateway owner**：用 Gateway 蓝图逐行复核第 4 节，统一术语、控制 ID 和风险等级。
2. **Identity owner**：定义 inbound JWT、workload identity、OBO/3LO 到 actor/session tag
   的标准映射，给出跨账户模式。
3. **Observability owner**：按新蓝图验证 Transaction Search、Memory log delivery、
   service/application spans、CloudTrail 数据面覆盖和统一脱敏字段。
4. **Policy owner**：明确 Policy/Guardrails 哪些路径可拦截，形成直连 Memory 的补偿控制。
5. **Runtime/Harness owner**：证明用户身份不在共享执行角色中丢失，并统一 session 生命周期。
6. **Landing zone 汇总 Agent**：合并所有服务控制、去重冲突、生成全栈责任矩阵和端到端实验。

## 6. 未执行事项

- 未部署、修改或删除任何 AWS 资源；
- 未运行 E00–E07，实验状态均为“设计完成、待授权执行”；
- 未访问真实客户数据、token、secret 或账户 ARN；
- 未宣称 CloudTrail 数据面、跨账户、PrivateLink 或 DR 已通过；
- 未启用 Transaction Search、log delivery、ADOT、Firehose 或 S3 Tables，也未采集云端证据；
- 未创建 commit 或 pull request。

下一次执行实验前，从 E00 开始重新核验 Region、Quotas、Pricing、SDK 和 sample commit。
