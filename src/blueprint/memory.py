from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from .domain import MemoryCandidate, shared_project_namespace


class AgentCoreDataClient(Protocol):
    def create_event(self, **kwargs: Any) -> dict[str, Any]:
        ...

    def batch_create_memory_records(self, **kwargs: Any) -> dict[str, Any]:
        ...


class SharedMemoryPublishError(RuntimeError):
    pass


class TransientSharedMemoryPublishError(SharedMemoryPublishError):
    pass


class MemoryWriter:
    def __init__(self, client: AgentCoreDataClient) -> None:
        self._client = client

    def write_personal_turn(
        self,
        *,
        memory_id: str,
        actor_id: str,
        session_id: str,
        user_text: str,
        assistant_text: str,
        client_token: str,
        project_id: str,
    ) -> dict[str, Any]:
        return self._client.create_event(
            memoryId=memory_id,
            actorId=actor_id,
            sessionId=session_id,
            eventTimestamp=datetime.now(timezone.utc),
            clientToken=client_token,
            payload=[
                self._message(user_text, "USER"),
                self._message(assistant_text, "ASSISTANT"),
            ],
            metadata={
                "project_id": {"stringValue": project_id},
                "data_class": {"stringValue": "conversation"},
            },
        )

    def publish_approved_shared_memory(
        self,
        *,
        memory_id: str,
        candidate: MemoryCandidate,
        reviewer_id: str,
    ) -> dict[str, Any]:
        if not reviewer_id:
            raise ValueError("reviewer_id is required for the audit boundary")

        response = self._client.batch_create_memory_records(
            memoryId=memory_id,
            records=[
                {
                    "requestIdentifier": candidate.candidate_id,
                    "content": {"text": candidate.statement},
                    "namespaces": [
                        shared_project_namespace(candidate.project_id)
                    ],
                    "timestamp": datetime.now(timezone.utc),
                    "metadata": {
                        "candidate_id": {
                            "stringValue": candidate.candidate_id
                        },
                        "project_id": {
                            "stringValue": candidate.project_id
                        },
                        "category": {"stringValue": candidate.category},
                        "review_status": {"stringValue": "approved"},
                        "promotion_hint": {
                            "stringValue": candidate.promotion_hint
                        },
                        "privacy_classification": {
                            "stringValue": candidate.privacy_classification
                        },
                    },
                }
            ],
        )
        failed = response.get("failedRecords", [])
        if failed:
            error_codes = {
                int(record.get("errorCode", 0))
                for record in failed
                if str(record.get("errorCode", "")).isdigit()
            }
            error = self._format_batch_failure(candidate.candidate_id, failed)
            if error_codes and error_codes.issubset({429, 500, 502, 503, 504}):
                raise TransientSharedMemoryPublishError(error)
            raise SharedMemoryPublishError(error)

        successful = [
            record
            for record in response.get("successfulRecords", [])
            if record.get("requestIdentifier") == candidate.candidate_id
        ]
        if len(successful) != 1 or not successful[0].get("memoryRecordId"):
            raise SharedMemoryPublishError(
                "BatchCreateMemoryRecords returned no record ID for "
                f"{candidate.candidate_id}"
            )
        return successful[0]

    @staticmethod
    def _format_batch_failure(
        candidate_id: str,
        failed: list[dict[str, Any]],
    ) -> str:
        details = "; ".join(
            f"code={record.get('errorCode', 'unknown')} "
            f"message={record.get('errorMessage', 'unspecified')}"
            for record in failed
        )
        return f"failed to publish shared memory {candidate_id}: {details}"

    @staticmethod
    def _message(text: str, role: str) -> dict[str, Any]:
        if not text.strip():
            raise ValueError("memory message text must not be empty")
        return {
            "conversational": {
                "content": {"text": text},
                "role": role,
            }
        }
