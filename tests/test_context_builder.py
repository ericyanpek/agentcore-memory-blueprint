import pathlib
import sys
import unittest

from botocore.exceptions import ClientError


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent.context_builder import ContextBuilder  # noqa: E402


class FakeMemory:
    def __init__(self) -> None:
        self.calls = []

    def retrieve_memory_records(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "memoryRecordSummaries": [
                {
                    "memoryRecordId": "mem-123",
                    "namespaces": [kwargs["namespace"]],
                    "score": 0.91,
                    "content": {"text": "remembered context"},
                }
            ]
        }


class FakeKnowledgeBase:
    def retrieve(self, **kwargs):
        return {"retrievalResults": [{"content": "official definition"}]}


class ContextBuilderTests(unittest.TestCase):
    def test_keeps_sources_separate_and_scoped(self) -> None:
        memory = FakeMemory()
        builder = ContextBuilder(
            memory_client=memory,
            knowledge_base_client=FakeKnowledgeBase(),
            personal_memory_id="PersonalMemory-1234567890",
            shared_memory_id="SharedMemory-1234567890",
            knowledge_base_id="KB12345678",
        )
        result = builder.build(
            query="How is revenue calculated?",
            authenticated_subject="alice",
            project_id="analytics-poc",
        )

        self.assertEqual(
            memory.calls[0]["namespace"],
            "/projects/project:analytics-poc/shared/",
        )
        self.assertEqual(
            memory.calls[1]["namespace"],
            "/users/user:alice/preferences/",
        )
        self.assertEqual(
            memory.calls[0]["searchCriteria"]["metadataFilters"][1]["right"],
            {"metadataValue": {"stringValue": "approved"}},
        )
        prompt = result.as_prompt_context()
        self.assertEqual(prompt["precedence"][0], "authoritative_documents")
        self.assertEqual(
            prompt["shared_project_memory"][0]["citation"][
                "memory_record_id"
            ],
            "mem-123",
        )
        self.assertNotEqual(
            prompt["shared_project_memory"],
            prompt["personal_preferences"],
        )

    def test_memory_failure_degrades_to_empty_context(self) -> None:
        class FailingMemory:
            def retrieve_memory_records(self, **_kwargs):
                raise ClientError(
                    {
                        "Error": {
                            "Code": "ServiceException",
                            "Message": "temporary",
                        }
                    },
                    "RetrieveMemoryRecords",
                )

        builder = ContextBuilder(
            memory_client=FailingMemory(),
            knowledge_base_client=FakeKnowledgeBase(),
            personal_memory_id="PersonalMemory-1234567890",
            shared_memory_id="SharedMemory-1234567890",
            knowledge_base_id="KB12345678",
        )
        result = builder.build(
            query="How is revenue calculated?",
            authenticated_subject="alice",
            project_id="analytics-poc",
        )
        self.assertEqual(result.shared_project_memory, [])
        self.assertEqual(result.personal_preferences, [])


if __name__ == "__main__":
    unittest.main()
