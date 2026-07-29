# SA Demo Runbook

> Translation. The primary document is [演示手册.md](演示手册.md) (Chinese).

## Story

Five analysts use one project agent for a customer-churn project.

- Alice prefers concise SQL-first answers. This should become only Alice's personal
  preference.
- Bob discovers that the curated revenue view excludes refunded orders. This may
  help everyone, but it requires review before becoming shared memory.
- The official metric definition remains in the managed Knowledge Base.
- A repeatable revenue-validation procedure is eventually promoted into a Skill.

## Demo Sequence

1. Alice asks for an analysis and states: "Prefer SQL first and keep explanations
   short." The agent writes the completed turn to Personal Memory with actor
   `user:<alice-sub>`. The preference strategy extracts it asynchronously.
2. Bob runs a tool that verifies the refund exclusion and proposes the sanitized
   candidate from `contracts/memory-candidate-proposed.json`.
3. EventBridge starts the Standard Step Functions execution.
4. The graph stops at `WaitForHumanReview`; the reviewer receives a candidate ID,
   not a task token or raw conversation.
5. The reviewer reads the evidence in the observability platform and approves.
6. The reviewer API calls `SendTaskSuccess`. The workflow writes the approved text
   directly as a long-term Shared Memory record in
   `/projects/project:analytics-poc/shared/`. The candidate ID is its idempotency key;
   no second model extraction rewrites the approved statement.
7. Carol starts a new session. The agent retrieves:
   - the official metric definition from the Knowledge Base;
   - the approved refund caveat from Shared Memory;
   - Carol's own preferences, not Alice's.
   `ContextBuilder` keeps these sources in separate fields, supplies an explicit
   precedence rule, and includes record ID, namespace, score, and strategy ID as a
   citation envelope.
8. Mark the shared record as a `procedure_hint`. Open a Git change against
   `skills/validate-revenue-metric/SKILL.md`; after review and tests, the Skill
   becomes the executable authority.

## Expected Step Functions View

```text
RegisterCandidate
  -> CandidateEligible?
  -> WaitForHumanReview [Running]
  -> Approved?
  -> PublishSharedMemory
  -> MarkPublished
```

Rejected privacy candidates follow `MarkRejected` without exposing them to the
shared Memory resource.

## Scripted Scenario and Test Report

`run_validation.py` asserts four boolean capability checks. `run_demo_scenario.py`
instead drives the whole story against live AWS and writes a narrated report:

```bash
python3 poc/run_demo_scenario.py --deployment build/poc-deployment.json
```

It produces `docs/scenario-test-report.md` (narrative, with every prompt, answer,
and record ID) and `build/scenario-results.json` (machine-readable steps), exiting
non-zero if any check fails.

Five acts, fourteen checks: personal continuity and preference extraction; one user
unable to read another's memory; the policy gate blocking a restricted-classification
candidate at 0.98 confidence and a 0.35-confidence candidate before any human sees
them; human review including anonymous 401, task-token non-exposure, verbatim
publication, replay returning 409, and rejection auditing; and finally a newcomer
citing the record approved minutes earlier while inheriting nothing personal.

Two assertion traps worth preserving. Waiting for "any record" in the shared
namespace passes on records left by earlier runs, so Act 5 waits for the specific
`memoryRecordId` published in Act 4. And "Bob sees nothing" passes vacuously when
extraction never ran, so Act 2 also asserts Alice's namespace is non-empty.

## Governance Dashboard

```bash
python3 dashboard/server.py --deployment build/poc-deployment.json --port 3000
```

Open `http://localhost:3000`. The server binds `127.0.0.1` only and makes the
read-only Memory calls with the operator's local AWS credentials, so the browser never
receives AWS credentials and never reads DynamoDB. Review decisions go from the browser
straight to the Cognito-protected Review API, which re-checks project reviewer group
membership on every request.

| View | Shows | Source |
|---|---|---|
| Personal Memory | actor and session pickers, short-term events with parsed turns, extracted preferences, session summary | `ListActors`, `ListSessions`, `ListEvents`, `ListMemoryRecords` |
| Shared Memory | fixed project namespace, inventory browse and semantic search kept separate, each record with ID, namespace, score, strategy ID, and metadata | `ListMemoryRecords` vs `RetrieveMemoryRecords` with `project_id` and `review_status` filters |
| Review Queue | candidates by status with evidence reference, proposer, and published shared record ID; approve/reject on pending items | `GET`/`POST /reviews` with a Cognito ID token |

`reviewerOrigin` must match the dashboard origin, because the reviewer Lambda returns
that exact value in `access-control-allow-origin`.

Sign-in needs a Cognito user in the project reviewer group emitted by the stack. Use a
different account than the one `run_validation.py` drives, because the validation run
rotates its own reviewer password on every execution:

```bash
aws cognito-idp admin-create-user --user-pool-id <ReviewerUserPoolId> \
  --username <you@example.com> --message-action SUPPRESS
aws cognito-idp admin-set-user-password --user-pool-id <ReviewerUserPoolId> \
  --username <you@example.com> --password '<password>' --permanent
aws cognito-idp admin-add-user-to-group --user-pool-id <ReviewerUserPoolId> \
  --username <you@example.com> --group-name <ReviewerGroupName>
```

The header line reports which groups the token carries and warns when the account is
not in the reviewer group, since the API returns 403 in that case.

Layout and functional regression check across desktop, laptop, and mobile viewports:

```bash
REVIEWER_EMAIL=<reviewer> REVIEWER_PASSWORD=<password> \
  node dashboard/check_layout.mjs
```

It fails on any element overlap, horizontal overflow, or console error, and writes
screenshots to `build/dashboard-screenshots/`.

## Production Extensions

- For a Strands agent, use `AgentCoreMemorySessionManager` for ordinary personal
  turn persistence and keep `TurnRecorder` focused on sanitized governance events.
- Gate user input before storage and gate recalled memory before prompt injection
  with a workload-specific Bedrock Guardrail policy.
- Mark tool, system, debug, import, and sensitive events with
  `extractionMode="SKIP"` when they must remain in short-term memory but must not
  produce personal long-term records.
- Add a reviewer web application with candidate diff, evidence deep links, and
  project membership authorization.
- Use a one-time promotion queue for Knowledge Base document PRs and Skill PRs.
- Add automated evaluation for leakage, stale-memory conflicts, and retrieval
  attribution.
- Add deletion propagation for privacy requests across logs, memories, documents,
  and vector indexes.
- Add `METADATA_ONLY` record streaming when downstream lifecycle consumers justify
  Kinesis cost and exposure; make consumers idempotent.
- Add cross-region dual-write/record replication only after defining RTO, RPO, and
  data-residency requirements.
