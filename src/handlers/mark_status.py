from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import boto3


CANDIDATES = boto3.resource("dynamodb").Table(os.environ["CANDIDATE_TABLE_NAME"])
EVENTS = boto3.client("events")
EVENT_BUS_NAME = os.environ["PROJECT_EVENT_BUS_NAME"]


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    status = event["target_status"]
    now = datetime.now(timezone.utc).isoformat()
    values: dict[str, Any] = {
        ":status": status,
        ":updated": now,
    }
    update = "SET #status = :status, updated_at = :updated"
    if event.get("reviewer_id"):
        update += ", reviewer_id = :reviewer"
        values[":reviewer"] = event["reviewer_id"]
    if event.get("shared_memory_record_id"):
        update += ", shared_memory_record_id = :memory_record"
        values[":memory_record"] = event["shared_memory_record_id"]
    # The reviewer's stated reason belongs on the candidate record, not only on the
    # callback row that is consumed and then forgotten. Without it the audit trail records
    # that a decision happened but not on what grounds.
    if event.get("status_reason"):
        update += ", status_reason = :reason"
        values[":reason"] = event["status_reason"]

    CANDIDATES.update_item(
        Key={"candidate_id": event["candidate_id"]},
        UpdateExpression=update,
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues=values,
    )

    if status == "PUBLISHED" and event.get("promotion_hint") in {
        "knowledge_base",
        "skill",
    }:
        EVENTS.put_events(
            Entries=[
                {
                    "EventBusName": EVENT_BUS_NAME,
                    "Source": "demo.memory-governance",
                    "DetailType": "memory.promotion.proposed",
                    "Detail": (
                        '{"candidate_id":"%s","project_id":"%s","target":"%s"}'
                        % (
                            event["candidate_id"],
                            event["project_id"],
                            event["promotion_hint"],
                        )
                    ),
                }
            ]
        )
    return {"candidate_id": event["candidate_id"], "status": status}
