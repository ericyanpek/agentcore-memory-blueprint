---
name: validate-revenue-metric
description: 依据受治理的指标定义与退款处理规则，校验项目的营收分析。
version: 1
---

> 本文档为 [英文原版](SKILL.md) 的中文翻译。如有出入，以英文版为准。

# 校验营收指标

当项目成员提出营收（revenue）、订单额（bookings）、净营收（net revenue）或退款相关的
分析请求时，使用本 Skill。

## 操作流程

1. 从托管的 Knowledge Base 中检索当前的营收指标定义。
2. 使用已批准的目录工具查看数据集或视图的元数据。
3. 判定所请求的指标是净营收还是总签约营收（gross booked revenue）。
4. 对于净营收，使用经过治理的营收视图（curated revenue view）。
5. 对于总签约营收，使用订单台账（booking ledger），并显式处理退款。
6. 报告数据来源、生效日期、过滤条件以及行数校验结果。
7. 如果 Knowledge Base 中的定义与数据集 schema 存在冲突，立即停止并请求澄清。绝不
   仅凭共享记忆来裁决冲突。

## 证据

本流程由经过评估的项目记忆提升而来。后续任何变更都必须经过 Git 评审，并针对有代表性
的数据集通过校验测试。
