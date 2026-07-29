> 本文档为主版本。English: [SECURITY.en.md](SECURITY.en.md)。

# 安全说明

## 数据处理

- 共享记忆（Shared Memory）只接收经过批准且脱敏的表述。
- 任务令牌（task token）在 DynamoDB 中加密存储，绝不出现在通知或日志中。
- Step Functions 的执行数据日志（execution data logging）保持关闭。
- AgentCore 的事件与记录元数据只包含分类标识和关联标识。原始证据、个人数据和密钥
  都不进入元数据。
- 运行时必须从经过认证的 claims 中推导 actor ID 和项目 ID。
- 个人 actor 请使用不可变的 Cognito `sub` 值。邮箱和用户名是可变的展示属性，不是
  持久可靠的安全标识符。
- 共享记忆的发布者策略和运行时读取策略都收敛到精确的项目命名空间（namespace）。
  多用户的服务端运行时仍然需要在应用层对个人 actor 做授权；当需要由 IAM 强制的
  按用户隔离时，请使用 Cognito 联邦临时凭证。

## 依赖审计

`npm audit --omit=dev` 目前会报出 `brace-expansion@5.0.7` 中的
`GHSA-mh99-v99m-4gvg`，该版本被打包在 `aws-cdk-lib@2.262.1` 内部。npm 无法覆盖或
自动替换这份被内联打包的副本。

该依赖仅在合成（synth）基础设施时使用，不会被打进 Lambda 产物。但 CDK 的 context 和
项目配置仍必须视为可信输入。请跟踪 `aws-cdk-lib` 的下一个补丁版本，待其内联依赖更新
后删除本条说明。不要使用 `npm audit fix --force`。

为保证 CDK 工具链的可复现性，请使用 Node.js 22 LTS。本蓝图在 Node.js 24.8.0 上也能
成功合成，尽管 CDK CLI 的某个校验依赖声明的 Node 引擎范围更窄，仅限 Node 22。
