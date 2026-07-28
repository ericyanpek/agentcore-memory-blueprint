from __future__ import annotations

import os
from typing import Any

import boto3
from boto3.dynamodb.conditions import Attr

from blueprint.domain import MemoryCandidate


TABLE = boto3.resource("dynamodb").Table(os.environ["CANDIDATE_TABLE_NAME"])


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    candidate = MemoryCandidate.from_event(event.get("event", event))
    execution_id = event.get("workflow_execution_id", "direct-invocation")
    item = candidate.as_item()
    item["workflow_execution_id"] = execution_id
    try:
        TABLE.put_item(
            Item=item,
            ConditionExpression=Attr("candidate_id").not_exists(),
        )
    except TABLE.meta.client.exceptions.ConditionalCheckFailedException:
        existing = TABLE.get_item(
            Key={"candidate_id": candidate.candidate_id},
            ConsistentRead=True,
        ).get("Item")
        if existing is None:
            raise
        if existing.get("workflow_execution_id") != execution_id:
            return {
                "candidate_id": candidate.candidate_id,
                "project_id": candidate.project_id,
                "eligible": False,
                "status": "DUPLICATE_IGNORED",
            }
        item = existing

    return {
        "candidate_id": candidate.candidate_id,
        "project_id": candidate.project_id,
        "eligible": item["status"] == "PENDING_REVIEW",
        "status": item["status"],
    }
