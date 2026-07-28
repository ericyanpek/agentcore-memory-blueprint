from __future__ import annotations

import os
import time
from typing import Any

import boto3


CALLBACKS = boto3.resource("dynamodb").Table(os.environ["CALLBACK_TABLE_NAME"])
TOPIC = boto3.client("sns")
TOPIC_ARN = os.environ["REVIEW_TOPIC_ARN"]
REVIEW_API_URL = os.environ["REVIEW_API_URL"]


def handler(event: dict[str, Any], _context: Any) -> dict[str, str]:
    candidate_id = event["candidate_id"]
    CALLBACKS.put_item(
        Item={
            "candidate_id": candidate_id,
            "task_token": event["task_token"],
            "project_id": event["project_id"],
            "created_at_epoch": int(time.time()),
            "expires_at_epoch": int(time.time()) + 7 * 24 * 60 * 60,
            "status": "WAITING",
        }
    )
    TOPIC.publish(
        TopicArn=TOPIC_ARN,
        Subject=f"Shared memory review required: {candidate_id}",
        Message=(
            f"Review candidate {candidate_id} in the reviewer API.\n"
            f"Endpoint: {REVIEW_API_URL}/reviews/{candidate_id}\n"
            "The approval callback token is intentionally not included."
        ),
    )
    return {"candidate_id": candidate_id, "status": "WAITING"}

