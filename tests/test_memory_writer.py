import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from blueprint.domain import MemoryCandidate  # noqa: E402
from blueprint.memory import (  # noqa: E402
    MemoryWriter,
    SharedMemoryPublishError,
    TransientSharedMemoryPublishError,
)


class FakeClient:
    def __init__(self) -> None:
        self.calls = []

    def create_event(self, **kwargs):
        self.calls.append(kwargs)
        return {"event": {"eventId": "1#abcdef"}}

    def batch_create_memory_records(self, **kwargs):
        self.calls.append(kwargs)
        request_id = kwargs["records"][0]["requestIdentifier"]
        return {
            "successfulRecords": [
                {
                    "requestIdentifier": request_id,
                    "memoryRecordId": "mem-record-123",
                    "status": "SUCCEEDED",
                }
            ],
            "failedRecords": [],
        }


class MemoryWriterTests(unittest.TestCase):
    def test_personal_turn_uses_user_actor(self) -> None:
        client = FakeClient()
        writer = MemoryWriter(client)
        writer.write_personal_turn(
            memory_id="PersonalMemory-1234567890",
            actor_id="user:alice",
            session_id="session-1",
            user_text="Prefer SQL first.",
            assistant_text="Understood.",
            client_token="turn-1",
            project_id="analytics-poc",
        )
        self.assertEqual(client.calls[0]["actorId"], "user:alice")
        self.assertEqual(len(client.calls[0]["payload"]), 2)

    def test_shared_publish_writes_reviewed_record_directly(self) -> None:
        client = FakeClient()
        writer = MemoryWriter(client)
        candidate = MemoryCandidate(
            candidate_id="cand-123",
            project_id="analytics-poc",
            proposer_actor_id="user:bob",
            category="constraint",
            statement="The curated revenue view excludes refunded orders.",
            evidence_ref="trace://example/tool/4",
            confidence=0.95,
            privacy_classification="internal",
            expires_at=None,
            promotion_hint="knowledge_base",
        )
        result = writer.publish_approved_shared_memory(
            memory_id="SharedMemory-1234567890",
            candidate=candidate,
            reviewer_id="reviewer-1",
        )
        call = client.calls[0]
        record = call["records"][0]
        self.assertEqual(
            record["namespaces"],
            ["/projects/project:analytics-poc/shared/"],
        )
        self.assertEqual(record["requestIdentifier"], "cand-123")
        self.assertEqual(
            record["metadata"]["review_status"]["stringValue"],
            "approved",
        )
        self.assertEqual(result["memoryRecordId"], "mem-record-123")

    def test_shared_publish_surfaces_terminal_partial_failure(self) -> None:
        client = FakeClient()
        client.batch_create_memory_records = lambda **_: {
            "successfulRecords": [],
            "failedRecords": [
                {
                    "requestIdentifier": "cand-123",
                    "errorCode": 400,
                    "errorMessage": "invalid metadata",
                }
            ],
        }
        writer = MemoryWriter(client)
        with self.assertRaises(SharedMemoryPublishError):
            writer.publish_approved_shared_memory(
                memory_id="SharedMemory-1234567890",
                candidate=self._candidate(),
                reviewer_id="reviewer-1",
            )

    def test_shared_publish_marks_transient_partial_failure(self) -> None:
        client = FakeClient()
        client.batch_create_memory_records = lambda **_: {
            "successfulRecords": [],
            "failedRecords": [
                {
                    "requestIdentifier": "cand-123",
                    "errorCode": 429,
                    "errorMessage": "throttled",
                }
            ],
        }
        writer = MemoryWriter(client)
        with self.assertRaises(TransientSharedMemoryPublishError):
            writer.publish_approved_shared_memory(
                memory_id="SharedMemory-1234567890",
                candidate=self._candidate(),
                reviewer_id="reviewer-1",
            )

    @staticmethod
    def _candidate() -> MemoryCandidate:
        return MemoryCandidate(
            candidate_id="cand-123",
            project_id="analytics-poc",
            proposer_actor_id="user:bob",
            category="constraint",
            statement="The curated revenue view excludes refunded orders.",
            evidence_ref="trace://example/tool/4",
            confidence=0.95,
            privacy_classification="internal",
            expires_at=None,
            promotion_hint="knowledge_base",
        )


if __name__ == "__main__":
    unittest.main()
