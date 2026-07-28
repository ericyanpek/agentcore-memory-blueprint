"""Accept a shared-memory candidate from an authenticated project member.

Lets a desktop coding agent propose team knowledge without holding permission to
write shared memory. The handler emits the same `memory.candidate.proposed`
EventBridge event the agent runtime uses, so proposals inherit the existing
policy gate, human review, and audit trail rather than a parallel path.

The proposer identity is taken from the Cognito token, never from the request
body: a client that could name its own proposer could attribute a rejected
statement to a colleague.
"""

from __future__ import annotations

import json
import os
from typing import Any

import boto3

from blueprint.domain import MemoryCandidate, ValidationError


EVENTS = boto3.client("events")
EVENT_BUS_NAME = os.environ["EVENT_BUS_NAME"]
PROJECT_ID = os.environ["PROJECT_ID"]
REVIEWER_ORIGIN = os.environ["REVIEWER_ORIGIN"]
EVENT_SOURCE = os.environ.get("EVENT_SOURCE", "demo.analytics-agent")


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    # API Gateway sends these keys with null values rather than omitting them, so
    # a `.get(key, {})` default does not protect the chained access.
    request_context = event.get("requestContext") or {}
    authorizer = request_context.get("authorizer") or {}
    claims = authorizer.get("claims") or {}
    subject = str(claims.get("sub", ""))
    if not subject:
        return _response(403, {"message": "authenticated project member required"})

    try:
        body = json.loads(event.get("body") or "{}")
    except ValueError:
        return _response(400, {"message": "body must be JSON"})
    if not isinstance(body, dict):
        return _response(400, {"message": "body must be a JSON object"})

    detail = {
        "schema_version": "1.0",
        "candidate_id": str(body.get("candidate_id", "")),
        "project_id": PROJECT_ID,
        "proposer_actor_id": f"user:{subject}",
        "category": str(body.get("category", "")),
        "statement": str(body.get("statement", "")),
        "evidence_ref": str(body.get("evidence_ref", "")),
        "confidence": body.get("confidence"),
        "privacy_classification": str(
            body.get("privacy_classification", "internal")
        ),
        "expires_at": body.get("expires_at"),
        "promotion_hint": str(body.get("promotion_hint", "none")),
    }

    # Validate here so a malformed proposal fails synchronously with a usable
    # message instead of dying inside the workflow.
    try:
        candidate = MemoryCandidate.from_event({"detail": detail})
    except (ValidationError, TypeError, ValueError) as error:
        return _response(400, {"message": str(error)})

    response = EVENTS.put_events(
        Entries=[
            {
                "EventBusName": EVENT_BUS_NAME,
                "Source": EVENT_SOURCE,
                "DetailType": "memory.candidate.proposed",
                "Detail": json.dumps(detail),
            }
        ]
    )
    if response.get("FailedEntryCount", 0):
        return _response(502, {"message": "candidate event could not be published"})

    return _response(
        202,
        {
            "candidate_id": candidate.candidate_id,
            "project_id": candidate.project_id,
            "proposer_actor_id": candidate.proposer_actor_id,
            # A candidate that fails the policy gate never reaches a reviewer, so
            # the caller must not be told review is guaranteed.
            "status": "SUBMITTED",
            "eligible_for_review": candidate.eligible_for_review,
        },
    )


def _response(status_code: int, body: Any) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {
            "content-type": "application/json",
            "access-control-allow-origin": REVIEWER_ORIGIN,
        },
        "body": json.dumps(body),
    }
