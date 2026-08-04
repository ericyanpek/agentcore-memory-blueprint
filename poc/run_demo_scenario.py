"""End-to-end governance scenario for the AgentCore Memory POC.

Drives the real Runtime, Memory, EventBridge, Step Functions, and Cognito review
API through a multi-user churn-analysis story, then writes a Markdown test report.

Unlike run_validation.py, which asserts four boolean checks, this script narrates
the lifecycle: what each user said, what the agent recalled, which candidates the
policy gate blocked before a human ever saw them, what a reviewer approved or
rejected, and which knowledge became visible to the rest of the project.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import secrets
import string
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


AWS_CONFIG = Config(
    retries={"total_max_attempts": 8, "mode": "adaptive"},
    connect_timeout=5,
    read_timeout=120,
)
ALICE = "user:alice-churn-demo"
BOB = "user:bob-churn-demo"
CAROL = "user:carol-churn-demo"
RUN_TAG = uuid.uuid4().hex[:8]
# Runtime requires runtimeSessionId to be at least 33 characters.
ALICE_SESSION_A = f"churn-demo-alice-session-a-{RUN_TAG}"
ALICE_SESSION_B = f"churn-demo-alice-session-b-{RUN_TAG}"
BOB_SESSION = f"churn-demo-bob-session-000-{RUN_TAG}"
CAROL_SESSION = f"churn-demo-carol-session-0-{RUN_TAG}"
EXTRACTION_TIMEOUT = 300


class Recorder:
    """Collects an ordered narrative of every step for the report."""

    def __init__(self) -> None:
        self.steps: list[dict[str, Any]] = []

    def add(
        self,
        *,
        act: str,
        title: str,
        detail: dict[str, Any],
        expected: str,
        observed: str,
        passed: bool,
    ) -> None:
        self.steps.append(
            {
                "index": len(self.steps) + 1,
                "act": act,
                "title": title,
                "detail": detail,
                "expected": expected,
                "observed": observed,
                "passed": passed,
            }
        )
        mark = "PASS" if passed else "FAIL"
        print(f"[{mark}] {act} · {title}\n       {observed}", flush=True)

    @property
    def all_passed(self) -> bool:
        return all(step["passed"] for step in self.steps)


def ask(
    runtime: Any,
    *,
    runtime_arn: str,
    session_id: str,
    actor_id: str,
    prompt: str,
) -> dict[str, Any]:
    response = runtime.invoke_agent_runtime(
        agentRuntimeArn=runtime_arn,
        qualifier="default",
        runtimeSessionId=session_id,
        contentType="application/json",
        accept="application/json",
        payload=json.dumps({"actor_id": actor_id, "prompt": prompt}).encode(),
    )
    document = json.loads(response["response"].read())
    if not isinstance(document, dict):
        raise RuntimeError(f"unexpected Runtime response: {document!r}")
    return document


def count_events(memory: Any, *, memory_id: str, actor_id: str, session_id: str) -> int:
    total = 0
    paginator = memory.get_paginator("list_events")
    for page in paginator.paginate(
        memoryId=memory_id,
        actorId=actor_id,
        sessionId=session_id,
        includePayloads=False,
        PaginationConfig={"PageSize": 100},
    ):
        total += len(page.get("events", []))
    return total


def retrieve(
    memory: Any,
    *,
    memory_id: str,
    namespace: str,
    query: str,
    metadata_filters: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    criteria: dict[str, Any] = {"searchQuery": query, "topK": 10}
    if metadata_filters:
        criteria["metadataFilters"] = metadata_filters
    try:
        response = memory.retrieve_memory_records(
            memoryId=memory_id,
            namespace=namespace,
            searchCriteria=criteria,
            maxResults=10,
        )
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
            return []
        raise
    return response.get("memoryRecordSummaries", [])


def wait_for_records(
    memory: Any,
    *,
    memory_id: str,
    namespace: str,
    query: str,
    timeout_seconds: int,
    metadata_filters: list[dict[str, Any]] | None = None,
    required_record_id: str | None = None,
) -> list[dict[str, Any]]:
    """Poll retrieval until results appear.

    A newly published record is only eventually consistent for retrieval, and
    older records in the same namespace will satisfy a bare "any results" check.
    Pass required_record_id so the wait is specific to the record under test.
    """
    deadline = time.time() + timeout_seconds
    while True:
        records = retrieve(
            memory,
            memory_id=memory_id,
            namespace=namespace,
            query=query,
            metadata_filters=metadata_filters,
        )
        if required_record_id is None:
            satisfied = bool(records)
        else:
            satisfied = any(
                record.get("memoryRecordId") == required_record_id
                for record in records
            )
        if satisfied or time.time() >= deadline:
            return records
        time.sleep(15)


def approved_filters(project_id: str) -> list[dict[str, Any]]:
    return [
        {
            "left": {"metadataKey": "project_id"},
            "operator": "EQUALS_TO",
            "right": {"metadataValue": {"stringValue": project_id}},
        },
        {
            "left": {"metadataKey": "review_status"},
            "operator": "EQUALS_TO",
            "right": {"metadataValue": {"stringValue": "approved"}},
        },
    ]


def propose(
    events: Any,
    *,
    event_bus_name: str,
    project_id: str,
    candidate: dict[str, Any],
) -> str:
    candidate_id = f"cand-demo-{uuid.uuid4().hex[:12]}"
    detail = {
        "schema_version": "1.0",
        "candidate_id": candidate_id,
        "project_id": project_id,
        "expires_at": None,
        "promotion_hint": "none",
        **candidate,
    }
    response = events.put_events(
        Entries=[
            {
                "EventBusName": event_bus_name,
                "Source": "demo.analytics-agent",
                "DetailType": "memory.candidate.proposed",
                "Detail": json.dumps(detail),
            }
        ]
    )
    if response.get("FailedEntryCount", 0):
        raise RuntimeError(f"candidate event rejected: {response['Entries']}")
    return candidate_id


def wait_for_status(
    dynamodb: Any,
    *,
    table_name: str,
    candidate_id: str,
    wanted: set[str],
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    while True:
        item = dynamodb.get_item(
            TableName=table_name,
            Key={"candidate_id": {"S": candidate_id}},
            ConsistentRead=True,
        ).get("Item")
        if item and item.get("status", {}).get("S") in wanted:
            return item
        if time.time() >= deadline:
            found = item.get("status", {}).get("S") if item else "absent"
            raise TimeoutError(
                f"{candidate_id} stayed at {found}, expected one of {sorted(wanted)}"
            )
        time.sleep(5)


def _callback_states(
    context: dict[str, Any], candidate_ids: list[str]
) -> dict[str, str]:
    """Read each candidate's callback row, which is where the task token lives."""
    table = context["config"]["candidate_table_name"].replace(
        "memory-candidates", "review-callbacks"
    )
    states: dict[str, str] = {}
    for candidate_id in candidate_ids:
        item = context["dynamodb"].get_item(
            TableName=table,
            Key={"candidate_id": {"S": candidate_id}},
            ConsistentRead=True,
        ).get("Item")
        states[candidate_id] = (
            item.get("status", {}).get("S", "unknown") if item else "absent"
        )
    return states


def plain(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: next(iter(value.values()))
        for key, value in item.items()
        if key != "task_token"
    }


def reviewer_token(
    cognito: Any,
    *,
    user_pool_id: str,
    client_id: str,
    group_name: str,
) -> str:
    username = "memory-poc-demo-reviewer@example.com"
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    password = "Aa1!" + "".join(secrets.choice(alphabet) for _ in range(20))
    try:
        cognito.admin_create_user(
            UserPoolId=user_pool_id,
            Username=username,
            UserAttributes=[
                {"Name": "email", "Value": username},
                {"Name": "email_verified", "Value": "true"},
            ],
            MessageAction="SUPPRESS",
        )
    except cognito.exceptions.UsernameExistsException:
        pass
    cognito.admin_set_user_password(
        UserPoolId=user_pool_id,
        Username=username,
        Password=password,
        Permanent=True,
    )
    cognito.admin_add_user_to_group(
        UserPoolId=user_pool_id,
        Username=username,
        GroupName=group_name,
    )
    auth = cognito.initiate_auth(
        ClientId=client_id,
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": username, "PASSWORD": password},
    )
    return auth["AuthenticationResult"]["IdToken"]


def call_review_api(
    url: str,
    *,
    token: str | None,
    decision: str | None = None,
    reason: str = "Scenario run: evidence and statement checked by the reviewer.",
) -> tuple[int, Any]:
    headers = {"content-type": "application/json"}
    if token:
        headers["authorization"] = token
    request = urllib.request.Request(
        url,
        method="POST" if decision else "GET",
        data=(
            json.dumps(
                {"decision": decision, "status_reason": reason}
            ).encode()
            if decision
            else None
        ),
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        body = error.read().decode(errors="replace")
        try:
            return error.code, json.loads(body)
        except ValueError:
            return error.code, body


def summarize(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "memory_record_id": record.get("memoryRecordId"),
            "text": record.get("content", {}).get("text"),
            "namespaces": record.get("namespaces", []),
            "score": record.get("score"),
            "memory_strategy_id": record.get("memoryStrategyId"),
        }
        for record in records
    ]


def act_one_personal(context: dict[str, Any], recorder: Recorder) -> dict[str, Any]:
    """Personal memory: continuity inside a session, preference across sessions."""
    runtime = context["runtime"]
    memory = context["memory"]
    arn = context["config"]["runtime_arn"]
    personal = context["config"]["personal_memory_id"]

    first = ask(
        runtime,
        runtime_arn=arn,
        session_id=ALICE_SESSION_A,
        actor_id=ALICE,
        prompt=(
            "I am analysing Q3 churn for the enterprise segment. My durable "
            "preference is concise Chinese bullet points. The cohort ID I care "
            "about is CHURN-Q3-ENT."
        ),
    )
    recall = ask(
        runtime,
        runtime_arn=arn,
        session_id=ALICE_SESSION_A,
        actor_id=ALICE,
        prompt="Which cohort ID am I analysing?",
    )
    event_count = count_events(
        memory, memory_id=personal, actor_id=ALICE, session_id=ALICE_SESSION_A
    )
    recalled = "churn-q3-ent" in recall.get("response", "").lower()
    recorder.add(
        act="Act 1 · Personal memory",
        title="Short-term memory keeps context within one session",
        detail={
            "actor_id": ALICE,
            "session_id": ALICE_SESSION_A,
            "turn_1": first.get("response"),
            "turn_2_question": "Which cohort ID am I analysing?",
            "turn_2_answer": recall.get("response"),
            "events_written": event_count,
        },
        expected="Agent recalls cohort CHURN-Q3-ENT from the same session; turns persisted",
        observed=(
            f"recalled cohort={recalled}, {event_count} events written to "
            f"{personal}"
        ),
        passed=recalled and event_count >= 2,
    )

    preference_namespace = f"/users/{ALICE}/preferences/"
    preference_records = wait_for_records(
        memory,
        memory_id=personal,
        namespace=preference_namespace,
        query="response language and formatting preference",
        timeout_seconds=EXTRACTION_TIMEOUT,
    )
    recorder.add(
        act="Act 1 · Personal memory",
        title="Preference strategy extracts a durable personal record",
        detail={
            "namespace": preference_namespace,
            "records": summarize(preference_records),
        },
        expected=f"At least one extracted record under {preference_namespace}",
        observed=f"{len(preference_records)} preference record(s) extracted asynchronously",
        passed=bool(preference_records),
    )

    new_session = ask(
        runtime,
        runtime_arn=arn,
        session_id=ALICE_SESSION_B,
        actor_id=ALICE,
        prompt="Starting fresh. How do I prefer answers formatted?",
    )
    text = new_session.get("response", "")
    honoured = any(
        token in text.lower() for token in ("chinese", "中文", "bullet", "要点")
    )
    recorder.add(
        act="Act 1 · Personal memory",
        title="Preference survives into a brand-new session",
        detail={
            "session_id": ALICE_SESSION_B,
            "question": "Starting fresh. How do I prefer answers formatted?",
            "answer": text,
        },
        expected="New session retrieves Alice's preference without her repeating it",
        observed=(
            "preference restored in a new session"
            if honoured
            else "agent did not reference the stored preference"
        ),
        passed=honoured,
    )
    return {"preference_records": summarize(preference_records)}


def act_two_isolation(context: dict[str, Any], recorder: Recorder) -> None:
    """A second user must not inherit the first user's personal memory."""
    runtime = context["runtime"]
    memory = context["memory"]
    personal = context["config"]["personal_memory_id"]

    bob = ask(
        runtime,
        runtime_arn=context["config"]["runtime_arn"],
        session_id=BOB_SESSION,
        actor_id=BOB,
        prompt="What cohort ID am I analysing, and how do I prefer answers formatted?",
    )
    bob_text = bob.get("response", "").lower()
    bob_records = retrieve(
        memory,
        memory_id=personal,
        namespace=f"/users/{BOB}/preferences/",
        query="response preference",
    )
    # Control: Alice's namespace must be non-empty, otherwise "Bob sees nothing"
    # would pass simply because extraction never ran.
    alice_records = retrieve(
        memory,
        memory_id=personal,
        namespace=f"/users/{ALICE}/preferences/",
        query="response preference",
    )
    leaked = "churn-q3-ent" in bob_text
    recorder.add(
        act="Act 2 · Isolation",
        title="Bob cannot read Alice's cohort or preference",
        detail={
            "actor_id": BOB,
            "question": (
                "What cohort ID am I analysing, and how do I prefer answers formatted?"
            ),
            "answer": bob.get("response"),
            "bob_namespace": f"/users/{BOB}/preferences/",
            "bob_preference_record_count": len(bob_records),
            "alice_namespace": f"/users/{ALICE}/preferences/",
            "alice_preference_record_count": len(alice_records),
        },
        expected=(
            "No trace of CHURN-Q3-ENT, zero records under Bob's namespace, while "
            "Alice's namespace is non-empty"
        ),
        observed=(
            f"cohort leaked={leaked}, Bob has {len(bob_records)} record(s), "
            f"Alice has {len(alice_records)} record(s)"
        ),
        passed=not leaked and not bob_records and bool(alice_records),
    )


def act_three_policy_gate(context: dict[str, Any], recorder: Recorder) -> None:
    """Policy must reject unsafe or weak candidates before any human sees them."""
    config = context["config"]
    table = config["candidate_table_name"]

    restricted_id = propose(
        context["events"],
        event_bus_name=config["event_bus_name"],
        project_id=config["project_id"],
        candidate={
            "proposer_actor_id": BOB,
            "category": "fact",
            "statement": (
                "Enterprise account ACME churned because their CFO shared that "
                "their internal budget was frozen after a restructuring."
            ),
            "evidence_ref": "trace://1-aaaa1111-2222333344445555666677/tool/2",
            "confidence": 0.98,
            "privacy_classification": "restricted",
        },
    )
    restricted_item = wait_for_status(
        context["dynamodb"],
        table_name=table,
        candidate_id=restricted_id,
        wanted={"REJECTED_POLICY", "PENDING_REVIEW"},
        timeout_seconds=120,
    )
    restricted_status = restricted_item["status"]["S"]
    recorder.add(
        act="Act 3 · Policy gate",
        title="Restricted-classification candidate is blocked before human review",
        detail={
            "candidate_id": restricted_id,
            "privacy_classification": "restricted",
            "confidence": 0.98,
            "status": restricted_status,
            "item": plain(restricted_item),
        },
        expected="REJECTED_POLICY without ever entering the reviewer queue",
        observed=f"status={restricted_status} (high confidence did not override privacy)",
        passed=restricted_status == "REJECTED_POLICY",
    )

    weak_id = propose(
        context["events"],
        event_bus_name=config["event_bus_name"],
        project_id=config["project_id"],
        candidate={
            "proposer_actor_id": BOB,
            "category": "fact",
            "statement": (
                "Enterprise churn in Q3 was probably driven by the pricing change, "
                "but the attribution is still a guess."
            ),
            "evidence_ref": "trace://1-aaaa1111-2222333344445555666678/tool/5",
            "confidence": 0.35,
            "privacy_classification": "internal",
        },
    )
    weak_item = wait_for_status(
        context["dynamodb"],
        table_name=table,
        candidate_id=weak_id,
        wanted={"REJECTED_POLICY", "PENDING_REVIEW"},
        timeout_seconds=120,
    )
    weak_status = weak_item["status"]["S"]
    recorder.add(
        act="Act 3 · Policy gate",
        title="Low-confidence candidate is blocked before human review",
        detail={
            "candidate_id": weak_id,
            "confidence": 0.35,
            "threshold": 0.70,
            "status": weak_status,
        },
        expected="REJECTED_POLICY because confidence is below the 0.70 threshold",
        observed=f"status={weak_status}",
        passed=weak_status == "REJECTED_POLICY",
    )


def act_four_review(context: dict[str, Any], recorder: Recorder) -> dict[str, Any]:
    """Human review decides what becomes shared project knowledge."""
    config = context["config"]
    table = config["candidate_table_name"]
    review_root = config["review_api_url"].rstrip("/")

    approve_statement = (
        "The curated churn view counts a downgrade as churn; true logo churn "
        "must be measured from the subscription ledger instead."
    )
    approve_id = propose(
        context["events"],
        event_bus_name=config["event_bus_name"],
        project_id=config["project_id"],
        candidate={
            "proposer_actor_id": BOB,
            "category": "constraint",
            "statement": approve_statement,
            "evidence_ref": "trace://1-aaaa1111-2222333344445555666679/tool/4",
            "confidence": 0.95,
            "privacy_classification": "internal",
        },
    )
    reject_id = propose(
        context["events"],
        event_bus_name=config["event_bus_name"],
        project_id=config["project_id"],
        candidate={
            "proposer_actor_id": BOB,
            "category": "decision",
            "statement": (
                "The team decided to drop the enterprise segment from all future "
                "churn reporting starting next quarter."
            ),
            "evidence_ref": "trace://1-aaaa1111-2222333344445555666680/tool/6",
            "confidence": 0.88,
            "privacy_classification": "internal",
        },
    )
    parked = {}
    for candidate_id in (approve_id, reject_id):
        item = wait_for_status(
            context["dynamodb"],
            table_name=table,
            candidate_id=candidate_id,
            wanted={"PENDING_REVIEW"},
            timeout_seconds=120,
        )
        parked[candidate_id] = item["status"]["S"]
    # A held task token is what makes the pause real, so assert the callback rows
    # exist in WAITING rather than hardcoding a pass.
    waiting = _callback_states(context, list(parked))
    recorder.add(
        act="Act 4 · Human review",
        title="Eligible candidates wait for a human decision",
        detail={
            "approve_candidate": approve_id,
            "reject_candidate": reject_id,
            "candidate_status": parked,
            "callback_status": waiting,
            "workflow": "Step Functions WaitForHumanReview (task token held server-side)",
        },
        expected=(
            "Both candidates sit at PENDING_REVIEW and both callbacks hold a "
            "task token in WAITING"
        ),
        observed=(
            f"candidates={sorted(set(parked.values()))}, "
            f"callbacks={sorted(set(waiting.values()))}"
        ),
        passed=set(parked.values()) == {"PENDING_REVIEW"}
        and set(waiting.values()) == {"WAITING"},
    )

    anonymous_status, anonymous_body = call_review_api(
        f"{review_root}/reviews", token=None
    )
    recorder.add(
        act="Act 4 · Human review",
        title="Review API rejects unauthenticated access",
        detail={
            "request": "GET /reviews without an Authorization header",
            "status_code": anonymous_status,
            "body": anonymous_body,
        },
        expected="401 Unauthorized from the Cognito authorizer",
        observed=f"HTTP {anonymous_status}",
        passed=anonymous_status == 401,
    )

    token = reviewer_token(
        context["cognito"],
        user_pool_id=config["reviewer_user_pool_id"],
        client_id=config["reviewer_client_id"],
        group_name=config["reviewer_group_name"],
    )
    queue_status, queue_body = call_review_api(f"{review_root}/reviews", token=token)
    pending = [
        item
        for item in queue_body.get("candidates", [])
        if item.get("status") == "PENDING_REVIEW"
    ]
    token_leaked = "task_token" in json.dumps(queue_body)
    recorder.add(
        act="Act 4 · Human review",
        title="Reviewer in the project group reads the queue without task tokens",
        detail={
            "reviewer_group": config["reviewer_group_name"],
            "status_code": queue_status,
            "pending_count": len(pending),
            "task_token_exposed": token_leaked,
            "sample_candidate": pending[0] if pending else None,
        },
        expected="200 with pending candidates and no task_token in the payload",
        observed=(
            f"HTTP {queue_status}, {len(pending)} pending, "
            f"task_token exposed={token_leaked}"
        ),
        passed=queue_status == 200 and not token_leaked and bool(pending),
    )

    approve_status, approve_body = call_review_api(
        f"{review_root}/reviews/{approve_id}", token=token, decision="APPROVED"
    )
    published = wait_for_status(
        context["dynamodb"],
        table_name=table,
        candidate_id=approve_id,
        wanted={"PUBLISHED", "PUBLISH_FAILED"},
        timeout_seconds=240,
    )
    published_status = published["status"]["S"]
    record_id = published.get("shared_memory_record_id", {}).get("S")
    recorder.add(
        act="Act 4 · Human review",
        title="Approval publishes the reviewed statement verbatim to shared memory",
        detail={
            "candidate_id": approve_id,
            "api_response": approve_body,
            "status": published_status,
            "shared_memory_record_id": record_id,
            "reviewer_id": published.get("reviewer_id", {}).get("S"),
            "evidence_ref": published.get("evidence_ref", {}).get("S"),
        },
        expected="PUBLISHED with a shared memory record ID and reviewer identity recorded",
        observed=f"status={published_status}, record={record_id}",
        passed=published_status == "PUBLISHED" and bool(record_id),
    )

    replay_status, replay_body = call_review_api(
        f"{review_root}/reviews/{approve_id}", token=token, decision="APPROVED"
    )
    recorder.add(
        act="Act 4 · Human review",
        title="A consumed review token cannot be replayed",
        detail={
            "candidate_id": approve_id,
            "second_decision_attempt": "APPROVED",
            "status_code": replay_status,
            "body": replay_body,
        },
        expected="409 Conflict because the callback was already consumed",
        observed=f"HTTP {replay_status}",
        passed=replay_status == 409,
    )

    call_review_api(
        f"{review_root}/reviews/{reject_id}", token=token, decision="REJECTED"
    )
    rejected = wait_for_status(
        context["dynamodb"],
        table_name=table,
        candidate_id=reject_id,
        wanted={"REJECTED_REVIEW"},
        timeout_seconds=180,
    )
    rejected_text = rejected["statement"]["S"]
    # Scan the whole namespace rather than a scored search: retrieval ranking
    # could hide a leaked record, an inventory listing cannot.
    inventory = context["memory"].list_memory_records(
        memoryId=config["shared_memory_id"],
        namespace=context["shared_namespace"],
        maxResults=100,
    )["memoryRecordSummaries"]
    leaked_matches = [
        record.get("memoryRecordId")
        for record in inventory
        if rejected_text[:40] in (record.get("content", {}).get("text") or "")
    ]
    recorder.add(
        act="Act 4 · Human review",
        title="Rejection leaves an audit record but never reaches shared memory",
        detail={
            "candidate_id": reject_id,
            "status": rejected["status"]["S"],
            "statement": rejected_text,
            "shared_namespace_record_count": len(inventory),
            "records_containing_rejected_text": leaked_matches,
        },
        expected=(
            "REJECTED_REVIEW in the audit table and zero shared-memory records "
            "containing the rejected statement"
        ),
        observed=(
            f"status={rejected['status']['S']}, "
            f"{len(leaked_matches)} of {len(inventory)} shared records contain the "
            "rejected text"
        ),
        passed=rejected["status"]["S"] == "REJECTED_REVIEW" and not leaked_matches,
    )
    return {
        "approved_candidate_id": approve_id,
        "approved_statement": approve_statement,
        "approved_record_id": record_id,
        "rejected_candidate_id": reject_id,
    }


def act_five_shared_benefit(
    context: dict[str, Any],
    review: dict[str, Any],
    recorder: Recorder,
) -> None:
    """A third user benefits from reviewed knowledge she never contributed."""
    config = context["config"]
    new_record_id = review["approved_record_id"]
    records = wait_for_records(
        context["memory"],
        memory_id=config["shared_memory_id"],
        namespace=context["shared_namespace"],
        query="logo churn measurement and downgrades",
        timeout_seconds=420,
        metadata_filters=approved_filters(config["project_id"]),
        required_record_id=new_record_id,
    )
    found_new = any(
        record.get("memoryRecordId") == new_record_id for record in records
    )
    recorder.add(
        act="Act 5 · Shared benefit",
        title="The just-approved record becomes retrievable under the project namespace",
        detail={
            "namespace": context["shared_namespace"],
            "metadata_filters": "project_id + review_status=approved",
            "awaited_record_id": new_record_id,
            "records": summarize(records),
        },
        expected=(
            f"Record {new_record_id} published in Act 4 is retrievable with "
            "approved-only filters"
        ),
        observed=(
            f"{len(records)} approved record(s) retrievable; "
            f"new record present={found_new}"
        ),
        passed=found_new,
    )

    carol = ask(
        context["runtime"],
        runtime_arn=config["runtime_arn"],
        session_id=CAROL_SESSION,
        actor_id=CAROL,
        prompt=(
            "I am new to this project. How should I measure true logo churn, and "
            "what is wrong with the curated churn view?"
        ),
    )
    text = carol.get("response", "").lower()
    citations = carol.get("shared_memory_citations", [])
    cited_ids = [citation.get("memory_record_id") for citation in citations]
    cited_new = new_record_id in cited_ids
    informed = "subscription ledger" in text or "logo churn" in text
    alice_leak = "churn-q3-ent" in text
    recorder.add(
        act="Act 5 · Shared benefit",
        title="Carol inherits the reviewed knowledge but not Alice's personal memory",
        detail={
            "actor_id": CAROL,
            "question": (
                "How should I measure true logo churn, and what is wrong with the "
                "curated churn view?"
            ),
            "answer": carol.get("response"),
            "shared_memory_citations": citations,
            "cited_the_new_record": cited_new,
            "alice_cohort_leaked": alice_leak,
        },
        expected=(
            f"Answer cites {new_record_id} (Bob's approved finding) and leaks no "
            "personal memory from Alice"
        ),
        observed=(
            f"cited new record={cited_new}, citations={len(cited_ids)}, "
            f"applied shared knowledge={informed}, Alice's cohort leaked={alice_leak}"
        ),
        passed=cited_new and informed and not alice_leak,
    )


def render_report(
    *,
    config: dict[str, Any],
    recorder: Recorder,
    review: dict[str, Any],
    started_at: str,
    finished_at: str,
) -> str:
    total = len(recorder.steps)
    passed = sum(1 for step in recorder.steps if step["passed"])
    lines = [
        "# AgentCore Memory Governance — Scenario Test Report",
        "",
        "> Auto-generated from the live run. The primary interpreted report is "
        "[实验报告](实验报告.md) (Chinese).",
        "",
        f"- Run tag: `{RUN_TAG}`",
        f"- Started: {started_at}",
        f"- Finished: {finished_at}",
        f"- Region: `{config['region']}` · Project: `{config['project_id']}`",
        f"- Runtime: `{config['runtime_id']}` v{config['runtime_version']}",
        f"- Personal Memory: `{config['personal_memory_id']}`",
        f"- Shared Memory: `{config['shared_memory_id']}`",
        f"- Result: **{passed}/{total} checks passed**",
        "",
        "## Scenario",
        "",
        "Three analysts share one project agent for a Q3 enterprise churn review.",
        "Alice contributes a personal working preference. Bob discovers a metric",
        "trap and proposes it as shared knowledge, alongside candidates that must",
        "not survive governance. Carol joins later and should benefit from what was",
        "reviewed without inheriting anything personal.",
        "",
        "## Result Summary",
        "",
        "| # | Act | Check | Result |",
        "|---|---|---|---|",
    ]
    for step in recorder.steps:
        lines.append(
            f"| {step['index']} | {step['act'].split('·')[1].strip()} | "
            f"{step['title']} | {'PASS' if step['passed'] else 'FAIL'} |"
        )

    lines += ["", "## Narrative Detail", ""]
    current_act = None
    for step in recorder.steps:
        if step["act"] != current_act:
            current_act = step["act"]
            lines += [f"### {current_act}", ""]
        lines += [
            f"**{step['index']}. {step['title']}** — "
            f"{'PASS' if step['passed'] else 'FAIL'}",
            "",
            f"- Expected: {step['expected']}",
            f"- Observed: {step['observed']}",
            "",
            "```json",
            json.dumps(step["detail"], indent=2, ensure_ascii=False, default=str),
            "```",
            "",
        ]

    lines += [
        "## Governance Properties Demonstrated",
        "",
        "| Property | Evidence |",
        "|---|---|",
        "| Session continuity is per user and per session | Act 1 recall of cohort CHURN-Q3-ENT |",
        "| Personal preferences persist across sessions | Act 1 new-session answer |",
        "| One user cannot read another's personal memory | Act 2 Bob's answer and empty namespace |",
        "| Privacy classification outranks confidence | Act 3 restricted candidate at 0.98 confidence still blocked |",
        "| Weak evidence never reaches a reviewer | Act 3 low-confidence rejection |",
        "| Shared writes require an authenticated project reviewer | Act 4 401 without a token |",
        "| Reviewers never receive workflow task tokens | Act 4 queue payload inspection |",
        "| Approved text is stored verbatim, with reviewer and evidence | Act 4 published record |",
        "| A review decision cannot be replayed | Act 4 second decision returns 409 |",
        "| Rejected knowledge is audited, not published | Act 4 rejected candidate absent from shared memory |",
        "| Reviewed knowledge reaches users who never proposed it | Act 5 Carol's cited answer |",
        "",
        "## Artifacts",
        "",
        f"- Approved candidate: `{review.get('approved_candidate_id')}`",
        f"- Published shared record: `{review.get('approved_record_id')}`",
        f"- Rejected candidate: `{review.get('rejected_candidate_id')}`",
        f"- Candidate audit table: `{config['candidate_table_name']}`",
        f"- Shared namespace: `/projects/project:{config['project_id']}/shared/`",
        "",
        "Inspect all of this in the dashboard at `http://localhost:3000`.",
        "",
    ]
    # This report is committed to the repository, so the AWS account ID is masked
    # rather than published. Nothing else here identifies the environment.
    return "\n".join(lines).replace(config["account_id"], "<account-id>")


def run(config: dict[str, Any]) -> tuple[Recorder, str]:
    session = boto3.Session(region_name=config["region"])
    context = {
        "config": config,
        "runtime": session.client("bedrock-agentcore", config=AWS_CONFIG),
        "memory": session.client("bedrock-agentcore", config=AWS_CONFIG),
        "events": session.client("events", config=AWS_CONFIG),
        "dynamodb": session.client("dynamodb", config=AWS_CONFIG),
        "cognito": session.client("cognito-idp", config=AWS_CONFIG),
        "shared_namespace": f"/projects/project:{config['project_id']}/shared/",
    }
    recorder = Recorder()
    started_at = datetime.now(timezone.utc).isoformat()

    act_one_personal(context, recorder)
    act_two_isolation(context, recorder)
    act_three_policy_gate(context, recorder)
    review = act_four_review(context, recorder)
    act_five_shared_benefit(context, review, recorder)

    report = render_report(
        config=config,
        recorder=recorder,
        review=review,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc).isoformat(),
    )
    return recorder, report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--deployment",
        type=pathlib.Path,
        default=pathlib.Path("build/poc-deployment.json"),
    )
    parser.add_argument(
        "--report",
        type=pathlib.Path,
        default=pathlib.Path("docs/scenario-test-report.md"),
    )
    parser.add_argument(
        "--json",
        type=pathlib.Path,
        default=pathlib.Path("build/scenario-results.json"),
    )
    args = parser.parse_args()

    config = json.loads(args.deployment.read_text())
    try:
        recorder, report = run(config)
    except (ClientError, RuntimeError, TimeoutError, urllib.error.URLError) as error:
        print(f"Scenario failed: {error}", file=sys.stderr)
        return 1

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(
            {"all_passed": recorder.all_passed, "steps": recorder.steps},
            indent=2,
            default=str,
        )
        + "\n"
    )
    passed = sum(1 for step in recorder.steps if step["passed"])
    print(f"\n{passed}/{len(recorder.steps)} checks passed → {args.report}")
    return 0 if recorder.all_passed else 2


if __name__ == "__main__":
    sys.exit(main())
