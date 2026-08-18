from __future__ import annotations

import hashlib
import json
import logging
import re
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


def fingerprint_query(query: str) -> list[str]:
    """Per-token hashes: enough to measure overlap between two queries, not enough to
    reconstruct either. A query can contain the thing the memory tier exists to protect."""
    tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", query.lower())
        if len(token) > 2
    }
    return sorted(
        hashlib.sha256(token.encode("utf-8")).hexdigest()[:12] for token in tokens
    )


@dataclass(frozen=True)
class RetrievalMetrics:
    query_fingerprint: list[str]
    shared_candidates: int
    shared_top_score: float | None

    @classmethod
    def from_records(
        cls,
        *,
        query: str,
        records: list[dict[str, Any]],
    ) -> "RetrievalMetrics":
        scores = [
            record["score"] for record in records if record.get("score") is not None
        ]
        return cls(
            query_fingerprint=fingerprint_query(query),
            shared_candidates=len(records),
            shared_top_score=max(scores) if scores else None,
        )

    def as_log_record(self) -> dict[str, Any]:
        return {
            "metric": "shared_memory_retrieval",
            "query_fingerprint": self.query_fingerprint,
            "shared_candidates": self.shared_candidates,
            "shared_hit": self.shared_candidates > 0,
            "shared_top_score": self.shared_top_score,
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
        LOGGER.info(
            json.dumps(
                RetrievalMetrics.from_records(query=query, records=shared).as_log_record()
            )
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
