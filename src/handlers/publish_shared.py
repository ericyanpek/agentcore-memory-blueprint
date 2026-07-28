from __future__ import annotations

import os
from typing import Any

import boto3
from botocore.config import Config

from blueprint.domain import MemoryCandidate
from blueprint.memory import MemoryWriter


CANDIDATES = boto3.resource("dynamodb").Table(os.environ["CANDIDATE_TABLE_NAME"])
MEMORY_WRITER = MemoryWriter(
    boto3.client(
        "bedrock-agentcore",
        config=Config(
            retries={"total_max_attempts": 5, "mode": "adaptive"},
            connect_timeout=3,
            read_timeout=15,
        ),
    )
)
SHARED_MEMORY_ID = os.environ["SHARED_MEMORY_ID"]


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    candidate_id = event["candidate_id"]
    item = CANDIDATES.get_item(
        Key={"candidate_id": candidate_id},
        ConsistentRead=True,
    ).get("Item")
    if item is None:
        raise KeyError(f"candidate not found: {candidate_id}")

    candidate = MemoryCandidate(
        candidate_id=item["candidate_id"],
        project_id=item["project_id"],
        proposer_actor_id=item["proposer_actor_id"],
        category=item["category"],
        statement=item["statement"],
        evidence_ref=item["evidence_ref"],
        confidence=int(item["confidence_basis_points"]) / 10_000,
        privacy_classification=item["privacy_classification"],
        expires_at=item.get("expires_at"),
        promotion_hint=item.get("promotion_hint", "none"),
    )
    response = MEMORY_WRITER.publish_approved_shared_memory(
        memory_id=SHARED_MEMORY_ID,
        candidate=candidate,
        reviewer_id=event["reviewer_id"],
    )
    return {
        **event,
        "shared_memory_record_id": response["memoryRecordId"],
        "promotion_hint": candidate.promotion_hint,
    }
