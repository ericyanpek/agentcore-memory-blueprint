# AgentCore Memory AWS 官方样例目录

> 主版本：中文。English: [AWS_SAMPLE_CATALOG.en.md](AWS_SAMPLE_CATALOG.en.md)。
> 复核日期：2026-08-04。样例仅用于能力验证和实验设计，不作为生产合规证据。

## 1. 固定快照

| 项目 | 值 |
|---|---|
| 仓库 | `awslabs/agentcore-samples` |
| 固定提交 | `fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645` |
| 提交日期 | 2026-08-03 |
| Memory 根目录 | `01-features/04-manage-context-of-your-agent/memory` |
| 上次本仓库快照 | `ff11ccbb89d391a7c2478160a1b66c63f0b63e59`（2026-07-22） |
| 核验方式 | 浅克隆当前提交，获取旧提交 tree，逐路径存在性与 name-status 比较 |

固定入口：
[Memory samples at fa72a1e](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory)。

从旧快照到当前快照，Memory 目录有 9 个已修改文件和 1 个新增文件。变化集中在 quickstart、
内置/override/自管策略、record metadata、extraction 管理及 episodic 示例；新增
`02-long-term-memory/requirements.txt`，将 metadata/extraction 所需 SDK 版本显式化。

## 2. 样例能力映射

| 样例路径 | 能力 | 企业问题 | 采用方式 | 生产化差距 |
|---|---|---|---|---|
| [`00-getting-started`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/00-getting-started) | CLI/boto3/SDK 基础流程 | 如何建立最小资源与工具链基线 | E00/E01 | 不提供账户治理、审批和证据包 |
| [`events-and-sessions`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/01-short-term-memory/01-events-and-sessions) | STM event/session | 原始交互如何持久 | E01 | 身份映射由调用方正确提供 |
| [`actor-session-isolation`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/01-short-term-memory/03-actor-session-isolation) | actor/session 分离 | 如何避免上下文串线 | E02/E03 | 组织键不等于最终用户归属证明 |
| [`built-in-strategies`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/02-long-term-memory/01-built-in-strategies) | semantic/summary/preference/episodic | 何时用哪种提取 | E01 | 模型输出仍需内容与权威治理 |
| [`strategy-overrides`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/02-long-term-memory/02-strategy-overrides) | 自定义 prompt/model | 如何控制提取行为 | E04 | 额外模型成本、测试和版本责任 |
| [`self-managed-strategy`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/02-long-term-memory/03-self-managed-strategy) | 自管提取 | 如何接入确定性/自有管道 | E04 | S3/SNS/Lambda、幂等和运维归客户 |
| [`namespaces`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/02-long-term-memory/04-namespaces) | namespace 组织 | 租户/项目如何分层 | E02/E03 | 必须叠加 IAM，不能只靠命名 |
| [`retrieval`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/02-long-term-memory/05-retrieval) | 语义检索与引用 | 如何保留来源 | E01/E07 | 无权威冲突、陈旧和审批判断 |
| [`record-metadata`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/02-long-term-memory/06-record-metadata) | indexed keys/filter | 如何做预过滤 | E04/E07 | indexed keys 不可删除，需 schema 治理 |
| [`batch-apis`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/02-long-term-memory/07-batch-apis) | record 直接 CRUD | 如何逐字发布已审核知识 | E07 | 部分失败、发布权限和审计需自建 |
| [`manage-extraction`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/02-long-term-memory/08-manage-extraction) | SKIP/redrive | 如何避免不当提取并恢复失败 | E04/E05 | 必须先分类错误，不能盲目 redrive |
| [`record-streaming`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/02-long-term-memory/09-record-streaming) | Kinesis 生命周期流 | 审计、分析、复制 | E05/E06 | 至少一次、KMS/IAM、成本和消费者责任 |
| [`runtime-integration`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/03-integrations/01-runtime-integration) | Runtime session manager | 如何接 Agent loop | E02/E07 | 避免 hook 与自写 recorder 双写 |
| [`identity-integration`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/03-integrations/02-identity-integration) | Identity + Memory | 用户身份如何进入记忆路径 | E02 | token 有效不等于 actor 业务授权 |
| [`guardrails-integration`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/03-integrations/03-guardrails-integration) | 输出 Guardrail | 如何叠加内容控制 | E04 | 样例明确只过滤输出，不保护存储/召回 |
| [`observability`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/04-observability) | 指标、告警、日志 | 如何发现提取/流故障 | E05 | 需企业阈值、集中审计和 runbook |
| [`iam-scoped-access`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/05-security/01-iam-scoped-access) | 条件键最小权限 | 如何做平台侧隔离 | E02 | 共享 principal 仍需应用归属校验 |
| [`kms-encryption`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/05-security/03-kms-encryption) | CMK | 如何控制数据密钥 | E04 | key disable 是全资源中断，不是删除 |
| [`production-patterns`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/06-production-patterns) | 错误、成本、检查表 | 如何从 demo 走向运营 | E05/E06 | 数值仍需对最新官方文档复核 |
| [`multi-region-replication`](https://github.com/awslabs/agentcore-samples/tree/fa72a1ed57c0c6c8dcb943b08e66813f8d8e4645/01-features/04-manage-context-of-your-agent/memory/06-production-patterns/00-multi-region-replication) | STM 双写 + LTM 流复制 | 如何构建 warm standby | E06 | 不复制删除、单账户、客户自担 RPO/RTO |

## 3. 已观察到的样例漂移

| 编号 | 观察 | 权威结论 | 处理 |
|---|---|---|---|
| DRIFT-001 | production checklist 写 `eventExpiryDuration` 为 3–365 天 | 当前 Quotas 页写 7–365 天 | 蓝图使用 7–365；E00 每次复核 |
| DRIFT-002 | CDK README 仍有“不能直接创建长期记录”的描述 | Data Plane API 与 batch sample 支持 `BatchCreateMemoryRecords` | 以 API Reference 为准 |
| DRIFT-003 | sample metadata 页仅列 `EQUALS_TO/EXISTS/NOT_EXISTS` | 当前服务模型与 API 支持更多过滤操作符 | 逐 SDK 版本做契约测试，不从 sample 推导全集 |
| DRIFT-004 | sample Guardrails 集成只过滤模型输出 | sample 自己也声明输入仍可存入 Memory | 存储前和注入前分别检查 |
| DRIFT-005 | multi-region sample 跳过 `MemoryRecordDeleted`，且仅单账户 | 它是客户自建 active-passive 示例，不是原生复制 | 不宣称强一致或完整删除传播 |
| DRIFT-006 | 旧快照到新快照修改策略、metadata 和 extraction 示例 | samples 会持续演进 | 所有引用固定 commit，不链接 `main` |

DRIFT-001 的权威来源：
[AgentCore quotas](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html)。
DRIFT-002 的权威来源：
[BatchCreateMemoryRecords API](https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/API_BatchCreateMemoryRecords.html)。

## 4. 官方文档快照

| 来源 | 本蓝图使用内容 | 优先级 |
|---|---|---:|
| [Developer Guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory.html) | 概念、组织、策略、网络、安全 | 1 |
| [Release Notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html) | 新能力和时间线 | 1 |
| [Data Plane API](https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/Welcome.html) | 请求/响应、字段和错误 | 2 |
| [Service Authorization Reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_bedrock-agentcore.html) | action、resource、condition key | 2 |
| [Region](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-regions.html) | Memory 可用 Region | 2 |
| [Quotas](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html) | 资源、TPS、token 限制 | 2 |
| [Pricing](https://aws.amazon.com/bedrock/agentcore/pricing/) | 事件、记录、检索价格 | 2 |
| [PrivateLink](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/vpc-interface-endpoints.html) | control/data endpoint 和 OAuth 限制 | 2 |
| [CloudFormation](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-bedrockagentcore-memory.html) | IaC 资源属性 | 2 |
| 固定 AWS samples | 可执行示例和生产提示 | 3 |
| 本仓库实验 | 具体架构的实测结果 | 4 |
| 本蓝图建议 | 企业治理设计 | 5 |

发生冲突时按表中优先级处理，并在本目录登记 drift，不能静默选择更方便的说法。

## 5. 不可从样例推导的结论

- sample 运行成功不证明合规、数据驻留或最小权限；
- actor/namespace 正确传参不证明调用者有权使用该值；
- Guardrails 通过不证明业务授权、事实真实或租户隔离；
- PrivateLink 不证明 API 调用已授权；
- 多 Region 示例不提供服务 SLA、强一致或完整删除复制；
- production checklist 的数字不替代当日 Region、Quotas 和 Pricing 页面；
- Memory Browser 是本地诊断工具，不是企业多用户治理控制台。

实验路线见[../experiments/README.md](../experiments/README.md)，控制要求见
[CONTROL_BASELINE.md](CONTROL_BASELINE.md)。
