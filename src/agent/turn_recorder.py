from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.config import Config

from blueprint.domain import MemoryCandidate, personal_actor_id
from blueprint.memory import MemoryWriter


# For Strands agents, prefer AgentCoreMemorySessionManager for ordinary
# conversation persistence. This adapter remains useful for sanitized domain
# events and for non-Strands runtimes that do not provide memory lifecycle hooks.
AWS_CONFIG = Config(
    retries={"total_max_attempts": 5, "mode": "adaptive"},
    connect_timeout=3,
    read_timeout=10,
)


@dataclass(frozen=True)
class CompletedTurn:
    project_id: str
    authenticated_subject: str
    session_id: str
    turn_id: str
    trace_id: str
    user_text: str
    assistant_text: str


class TurnRecorder:
    def __init__(
        self,
        *,
        personal_memory_id: str,
        event_bus_name: str,
        memory_client: Any | None = None,
        events_client: Any | None = None,
    ) -> None:
        self._personal_memory_id = personal_memory_id
        self._event_bus_name = event_bus_name
        self._memory_writer = MemoryWriter(
            memory_client or boto3.client("bedrock-agentcore", config=AWS_CONFIG)
        )
        self._events = events_client or boto3.client("events", config=AWS_CONFIG)

    def record(
        self,
        turn: CompletedTurn,
        shared_candidate: MemoryCandidate | None = None,
    ) -> dict[str, Any]:
        actor_id = personal_actor_id(turn.authenticated_subject)
        response = self._memory_writer.write_personal_turn(
            memory_id=self._personal_memory_id,
            actor_id=actor_id,
            session_id=turn.session_id,
            user_text=turn.user_text,
            assistant_text=turn.assistant_text,
            client_token=turn.turn_id,
            project_id=turn.project_id,
        )
        event_id = response["event"]["eventId"]

        entries = [
            {
                "EventBusName": self._event_bus_name,
                "Source": "demo.analytics-agent",
                "DetailType": "conversation.turn.completed",
                "Detail": json.dumps(
                    {
                        "schema_version": "1.0",
                        "project_id": turn.project_id,
                        "actor_id": actor_id,
                        "session_id": turn.session_id,
                        "turn_id": turn.turn_id,
                        "trace_id": turn.trace_id,
                        "personal_memory_event_id": event_id,
                        "shared_candidate_proposed": shared_candidate is not None,
                    }
                ),
            }
        ]
        if shared_candidate is not None:
            entries.append(
                {
                    "EventBusName": self._event_bus_name,
                    "Source": "demo.analytics-agent",
                    "DetailType": "memory.candidate.proposed",
                    "Detail": json.dumps(
                        {
                            **shared_candidate.as_item(),
                            "confidence": shared_candidate.confidence,
                            "schema_version": "1.0",
                        }
                    ),
                }
            )

        result = self._events.put_events(Entries=entries)
        if result.get("FailedEntryCount", 0):
            raise RuntimeError(f"failed to publish domain event: {result['Entries']}")
        return {"memory_event_id": event_id, "domain_event_count": len(entries)}


def from_environment() -> TurnRecorder:
    return TurnRecorder(
        personal_memory_id=os.environ["PERSONAL_MEMORY_ID"],
        event_bus_name=os.environ["PROJECT_EVENT_BUS_NAME"],
    )
