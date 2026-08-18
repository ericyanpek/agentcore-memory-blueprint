# AWS 官方依据与实现对照

> 相关：[架构设计](架构设计.md) · [设计取舍依据](设计取舍依据.md) · [实验报告](实验报告.md) ·
> [桌面客户端集成设计](桌面客户端集成设计.md) · [下一步演进](下一步演进.md)

本文把本蓝图的每条设计主张对齐到 AWS 官方文档，给出逐字原文、实现位置与实测证据。

## 关于"背书"这个词

Well-Architected Lens 不是先验规范。它的形成路径是：解决方案架构师在客户现场反复遇到
同类问题，沉淀出模式，模式被验证后才编纂进 Lens。**Lens 是实践的后验编纂，不是实践的
前置许可。**

所以本文不是"AWS 规定了，本项目遵守了"。准确的关系是三层：

| 层次 | 内容 |
|---|---|
| **AWS 已编纂** | 人工审核、命名空间隔离、IAM 条件键、确定性风险分类 —— Lens 已写明，本项目是可运行的参考实现 |
| **AWS 已建原语但未接入 Memory** | 记忆治理"可编码可审计"是 AGENTSEC01 的 Level 5 目标。AgentCore **在 Registry 资源上已有完整审批状态机**（`SubmitRegistryRecordForApproval` / `UpdateRegistryRecordStatus`），但 Memory 资源没有接入它。这段是客户自建 |
| **AWS 尚未覆盖** | 共享记忆的准入治理、检索优先级全序、证据版本固定 —— 无官方来源，属本项目的工程判断 |

第二层和第三层才是这个项目的实际贡献。第一层的价值在于：它证明这些选择不是个人偏好，
而是与 AWS 自己的框架同向。

---

## 一、人工审核是共享写入的唯一入口

### AWS 官方依据

**《AGENTSEC04-BP02 Human-in-the-loop for critical decisions》**
（AWS Well-Architected Agentic AI Lens）
https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentsec04-bp02.html

未建立此实践的风险等级：**High**。

四段逐字原文，与本实现逐条对应：

> "For agents embedded in step-function-driven workloads, AWS Step Functions
> **.waitForTaskToken callback pattern introduces an approval step**."

> "**Reviewers don't typically call Step Functions APIs directly. The approval app holds
> the credentials**, and the reviewer interacts with the app."

> "You **log human approval decisions with timestamps and reviewer identities**, creating
> an auditable record of human oversight for compliance purposes."

> "**Store the full decision context in durable storage such as Amazon S3** before sending
> the approval notification... Make the context available through **the same authenticated
> interface** the reviewer uses to approve or deny."

**《Discover service integration patterns in Step Functions》**
https://docs.aws.amazon.com/step-functions/latest/dg/connect-to-resource.html

> "Callback tasks provide a way to pause a workflow until a task token is returned.
> **A task might need to wait for a human approval**."

同一页的集成表格显示 **Bedrock AgentCore 的 `.waitForTaskToken` 为 Not supported** ——
这解释了为什么审批层必须自建，而不是平台提供。

### 本实现

| 要求 | 位置 |
|---|---|
| `waitForTaskToken` 审批步骤 | `infra/lib/memory-governance-stack.ts:470`（`IntegrationPattern.WAIT_FOR_TASK_TOKEN`） |
| task token 由服务端保管 | `src/handlers/request_review.py:21` 写入 DynamoDB；`src/handlers/reviewer_api.py:66,87` 在返回前 `pop` 掉 |
| 记录审核员身份与时间 | `src/handlers/reviewer_api.py` 的 `_decide()` 写入 `reviewer_id` 与 `decided_at` |
| 审核界面经身份认证 | Cognito 保护的 Review API，每次请求重新校验 reviewer 组 |

### 实测证据

`build/bridge-validation.json`、`build/scenario-results.json`：

```
[PASS] Reviewer in the project group reads the queue without task tokens
       HTTP 200, 3 pending, task_token exposed=False
[PASS] Review API rejects unauthenticated access          → HTTP 401
[PASS] A consumed review token cannot be replayed         → HTTP 409
[PASS] Non-reviewer is refused the review queue
       ok=False detail=You are not in the project reviewer group, so you cannot read the review queue.
```

拒绝是明示的，而非静默过滤 —— 非审核员被告知缺少组成员身份，不会收到一个空队列。

`task_token exposed=False` 正是 AWS 那句"审核员不直接调 Step Functions API"的可验证形式。

---

## 二、政策闸门用确定性规则，不用 LLM

### AWS 官方依据

同一份 AGENTSEC04-BP02，这一段是本项目当初没有明确论证、但 AWS 讲得比我更透的：

> "**Risk classification itself can't rely on an LLM exposed to the same untrusted content
> as the request being evaluated**, because adversarial content could influence the
> classifier into marking the request as low-risk. Use **deterministic logic (policy
> engines, rule-based classifiers) as the authoritative signal**, with LLM-assisted
> classification as an optional input that a deterministic layer re-checks."

**《AGENTREL02-BP05 Establish tiered human oversight and approval workflows》**
https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentrel02-bp05.html

> "You have a **first-pass automated review layer that filters policy-violating actions
> before human reviewers see them**."

### 本实现

`src/blueprint/domain.py:101-105` —— 纯布尔判断，无模型参与：

```python
@property
def eligible_for_review(self) -> bool:
    return (
        self.privacy_classification != "restricted"
        and self.confidence >= 0.70
    )
```

不合格候选在 `domain.py:120` 直接落为 `REJECTED_POLICY`，从不进入审核队列。

### 实测证据

```
[PASS] Restricted-classification candidate is blocked before human review
       status=REJECTED_POLICY（置信度 0.98 仍被拦 —— 隐私分级优先于置信度）
[PASS] Low-confidence candidate is blocked before human review
       status=REJECTED_POLICY（阈值 0.70）
```

---

## 三、按 actorId 与 namespace 做隔离，由 IAM 强制

### AWS 官方依据

**《Actions, resources, and condition keys for Amazon Bedrock AgentCore》**
（Service Authorization Reference）
https://docs.aws.amazon.com/service-authorization/latest/reference/list_bedrock-agentcore.html

在该页确认存在的条件键：**`bedrock-agentcore:actorId`**（用于 `CreateEvent`）、
**`bedrock-agentcore:namespace`**（用于 `BatchCreateMemoryRecords`、
`BatchUpdateMemoryRecords`）、**`bedrock-agentcore:sessionId`**（用于 `CreateEvent`）。

本项目依赖的正是前两个。`strategyId` 条件键此前记为在该官方页面上"未能确认"，
**2026-08-18 复核时已确认存在**（`bedrock-agentcore:strategyId`，Filters access by Memory
Strategy Id），该保留意见撤回。本项目目前未使用它。

**《Memory organization in AgentCore Memory》**
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-organization.html

> "You can create IAM policies to **restrict memory access by the scopes you define, such
> as actor, session, and namespace**. Use the scopes as context keys in your IAM policies."

该页的策略示例还使用了 **`bedrock-agentcore:namespacePath`** 做层级前缀匹配
（`StringLike` 配 `summaries/agent1/*`），与精确匹配的 `namespace` 并列。本项目当前只用
`namespace`；若将来需要按命名空间子树授权，`namespacePath` 是官方给出的方式。

同页另一条与本项目双资源设计相关：命名空间使 "all long-term memories are scoped to their
specific namespace, keeping them organized and **preventing any conflicts with other users
or sessions**"，并提醒结尾斜杠可 "prevent prefix collisions in multi-tenant applications"。

**《Capability 5. Providing secure access, usage, and implementation of generative AI
agents》**（AWS Prescriptive Guidance，生成式 AI 安全参考架构）
https://docs.aws.amazon.com/prescriptive-guidance/latest/security-reference-architecture-generative-ai/gen-auto-agents.html

> "**Secure agent memory through the Amazon Bedrock AgentCore Memory namespace structure
> for logical data isolation.**"

> "**Prevent memory poisoning by ensuring that users can't modify their session ID or
> actor ID.** Don't include ActorID or SessionID values in system prompts where users
> could manipulate them."

### 本实现

| 要求 | 位置 |
|---|---|
| 桌面端凭证按 `actorId` 限定 | `poc/validate_identity_pool.py:122`，条件值为 `user:${aws:PrincipalTag/userId}` |
| Runtime 检索限定于用户命名空间 | `infra/lib/memory-governance-stack.ts:397` |
| 共享记忆限定单一项目命名空间 | `infra/lib/memory-governance-stack.ts:405`、`poc/validate_identity_pool.py` |
| 客户端无法声明 actor | `bridge/server.py` —— 没有任何工具接受 `actor_id` 参数，身份只从已验签 token 的 `sub` 派生 |

### 实测证据

`build/identity-pool-validation.json`（8/8）—— 同一个 IAM role，权限完全镜像反转：

```
[PASS] Alice writes her own short-term memory              → ALLOWED
[PASS] Alice writes into Bob's actor (impersonation)       → AccessDeniedException
[PASS] Alice reads Bob's events                            → AccessDeniedException
[PASS] Alice retrieves Bob's preference namespace          → AccessDeniedException
[PASS] Alice writes shared memory directly, bypassing review → AccessDeniedException
```

镜像对照：换 Bob 登录，能读 Bob、被拒读 Alice。两人 caller ARN 相同
（`assumed-role/agentcore-memory-desktop-client-role/CognitoIdentityCredentials`），
证明差异来自 session tag 而非策略写死。

**这一条是文档与实测互补的范例**：官方文档说条件键存在，实测证明它真的拦。任一单独都不够。

---

## 四、记忆不是权威事实，不得覆盖当前数据

### AWS 官方依据

**《Secure agent memory and state》（AGENTSEC01）**
https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentsec01.html

> "**Every write path into memory**, including user inputs, tool outputs, inter-agent
> messages, and consolidation, **passes through a layered validation pipeline before data
> reaches the store**."

"常见问题"第一条，直接支持双资源而非单资源加命名空间约定：

> "**Shared namespaces treated as the default rather than an explicit design decision**,
> so one affected session can read or overwrite context that belongs to a different user
> or tenant."

**《Encrypt your Amazon Bedrock AgentCore Memory》**
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/storage-encryption.html

AWS 官方文档自己定义了这个威胁：

> "**Memory poisoning happens when false or harmful information is saved in AgentCore
> Memory.** Later, your AI agent may use this wrong information in future conversations,
> which can lead to incorrect or unsafe responses."

### 部分支持而非完全支持

检索优先级的**六级全序**（实时数据 > Skills > 权威文档 > 已审团队记忆 > 个人偏好 >
模型推断）**没有 AWS 来源**。AWS 讲"记忆是候选上下文而非权威事实"这个方向，但没有列出
完整序列。这是本项目的工程判断，详见[设计取舍依据](设计取舍依据.md)第二节。

---

## 五、逐字发布：批准的文本原样入库

### AWS 官方依据

**《Self-managed strategy》**
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-self-managed-strategies.html

> "A self-managed strategy in combination with the batch operations
> (**BatchCreateMemoryRecords**, BatchUpdateMemoryRecords, BatchDeleteMemoryRecords), let
> you **directly ingest these extracted records** into Amazon Bedrock AgentCore memory for
> search capabilities."

即"绕过平台抽取、直接写入长期记录"是 AWS 文档化的受支持路径，不是变通用法。

同页把自管理策略描述为五步流程：**配置触发 → 接收通知与载荷 → 抽取 → 整合（去重与消解
冲突）→ 用批量 API 存回**。本项目的治理链路与之同形，差别在于第三、四步之间插入了政策闸门
与人工审核，并且第五步存入的是**审核员批准的原文**而非模型抽取结果。AWS 把"自定义抽取与
整合算法"列为该策略的用途之一：

> "Implement custom extraction and consolidation algorithms"

本项目属于把这一自由度用在治理而非抽取质量上。

另外该页也确认了本文末尾要更正的那点：涉及记忆记录状态的操作只有
`BatchCreateMemoryRecords` / `BatchUpdateMemoryRecords` / `BatchDeleteMemoryRecords`，
**未出现任何 `INVALID` 状态**。

**《Locking objects with Object Lock》**（S3）
https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html

> "S3 Object Lock uses a **write-once-read-many (WORM)** model to store objects... In
> compliance mode, a protected object version **can't be overwritten or deleted by any
> user, including the root user** in your AWS account."

### 本实现

`src/blueprint/memory.py:66-70` —— `requestIdentifier` 用 `candidate_id` 做幂等键，
`content.text` 即审核员批准的字符串本身。

### 需要说明的边界

"批准文本必须逐字保存"这个**要求**没有 AWS 来源。AWS 提供了实现它的 API，但没有说
应该这样做。这条主张的外部支撑来自 arXiv:2603.02473（零 LLM 调用的原始分块存储打平或
优于有损替代），见[设计取舍依据](设计取舍依据.md)第一节。

---

## AWS 未覆盖的部分

如实列出，以免对外过度声称：

| 设计要素 | 状态 |
|---|---|
| **记忆写入的原生审核闸门** | AgentCore Memory 不提供 —— 但需精确表述：同一服务的 **Registry 资源有**（见[设计取舍依据](设计取舍依据.md)第三节）。所以准确的说法不是「AWS 没有审批原语」，而是「AWS 已经建好了，只是 Memory 没接」。本项目的 EventBridge → Step Functions 链路是客户自建架构 |
| **"团队知识"作为治理类别** | AWS 文档讲共享命名空间，但不讲"什么内容有资格进入共享命名空间"的审批策划 |
| **检索优先级全序** | 无 AWS 来源 |
| **`evidence_ref` 固定 S3 versionId 作为记忆证据** | S3 Object Lock 的 WORM 语义有完整文档，但 AWS 没有把 versionId 固定表述为 AI 记忆的溯源机制 |
| **Identity Pool session tag + 单一共享角色限定 actorId** | 两个组件各有官方文档，但 AWS 未把二者组合推荐给 AgentCore Memory。这是本项目的原创组合 |

## 需要更正的一处先前说法

"AgentCore 把过时记忆标记为 `INVALID` 而非删除"这一说法的出处是 **AWS 机器学习博客**，
但**开发者指南与 API 文档中查不到该状态** —— 记忆记录没有状态字段，批量操作只有增/改/删。
这是 AWS 官方来源之间的不一致，而非纯粹的引用错误。

**处理方式：按 API 文档行事，不依赖该行为。** 本蓝图的取代机制用自有的离散状态标志实现
（见[下一步演进](下一步演进.md)第 4 项），不假设平台侧存在 `INVALID`。对外引用时应说明这一分歧，而不是单引博客。

## 不可作为 AWS 官方来源引用

repost.aws 上的 "Secure Your AI Agents on AWS" 系列（Part 1–3）内容相关且质量不错，
但页面明确声明：

> "This is a personal post. The views are my own and do not represent AWS."

作者身份是 AWS Technical Account Manager，属个人发布，**不能作为 AWS 官方立场引用**。

## 依据一览

| AWS 来源 | 支撑的主张 | 强度 |
|---|---|---|
| [AGENTSEC04-BP02](https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentsec04-bp02.html) | 人工审核、token 不外泄、审核员身份、S3 决策上下文、确定性风险分类 | 强 |
| [Service Authorization Reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_bedrock-agentcore.html) | `actorId` / `namespace` 条件键存在 | 强 |
| [AGENTSEC01](https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentsec01.html) | 写入前校验、共享命名空间不应为默认、成熟度模型 | 强 |
| [GenAI 安全参考架构](https://docs.aws.amazon.com/prescriptive-guidance/latest/security-reference-architecture-generative-ai/gen-auto-agents.html) | 命名空间隔离、禁止用户篡改 actorId、KMS 加密 | 强 |
| [Step Functions 集成模式](https://docs.aws.amazon.com/step-functions/latest/dg/connect-to-resource.html) | `waitForTaskToken` 即人工审批机制 | 强 |
| [Memory organization](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-organization.html) | 用 scope 作 IAM context key | 强 |
| [AGENTREL02-BP05](https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentrel02-bp05.html) | 人工审核前的自动化首轮过滤 | 强 |
| [Self-managed strategy](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-self-managed-strategies.html) | `BatchCreateMemoryRecords` 直接写入 | 强 |
| [storage-encryption](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/storage-encryption.html) | AWS 官方对"记忆投毒"的定义 | 强 |
| [S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html) | WORM 与版本不可变 | 强 |
| [Generative AI Lens](https://docs.aws.amazon.com/wellarchitected/latest/generative-ai-lens/generative-ai-lens.html) | "automated checks, human review... governance policies" | 部分 |
