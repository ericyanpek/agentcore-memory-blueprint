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
ALICE = "user:alice-memory-poc"
BOB = "user:bob-memory-poc"
CAROL = "user:carol-memory-poc"
# Per-run session IDs: with fixed ones, a re-run finds the previous run's events
# already present and the short-term check passes even if this run's write failed.
RUN_TAG = uuid.uuid4().hex[:8]
ALICE_SESSION = f"memory-poc-alice-session-a-{RUN_TAG}"
ALICE_NEW_SESSION = f"memory-poc-alice-session-b-{RUN_TAG}"
BOB_SESSION = f"memory-poc-bob-session-0000-{RUN_TAG}"
CAROL_SESSION = f"memory-poc-carol-session-00-{RUN_TAG}"
CODE_WORD = "ORBIT-742"


def read_json(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def invoke_runtime(
    client: Any,
    *,
    runtime_arn: str,
    session_id: str,
    actor_id: str,
    prompt: str,
) -> dict[str, Any]:
    response = client.invoke_agent_runtime(
        agentRuntimeArn=runtime_arn,
        qualifier="default",
        runtimeSessionId=session_id,
        contentType="application/json",
        accept="application/json",
        payload=json.dumps(
            {"actor_id": actor_id, "prompt": prompt}
        ).encode(),
    )
    body = response["response"].read()
    document = json.loads(body)
    if not isinstance(document, dict):
        raise RuntimeError(f"unexpected Runtime response: {document!r}")
    return document


def list_events(
    memory: Any,
    *,
    memory_id: str,
    actor_id: str,
    session_id: str,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    paginator = memory.get_paginator("list_events")
    for page in paginator.paginate(
        memoryId=memory_id,
        actorId=actor_id,
        sessionId=session_id,
        includePayloads=True,
        PaginationConfig={"PageSize": 100},
    ):
        events.extend(page.get("events", []))
    return events


def retrieve_records(
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
    response = memory.retrieve_memory_records(
        memoryId=memory_id,
        namespace=namespace,
        searchCriteria=criteria,
        maxResults=10,
    )
    return response.get("memoryRecordSummaries", [])


def wait_for_records(
    memory: Any,
    *,
    memory_id: str,
    namespace: str,
    query: str,
    timeout_seconds: int,
    metadata_filters: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        records = retrieve_records(
            memory,
            memory_id=memory_id,
            namespace=namespace,
            query=query,
            metadata_filters=metadata_filters,
        )
        if records:
            return records
        time.sleep(15)
    return []


def find_candidate_table(dynamodb: Any, expected_name: str) -> str:
    table_names: list[str] = []
    paginator = dynamodb.get_paginator("list_tables")
    for page in paginator.paginate():
        table_names.extend(page.get("TableNames", []))
    if expected_name not in table_names:
        raise RuntimeError(f"candidate table not found: {expected_name}")
    return expected_name


def wait_for_candidate(
    dynamodb: Any,
    *,
    table_name: str,
    candidate_id: str,
    expected_status: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    terminal_failures = {
        "PUBLISH_FAILED",
        "REJECTED_POLICY",
        "REJECTED_REVIEW",
    }
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        response = dynamodb.get_item(
            TableName=table_name,
            Key={"candidate_id": {"S": candidate_id}},
            ConsistentRead=True,
        )
        item = response.get("Item")
        if item:
            current_status = item.get("status", {}).get("S")
            if current_status == expected_status:
                return item
            if current_status in terminal_failures:
                raise RuntimeError(
                    f"{candidate_id} reached {current_status}, "
                    f"expected {expected_status}"
                )
        time.sleep(5)
    raise TimeoutError(
        f"{candidate_id} did not reach {expected_status} in time"
    )


def reviewer_password() -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "Aa1!" + "".join(secrets.choice(alphabet) for _ in range(20))


def reviewer_token(
    cognito: Any,
    *,
    user_pool_id: str,
    client_id: str,
    group_name: str,
) -> str:
    # Dedicated account: this rotates its own password on every run, so it must
    # not be the reviewer a human uses to sign in to the dashboard.
    username = "memory-poc-validation@example.com"
    password = reviewer_password()
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


def approve_candidate(url: str, token: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        method="POST",
        data=json.dumps({"decision": "APPROVED"}).encode(),
        headers={
            "authorization": token,
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        body = error.read().decode(errors="replace")
        raise RuntimeError(
            f"review API returned {error.code}: {body}"
        ) from error


def emit_candidate(
    events: Any,
    *,
    event_bus_name: str,
    candidate_id: str,
    project_id: str,
) -> None:
    detail = {
        "schema_version": "1.0",
        "candidate_id": candidate_id,
        "project_id": project_id,
        "proposer_actor_id": BOB,
        "category": "constraint",
        "statement": (
            "The curated revenue view excludes refunded orders; gross booked "
            "revenue analysis must use the booking ledger."
        ),
        "evidence_ref": (
            "trace://1-abcdef01-0123456789abcdef01234567/tool/4"
        ),
        "confidence": 0.96,
        "privacy_classification": "internal",
        "expires_at": None,
        "promotion_hint": "none",
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
        raise RuntimeError(f"candidate event failed: {response['Entries']}")


def summarize_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "memory_record_id": record.get("memoryRecordId"),
            "text": record.get("content", {}).get("text"),
            "namespaces": record.get("namespaces", []),
            "score": record.get("score"),
            "metadata": record.get("metadata", {}),
        }
        for record in records
    ]


def validate(config: dict[str, Any]) -> dict[str, Any]:
    project_id = config["project_id"]
    session = boto3.Session(region_name=config["region"])
    runtime = session.client("bedrock-agentcore", config=AWS_CONFIG)
    memory = session.client("bedrock-agentcore", config=AWS_CONFIG)
    events = session.client("events", config=AWS_CONFIG)
    dynamodb = session.client("dynamodb", config=AWS_CONFIG)
    cognito = session.client("cognito-idp", config=AWS_CONFIG)

    alice_intro = invoke_runtime(
        runtime,
        runtime_arn=config["runtime_arn"],
        session_id=ALICE_SESSION,
        actor_id=ALICE,
        prompt=(
            f"Remember that my project code word is {CODE_WORD}. "
            "Acknowledge briefly."
        ),
    )
    alice_recall = invoke_runtime(
        runtime,
        runtime_arn=config["runtime_arn"],
        session_id=ALICE_SESSION,
        actor_id=ALICE,
        prompt="What is my project code word?",
    )
    alice_events = list_events(
        memory,
        memory_id=config["personal_memory_id"],
        actor_id=ALICE,
        session_id=ALICE_SESSION,
    )
    stm_passed = (
        CODE_WORD.lower()
        in alice_recall.get("response", "").lower()
        and len(alice_events) >= 2
    )

    preference_turn = invoke_runtime(
        runtime,
        runtime_arn=config["runtime_arn"],
        session_id=ALICE_SESSION,
        actor_id=ALICE,
        prompt=(
            "My durable response preference is concise Chinese bullet points. "
            "Please remember this preference."
        ),
    )
    preference_namespace = f"/users/{ALICE}/preferences/"
    preference_records = wait_for_records(
        memory,
        memory_id=config["personal_memory_id"],
        namespace=preference_namespace,
        query="response language and formatting preference",
        timeout_seconds=240,
    )
    alice_new_session = invoke_runtime(
        runtime,
        runtime_arn=config["runtime_arn"],
        session_id=ALICE_NEW_SESSION,
        actor_id=ALICE,
        prompt="Describe my stored response preference and follow it.",
    )
    preference_passed = bool(preference_records)

    bob_response = invoke_runtime(
        runtime,
        runtime_arn=config["runtime_arn"],
        session_id=BOB_SESSION,
        actor_id=BOB,
        prompt="What are my stored code word and response preference?",
    )
    bob_preference_records = retrieve_records(
        memory,
        memory_id=config["personal_memory_id"],
        namespace=f"/users/{BOB}/preferences/",
        query="response preference",
    )
    # Requiring Alice's namespace to be non-empty is what makes this a real
    # isolation check: "Bob sees nothing" also holds when extraction never ran and
    # both namespaces are empty, which proves absence rather than isolation.
    isolation_passed = (
        bool(preference_records)
        and not bob_preference_records
        and CODE_WORD.lower()
        not in bob_response.get("response", "").lower()
    )

    candidate_table = find_candidate_table(
        dynamodb, config["candidate_table_name"]
    )
    candidate_id = f"cand-poc-{uuid.uuid4().hex[:12]}"
    emit_candidate(
        events,
        event_bus_name=config["event_bus_name"],
        candidate_id=candidate_id,
        project_id=project_id,
    )
    wait_for_candidate(
        dynamodb,
        table_name=candidate_table,
        candidate_id=candidate_id,
        expected_status="PENDING_REVIEW",
        timeout_seconds=120,
    )
    token = reviewer_token(
        cognito,
        user_pool_id=config["reviewer_user_pool_id"],
        client_id=config["reviewer_client_id"],
        group_name=config["reviewer_group_name"],
    )
    review_result = approve_candidate(
        (
            config["review_api_url"].rstrip("/")
            + f"/reviews/{candidate_id}"
        ),
        token,
    )
    published_item = wait_for_candidate(
        dynamodb,
        table_name=candidate_table,
        candidate_id=candidate_id,
        expected_status="PUBLISHED",
        timeout_seconds=180,
    )
    shared_namespace = f"/projects/project:{project_id}/shared/"
    shared_records = wait_for_records(
        memory,
        memory_id=config["shared_memory_id"],
        namespace=shared_namespace,
        query="refunds and gross booked revenue",
        timeout_seconds=180,
        metadata_filters=[
            {
                "left": {"metadataKey": "project_id"},
                "operator": "EQUALS_TO",
                "right": {
                    "metadataValue": {"stringValue": project_id}
                },
            },
            {
                "left": {"metadataKey": "review_status"},
                "operator": "EQUALS_TO",
                "right": {
                    "metadataValue": {"stringValue": "approved"}
                },
            },
        ],
    )
    carol_response = invoke_runtime(
        runtime,
        runtime_arn=config["runtime_arn"],
        session_id=CAROL_SESSION,
        actor_id=CAROL,
        prompt=(
            "Which source should I use for gross booked revenue, and what "
            "does the curated view exclude?"
        ),
    )
    shared_passed = (
        bool(shared_records)
        and bool(carol_response.get("shared_memory_citations"))
        and "booking ledger"
        in carol_response.get("response", "").lower()
    )

    checks = {
        "short_term_same_session": stm_passed,
        "personal_preference_long_term": preference_passed,
        "cross_user_isolation": isolation_passed,
        "reviewed_shared_memory": shared_passed,
    }
    return {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "all_passed": all(checks.values()),
        "short_term": {
            "intro_response": alice_intro,
            "recall_response": alice_recall,
            "event_count": len(alice_events),
        },
        "personal_preference": {
            "preference_turn": preference_turn,
            "records": summarize_records(preference_records),
            "new_session_response": alice_new_session,
        },
        "isolation": {
            "bob_preference_record_count": len(bob_preference_records),
            "bob_response": bob_response,
        },
        "shared_memory": {
            "candidate_id": candidate_id,
            "review_result": review_result,
            "published_memory_record_id": published_item.get(
                "shared_memory_record_id", {}
            ).get("S"),
            "records": summarize_records(shared_records),
            "carol_response": carol_response,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deployment", type=pathlib.Path, required=True)
    parser.add_argument(
        "--result",
        type=pathlib.Path,
        default=pathlib.Path("build/poc-validation-results.json"),
    )
    args = parser.parse_args()
    try:
        result = validate(read_json(args.deployment))
        args.result.parent.mkdir(parents=True, exist_ok=True)
        args.result.write_text(json.dumps(result, indent=2, default=str) + "\n")
        print(json.dumps(result, indent=2, default=str))
        return 0 if result["all_passed"] else 2
    except (
        ClientError,
        RuntimeError,
        TimeoutError,
        urllib.error.URLError,
    ) as error:
        print(f"Validation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
