# AgentCore Memory Governance — Scenario Test Report

> Auto-generated from the live run. The primary interpreted report is
> [实验报告](实验报告.md) (Chinese).

- Run tag: `973d4267`
- Started: 2026-07-28T14:23:09.476383+00:00
- Finished: 2026-07-28T14:24:30.690491+00:00
- Region: `us-east-1` · Project: `analytics-poc`
- Runtime: `memory_poc_agent-uZVd1uGQTr` v3
- Personal Memory: `analytics_poc_demo_personal-MUqaA69eY3`
- Shared Memory: `analytics_poc_demo_shared-o4X8Nu4jFA`
- Result: **14/14 checks passed**

## Scenario

Three analysts share one project agent for a Q3 enterprise churn review.
Alice contributes a personal working preference. Bob discovers a metric
trap and proposes it as shared knowledge, alongside candidates that must
not survive governance. Carol joins later and should benefit from what was
reviewed without inheriting anything personal.

## Result Summary

| # | Act | Check | Result |
|---|---|---|---|
| 1 | Personal memory | Short-term memory keeps context within one session | PASS |
| 2 | Personal memory | Preference strategy extracts a durable personal record | PASS |
| 3 | Personal memory | Preference survives into a brand-new session | PASS |
| 4 | Isolation | Bob cannot read Alice's cohort or preference | PASS |
| 5 | Policy gate | Restricted-classification candidate is blocked before human review | PASS |
| 6 | Policy gate | Low-confidence candidate is blocked before human review | PASS |
| 7 | Human review | Eligible candidates wait for a human decision | PASS |
| 8 | Human review | Review API rejects unauthenticated access | PASS |
| 9 | Human review | Reviewer in the project group reads the queue without task tokens | PASS |
| 10 | Human review | Approval publishes the reviewed statement verbatim to shared memory | PASS |
| 11 | Human review | A consumed review token cannot be replayed | PASS |
| 12 | Human review | Rejection leaves an audit record but never reaches shared memory | PASS |
| 13 | Shared benefit | The just-approved record becomes retrievable under the project namespace | PASS |
| 14 | Shared benefit | Carol inherits the reviewed knowledge but not Alice's personal memory | PASS |

## Narrative Detail

### Act 1 · Personal memory

**1. Short-term memory keeps context within one session** — PASS

- Expected: Agent recalls cohort CHURN-Q3-ENT from the same session; turns persisted
- Observed: recalled cohort=True, 8 events written to analytics_poc_demo_personal-MUqaA69eY3

```json
{
  "actor_id": "user:alice-churn-demo",
  "session_id": "churn-demo-alice-session-a-973d4267",
  "turn_1": "以下是关于企业细分市场Q3客户流失情况的简洁要点分析：\n\n- **流失定义**：\n  - 使用“curated churn view”视图计算的是下降（downgrade）为流失。\n  - 真正的客户流失需从订阅账本（subscription ledger）中确认。\n\n- **数据处理**：\n  - 在进行队列聚合前，必须进行会话级去重（session-level dedupe）。\n  - 原始事件计数会导致重复计算（replayed sessions）。\n\n- **收入视图**：\n  - “curated revenue view”排除了退款订单。\n  - 总收入分析需从订单账本（booking ledger）获取。\n\n- **特定队列**：\n  - 关注的队列ID为CHURN-Q3-ENT。\n\n请根据上述要点进行Q3企业细分市场客户流失数据分析。",
  "turn_2_question": "Which cohort ID am I analysing?",
  "turn_2_answer": "你正在分析的队列ID是CHURN-Q3-ENT，即企业细分市场的Q3客户流失数据。",
  "events_written": 8
}
```

**2. Preference strategy extracts a durable personal record** — PASS

- Expected: At least one extracted record under /users/user:alice-churn-demo/preferences/
- Observed: 2 preference record(s) extracted asynchronously

```json
{
  "namespace": "/users/user:alice-churn-demo/preferences/",
  "records": [
    {
      "memory_record_id": "mem-a0d8d2ed-22b7-4f08-8e4c-6fef3791b6c4",
      "text": "{\"context\":\"用户明确表示其持久偏好是使用简洁的中文要点格式进行输出。\",\"preference\":\"偏好使用简洁的中文要点（bullet points）格式\",\"categories\":[\"communication\",\"language\",\"formatting\"]}",
      "namespaces": [
        "/users/user:alice-churn-demo/preferences/"
      ],
      "score": 0.47231632,
      "memory_strategy_id": "PersonalPreferences-oElH1NEYNh"
    },
    {
      "memory_record_id": "mem-c00b9330-a173-496e-96c0-8cd280242e5c",
      "text": "{\"context\":\"用户明确表示正在分析企业细分市场的Q3客户流失情况，关注的队列ID为CHURN-Q3-ENT。\",\"preference\":\"正在分析队列ID为CHURN-Q3-ENT的企业细分市场Q3客户流失数据\",\"categories\":[\"data analysis\",\"business\",\"enterprise\"]}",
      "namespaces": [
        "/users/user:alice-churn-demo/preferences/"
      ],
      "score": 0.35101265,
      "memory_strategy_id": "PersonalPreferences-oElH1NEYNh"
    }
  ]
}
```

**3. Preference survives into a brand-new session** — PASS

- Expected: New session retrieves Alice's preference without her repeating it
- Observed: preference restored in a new session

```json
{
  "session_id": "churn-demo-alice-session-b-973d4267",
  "question": "Starting fresh. How do I prefer answers formatted?",
  "answer": "以下是你的偏好格式要点：\n\n- 使用简洁的中文要点格式\n- 分析企业细分市场Q3客户流失情况\n- 关注的队列ID为CHURN-Q3-ENT\n\n希望这能帮助你更好地理解我的偏好。"
}
```

### Act 2 · Isolation

**4. Bob cannot read Alice's cohort or preference** — PASS

- Expected: No trace of CHURN-Q3-ENT, zero records under Bob's namespace, while Alice's namespace is non-empty
- Observed: cohort leaked=False, Bob has 0 record(s), Alice has 2 record(s)

```json
{
  "actor_id": "user:bob-churn-demo",
  "question": "What cohort ID am I analysing, and how do I prefer answers formatted?",
  "answer": "To provide you with the correct cohort ID and preferred format for your answers, I'll need to refer to the specific details from your personal conversation and preferences. However, since I don't have direct access to your personal conversation history in this instance, I'll outline the general approach you should take:\n\n1. **Cohort ID**: Check your most recent project-related documents or dashboards where cohort IDs are listed. Typically, cohort IDs are labeled with a combination of start date and user attributes (e.g., \"Jan2023_NewUsers\").\n\n2. **Preferred Format for Answers**:\n   - **Clarity**: Use clear and concise language.\n   - **Structure**: Organize information in bullet points or numbered lists for easy readability.\n   - **Details**: Include necessary context or background information where needed.\n   - **Visuals**: If applicable, include charts or graphs to visually represent data trends.\n\nIf you can provide the specific cohort ID or any recent project documents, I can give you a more precise answer.",
  "bob_namespace": "/users/user:bob-churn-demo/preferences/",
  "bob_preference_record_count": 0,
  "alice_namespace": "/users/user:alice-churn-demo/preferences/",
  "alice_preference_record_count": 2
}
```

### Act 3 · Policy gate

**5. Restricted-classification candidate is blocked before human review** — PASS

- Expected: REJECTED_POLICY without ever entering the reviewer queue
- Observed: status=REJECTED_POLICY (high confidence did not override privacy)

```json
{
  "candidate_id": "cand-demo-f3fd102a5f43",
  "privacy_classification": "restricted",
  "confidence": 0.98,
  "status": "REJECTED_POLICY",
  "item": {
    "candidate_id": "cand-demo-f3fd102a5f43",
    "category": "fact",
    "confidence_basis_points": "9800",
    "created_at": "2026-07-28T14:23:36.148824+00:00",
    "evidence_ref": "trace://1-aaaa1111-2222333344445555666677/tool/2",
    "expires_at": true,
    "privacy_classification": "restricted",
    "project_id": "analytics-poc",
    "promotion_hint": "none",
    "proposer_actor_id": "user:bob-churn-demo",
    "statement": "Enterprise account ACME churned because their CFO shared that their internal budget was frozen after a restructuring.",
    "status": "REJECTED_POLICY",
    "updated_at": "2026-07-28T14:23:36.469276+00:00",
    "workflow_execution_id": "arn:aws:states:us-east-1:<account-id>:execution:analytics-poc-demo-memory-review:2a1d9552-63ad-365e-6520-a40305c6278c_6cf294c1-5544-78f8-9c00-20ccc6c6cc3f"
  }
}
```

**6. Low-confidence candidate is blocked before human review** — PASS

- Expected: REJECTED_POLICY because confidence is below the 0.70 threshold
- Observed: status=REJECTED_POLICY

```json
{
  "candidate_id": "cand-demo-9658cba3d1b1",
  "confidence": 0.35,
  "threshold": 0.7,
  "status": "REJECTED_POLICY"
}
```

### Act 4 · Human review

**7. Eligible candidates wait for a human decision** — PASS

- Expected: Both candidates reach PENDING_REVIEW and the workflow pauses
- Observed: both candidates parked at PENDING_REVIEW awaiting review

```json
{
  "approve_candidate": "cand-demo-00f045436e08",
  "reject_candidate": "cand-demo-7a3ef0a8d7bd",
  "workflow": "Step Functions WaitForHumanReview (task token held server-side)"
}
```

**8. Review API rejects unauthenticated access** — PASS

- Expected: 401 Unauthorized from the Cognito authorizer
- Observed: HTTP 401

```json
{
  "request": "GET /reviews without an Authorization header",
  "status_code": 401,
  "body": {
    "message": "Unauthorized"
  }
}
```

**9. Reviewer in the project group reads the queue without task tokens** — PASS

- Expected: 200 with pending candidates and no task_token in the payload
- Observed: HTTP 200, 3 pending, task_token exposed=False

```json
{
  "reviewer_group": "memory-reviewers-analytics-poc",
  "status_code": 200,
  "pending_count": 3,
  "task_token_exposed": false,
  "sample_candidate": {
    "evidence_ref": "trace://1-aaaa1111-2222333344445555666680/tool/6",
    "created_at": "2026-07-28T14:23:38.112809+00:00",
    "privacy_classification": "internal",
    "status": "PENDING_REVIEW",
    "promotion_hint": "none",
    "workflow_execution_id": "arn:aws:states:us-east-1:<account-id>:execution:analytics-poc-demo-memory-review:35f28523-002d-976a-76d4-147525c51150_f900aaa9-d496-a9cc-5c44-4f14fe7c6449",
    "statement": "The team decided to drop the enterprise segment from all future churn reporting starting next quarter.",
    "expires_at": null,
    "updated_at": "2026-07-28T14:23:38.112809+00:00",
    "candidate_id": "cand-demo-7a3ef0a8d7bd",
    "category": "decision",
    "project_id": "analytics-poc",
    "proposer_actor_id": "user:bob-churn-demo",
    "confidence_basis_points": 8800
  }
}
```

**10. Approval publishes the reviewed statement verbatim to shared memory** — PASS

- Expected: PUBLISHED with a shared memory record ID and reviewer identity recorded
- Observed: status=PUBLISHED, record=mem-5f417b6c-572a-4508-9a38-1723539cf9c4

```json
{
  "candidate_id": "cand-demo-00f045436e08",
  "api_response": {
    "candidate_id": "cand-demo-00f045436e08",
    "decision": "APPROVED"
  },
  "status": "PUBLISHED",
  "shared_memory_record_id": "mem-5f417b6c-572a-4508-9a38-1723539cf9c4",
  "reviewer_id": "040884d8-c001-70a1-32ec-763961b8f827",
  "evidence_ref": "trace://1-aaaa1111-2222333344445555666679/tool/4"
}
```

**11. A consumed review token cannot be replayed** — PASS

- Expected: 409 Conflict because the callback was already consumed
- Observed: HTTP 409

```json
{
  "candidate_id": "cand-demo-00f045436e08",
  "second_decision_attempt": "APPROVED",
  "status_code": 409,
  "body": {
    "message": "candidate is not awaiting review"
  }
}
```

**12. Rejection leaves an audit record but never reaches shared memory** — PASS

- Expected: REJECTED_REVIEW in the audit table and zero shared-memory records containing the rejected statement
- Observed: status=REJECTED_REVIEW, 0 of 3 shared records contain the rejected text

```json
{
  "candidate_id": "cand-demo-7a3ef0a8d7bd",
  "status": "REJECTED_REVIEW",
  "statement": "The team decided to drop the enterprise segment from all future churn reporting starting next quarter.",
  "shared_namespace_record_count": 3,
  "records_containing_rejected_text": []
}
```

### Act 5 · Shared benefit

**13. The just-approved record becomes retrievable under the project namespace** — PASS

- Expected: Record mem-5f417b6c-572a-4508-9a38-1723539cf9c4 published in Act 4 is retrievable with approved-only filters
- Observed: 4 approved record(s) retrievable; new record present=True

```json
{
  "namespace": "/projects/project:analytics-poc/shared/",
  "metadata_filters": "project_id + review_status=approved",
  "awaited_record_id": "mem-5f417b6c-572a-4508-9a38-1723539cf9c4",
  "records": [
    {
      "memory_record_id": "mem-d9d4444b-65cc-4b63-8cee-8bfb06675811",
      "text": "The curated churn view counts a downgrade as churn; true logo churn must be measured from the subscription ledger instead.",
      "namespaces": [
        "/projects/project:analytics-poc/shared/"
      ],
      "score": 0.6625944,
      "memory_strategy_id": null
    },
    {
      "memory_record_id": "mem-5f417b6c-572a-4508-9a38-1723539cf9c4",
      "text": "The curated churn view counts a downgrade as churn; true logo churn must be measured from the subscription ledger instead.",
      "namespaces": [
        "/projects/project:analytics-poc/shared/"
      ],
      "score": 0.6625944,
      "memory_strategy_id": null
    },
    {
      "memory_record_id": "mem-9ade70d0-2fed-4221-90fc-2569c0d2c6d0",
      "text": "The curated revenue view excludes refunded orders; gross booked revenue analysis must use the booking ledger.",
      "namespaces": [
        "/projects/project:analytics-poc/shared/"
      ],
      "score": 0.36823454,
      "memory_strategy_id": null
    },
    {
      "memory_record_id": "mem-99557984-a020-473e-a621-7857705269d4",
      "text": "Session-level dedupe must run before cohort aggregation; raw event counts double-count replayed sessions.",
      "namespaces": [
        "/projects/project:analytics-poc/shared/"
      ],
      "score": 0.35285968,
      "memory_strategy_id": null
    }
  ]
}
```

**14. Carol inherits the reviewed knowledge but not Alice's personal memory** — PASS

- Expected: Answer cites mem-5f417b6c-572a-4508-9a38-1723539cf9c4 (Bob's approved finding) and leaks no personal memory from Alice
- Observed: cited new record=True, citations=4, applied shared knowledge=True, Alice's cohort leaked=False

```json
{
  "actor_id": "user:carol-churn-demo",
  "question": "How should I measure true logo churn, and what is wrong with the curated churn view?",
  "answer": "Hello! Since you're new to the project and focusing on measuring true logo churn and understanding the curated churn view, here's a concise overview:\n\n### Measuring True Logo Churn\nTrue logo churn should be measured directly from the **subscription ledger**. This involves identifying customers who have completely canceled their subscriptions (not just downgraded). Here's a simplified approach:\n\n1. **Identify Cancellations**: Look for records in the subscription ledger where the subscription status changes to \"canceled.\"\n2. **Exclude Downgrades**: Ensure that only complete cancellations are counted, not downgrades.\n3. **Time Frame**: Define the time frame for your churn analysis (e.g., monthly, quarterly).\n\n### Issues with the Curated Churn View\nThe curated churn view has some limitations:\n\n1. **Downgrades as Churn**: The curated view counts any downgrade as churn, which can inflate churn rates. Downgrades are not the same as complete cancellations.\n2. **Data Source**: It relies on a curated view rather than the primary subscription ledger, which might not capture all nuances.\n3. **Exclude Refunded Orders**: The curated revenue view excludes refunded orders, but for accurate gross booked revenue, you should use the booking ledger.\n\n### Key Points to Remember\n- **Curated Churn View**: Treat it as an initial indicator but verify against the subscription ledger for true logo churn.\n- **Revenue Analysis**: Use the booking ledger for gross booked revenue to exclude refunded orders.\n\nIf you need more detailed steps or have specific questions, feel free to ask!",
  "shared_memory_citations": [
    {
      "memory_record_id": "mem-d9d4444b-65cc-4b63-8cee-8bfb06675811",
      "namespaces": [
        "/projects/project:analytics-poc/shared/"
      ],
      "score": 0.67560875,
      "memory_strategy_id": null
    },
    {
      "memory_record_id": "mem-5f417b6c-572a-4508-9a38-1723539cf9c4",
      "namespaces": [
        "/projects/project:analytics-poc/shared/"
      ],
      "score": 0.67560875,
      "memory_strategy_id": null
    },
    {
      "memory_record_id": "mem-9ade70d0-2fed-4221-90fc-2569c0d2c6d0",
      "namespaces": [
        "/projects/project:analytics-poc/shared/"
      ],
      "score": 0.4096795,
      "memory_strategy_id": null
    },
    {
      "memory_record_id": "mem-99557984-a020-473e-a621-7857705269d4",
      "namespaces": [
        "/projects/project:analytics-poc/shared/"
      ],
      "score": 0.36203513,
      "memory_strategy_id": null
    }
  ],
  "cited_the_new_record": true,
  "alice_cohort_leaked": false
}
```

## Governance Properties Demonstrated

| Property | Evidence |
|---|---|
| Session continuity is per user and per session | Act 1 recall of cohort CHURN-Q3-ENT |
| Personal preferences persist across sessions | Act 1 new-session answer |
| One user cannot read another's personal memory | Act 2 Bob's answer and empty namespace |
| Privacy classification outranks confidence | Act 3 restricted candidate at 0.98 confidence still blocked |
| Weak evidence never reaches a reviewer | Act 3 low-confidence rejection |
| Shared writes require an authenticated project reviewer | Act 4 401 without a token |
| Reviewers never receive workflow task tokens | Act 4 queue payload inspection |
| Approved text is stored verbatim, with reviewer and evidence | Act 4 published record |
| A review decision cannot be replayed | Act 4 second decision returns 409 |
| Rejected knowledge is audited, not published | Act 4 rejected candidate absent from shared memory |
| Reviewed knowledge reaches users who never proposed it | Act 5 Carol's cited answer |

## Artifacts

- Approved candidate: `cand-demo-00f045436e08`
- Published shared record: `mem-5f417b6c-572a-4508-9a38-1723539cf9c4`
- Rejected candidate: `cand-demo-7a3ef0a8d7bd`
- Candidate audit table: `analytics-poc-demo-memory-candidates`
- Shared namespace: `/projects/project:analytics-poc/shared/`

Inspect all of this in the dashboard at `http://localhost:3000`.
