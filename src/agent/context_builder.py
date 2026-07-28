from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from botocore.exceptions import ClientError

from blueprint.domain import personal_actor_id, shared_project_namespace


LOGGER = logging.getLogger(__name__)


class MemorySearchClient(Protocol):
    def retrieve_memory_records(self, **kwargs: Any) -> dict[str, Any]:
        ...


class KnowledgeBaseClient(Protocol):
    def retrieve(self, **kwargs: Any) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class ContextBundle:
    authoritative_documents: list[dict[str, Any]]
    shared_project_memory: list[dict[str, Any]]
    personal_preferences: list[dict[str, Any]]

    def as_prompt_context(self) -> dict[str, Any]:
        return {
            "precedence": [
                "authoritative_documents",
                "shared_project_memory",
                "personal_preferences",
            ],
            "authoritative_documents": self.authoritative_documents,
            "shared_project_memory": self.shared_project_memory,
            "personal_preferences": self.personal_preferences,
            "conflict_rule": (
                "A managed document overrides memory. Current tool data overrides all "
                "retrieved context. Personal preferences may change presentation only."
            ),
        }


class ContextBuilder:
    def __init__(
        self,
        *,
        memory_client: MemorySearchClient,
        knowledge_base_client: KnowledgeBaseClient,
        personal_memory_id: str,
        shared_memory_id: str,
        knowledge_base_id: str,
    ) -> None:
        self._memory = memory_client
        self._knowledge_base = knowledge_base_client
        self._personal_memory_id = personal_memory_id
        self._shared_memory_id = shared_memory_id
        self._knowledge_base_id = knowledge_base_id

    def build(
        self,
        *,
        query: str,
        authenticated_subject: str,
        project_id: str,
    ) -> ContextBundle:
        user_actor = personal_actor_id(authenticated_subject)

        documents = self._knowledge_base.retrieve(
            knowledgeBaseId=self._knowledge_base_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {"numberOfResults": 5}
            },
        ).get("retrievalResults", [])
        shared = self._retrieve_memory(
            memory_id=self._shared_memory_id,
            namespace=shared_project_namespace(project_id),
            query=query,
            top_k=5,
            metadata_filters=[
                self._equals_filter("project_id", project_id),
                self._equals_filter("review_status", "approved"),
            ],
        )
        preferences = self._retrieve_memory(
            memory_id=self._personal_memory_id,
            namespace=f"/users/{user_actor}/preferences/",
            query=query,
            top_k=3,
        )
        return ContextBundle(
            authoritative_documents=documents,
            shared_project_memory=shared,
            personal_preferences=preferences,
        )

    def _retrieve_memory(
        self,
        *,
        memory_id: str,
        namespace: str,
        query: str,
        top_k: int,
        metadata_filters: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        search_criteria: dict[str, Any] = {
            "searchQuery": query,
            "topK": top_k,
        }
        if metadata_filters:
            search_criteria["metadataFilters"] = metadata_filters
        try:
            response = self._memory.retrieve_memory_records(
                memoryId=memory_id,
                namespace=namespace,
                searchCriteria=search_criteria,
                maxResults=top_k,
            )
        except ClientError as error:
            LOGGER.warning(
                "Memory retrieval failed for %s (%s); continuing without it",
                namespace,
                error.response.get("Error", {}).get("Code", "unknown"),
            )
            return []
        return [
            self._with_memory_citation(record, memory_id)
            for record in response.get("memoryRecordSummaries", [])
        ]

    @staticmethod
    def _equals_filter(key: str, value: str) -> dict[str, Any]:
        return {
            "left": {"metadataKey": key},
            "operator": "EQUALS_TO",
            "right": {"metadataValue": {"stringValue": value}},
        }

    @staticmethod
    def _with_memory_citation(
        record: dict[str, Any],
        memory_id: str,
    ) -> dict[str, Any]:
        return {
            **record,
            "citation": {
                "source_type": "agentcore_memory",
                "memory_id": memory_id,
                "memory_record_id": record.get("memoryRecordId"),
                "namespaces": record.get("namespaces", []),
                "score": record.get("score"),
                "memory_strategy_id": record.get("memoryStrategyId"),
            },
        }
