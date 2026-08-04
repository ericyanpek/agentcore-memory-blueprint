from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.conditions import Attr

from blueprint.domain import has_reviewer_group


CANDIDATES = boto3.resource("dynamodb").Table(os.environ["CANDIDATE_TABLE_NAME"])
CALLBACKS = boto3.resource("dynamodb").Table(os.environ["CALLBACK_TABLE_NAME"])
SFN = boto3.client("stepfunctions")
REVIEWER_GROUP = os.environ["REVIEWER_GROUP"]
REVIEWER_ORIGIN = os.environ["REVIEWER_ORIGIN"]
# Long enough to force a real sentence, short enough to stay a reason not an essay.
MIN_REASON, MAX_REASON = 10, 500


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    reviewer_id, authorization_error = _authorized_reviewer(event)
    if authorization_error:
        return _response(403, {"message": authorization_error})

    method = event["httpMethod"]
    candidate_id = (event.get("pathParameters") or {}).get("candidate_id")
    if method == "GET" and not candidate_id:
        return _list_candidates(event)
    if method == "GET" and candidate_id:
        return _get_candidate(candidate_id)
    if method == "POST" and candidate_id:
        return _decide(event, candidate_id, reviewer_id)
    return _response(404, {"message": "route not found"})


def _authorized_reviewer(event: dict[str, Any]) -> tuple[str, str | None]:
    # API Gateway sends these keys with null values rather than omitting them, so
    # a `.get(key, {})` default does not protect the chained access.
    request_context = event.get("requestContext") or {}
    authorizer = request_context.get("authorizer") or {}
    claims = authorizer.get("claims") or {}
    reviewer_id = str(claims.get("sub", ""))
    if not reviewer_id:
        return "", "authenticated reviewer is required"
    if not has_reviewer_group(claims.get("cognito:groups"), REVIEWER_GROUP):
        return "", "project reviewer membership is required"
    return reviewer_id, None


def _list_candidates(event: dict[str, Any]) -> dict[str, Any]:
    parameters = event.get("queryStringParameters") or {}
    status = str(parameters.get("status") or "").strip().upper()
    try:
        limit = min(max(int(parameters.get("limit") or 50), 1), 100)
    except (TypeError, ValueError):
        return _response(400, {"message": "limit must be an integer"})

    items: list[dict[str, Any]] = []
    paginator = CANDIDATES.meta.client.get_paginator("scan")
    for page in paginator.paginate(TableName=CANDIDATES.name):
        for item in page.get("Items", []):
            if status and item.get("status") != status:
                continue
            item.pop("task_token", None)
            items.append(item)

    items.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
    return _response(
        200,
        {
            "candidates": items[:limit],
            "returned": min(len(items), limit),
            "matched": len(items),
        },
    )


def _get_candidate(candidate_id: str) -> dict[str, Any]:
    item = CANDIDATES.get_item(
        Key={"candidate_id": candidate_id},
        ConsistentRead=True,
    ).get("Item")
    if item is None:
        return _response(404, {"message": "candidate not found"})
    item.pop("task_token", None)
    return _response(200, item)


def _decide(
    event: dict[str, Any],
    candidate_id: str,
    reviewer_id: str,
) -> dict[str, Any]:
    body = json.loads(event.get("body") or "{}")
    decision = str(body.get("decision", "")).upper()
    if decision not in {"APPROVED", "REJECTED"}:
        return _response(400, {"message": "decision must be APPROVED or REJECTED"})

    # AgentCore's own approval API (UpdateRegistryRecordStatus) makes statusReason a
    # required parameter, and the reason is the part of the audit record that explains a
    # decision rather than merely recording it. A bare APPROVED tells a later reader that
    # someone signed off, not why the claim was judged sound.
    status_reason = str(body.get("status_reason", "")).strip()
    if not MIN_REASON <= len(status_reason) <= MAX_REASON:
        return _response(
            400,
            {
                "message": (
                    f"status_reason is required and must be "
                    f"{MIN_REASON}-{MAX_REASON} characters"
                )
            },
        )

    callback = CALLBACKS.get_item(
        Key={"candidate_id": candidate_id},
        ConsistentRead=True,
    ).get("Item")
    if callback is None or callback.get("status") != "WAITING":
        return _response(409, {"message": "candidate is not awaiting review"})

    now = datetime.now(timezone.utc).isoformat()
    try:
        CALLBACKS.update_item(
            Key={"candidate_id": candidate_id},
            UpdateExpression=(
                "SET #status = :deciding, reviewer_id = :reviewer, "
                "decision = :decision, decided_at = :now, "
                "status_reason = :reason"
            ),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":deciding": "DECIDING",
                ":reviewer": reviewer_id,
                ":decision": decision,
                ":now": now,
                ":reason": status_reason,
            },
            ConditionExpression=Attr("status").eq("WAITING"),
        )
    except CALLBACKS.meta.client.exceptions.ConditionalCheckFailedException:
        return _response(409, {"message": "review decision was already submitted"})

    SFN.send_task_success(
        taskToken=callback["task_token"],
        output=json.dumps(
            {
                "candidate_id": candidate_id,
                "decision": decision,
                "reviewer_id": reviewer_id,
                "reviewed_at": now,
                "status_reason": status_reason,
            }
        ),
    )
    CALLBACKS.update_item(
        Key={"candidate_id": candidate_id},
        UpdateExpression="SET #status = :consumed",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={
            ":consumed": "CONSUMED",
        },
        ConditionExpression=Attr("status").eq("DECIDING"),
    )
    return _response(
        200,
        {
            "candidate_id": candidate_id,
            "decision": decision,
            "status_reason": status_reason,
        },
    )


def _response(status_code: int, body: Any) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {
            "content-type": "application/json",
            "access-control-allow-origin": REVIEWER_ORIGIN,
        },
        "body": json.dumps(body, default=_json_default),
    }


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    raise TypeError(f"cannot serialize {type(value).__name__}")
