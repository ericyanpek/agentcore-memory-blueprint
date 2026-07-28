from __future__ import annotations

import logging
import os
import re
from typing import Any

import boto3
from bedrock_agentcore.memory.integrations.strands.config import (
    AgentCoreMemoryConfig,
    RetrievalConfig,
)
from bedrock_agentcore.memory.integrations.strands.session_manager import (
    AgentCoreMemorySessionManager,
)
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from botocore.config import Config
from botocore.exceptions import ClientError
from strands import Agent
from strands.models import BedrockModel


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
LOGGER = logging.getLogger("memory-poc-agent")
app = BedrockAgentCoreApp()

REGION = os.environ["AWS_REGION"]
MODEL_ID = os.environ["MODEL_ID"]
PERSONAL_MEMORY_ID = os.environ["PERSONAL_MEMORY_ID"]
SHARED_MEMORY_ID = os.environ["SHARED_MEMORY_ID"]
PROJECT_ID = os.environ["PROJECT_ID"]
ACTOR_ID = re.compile(r"^user:[A-Za-z0-9][A-Za-z0-9_/-]{0,79}$")

AWS_CONFIG = Config(
    retries={"total_max_attempts": 5, "mode": "adaptive"},
    connect_timeout=3,
    read_timeout=30,
)
MEMORY = boto3.client(
    "bedrock-agentcore",
    region_name=REGION,
    config=AWS_CONFIG,
)


def shared_namespace() -> str:
    return f"/projects/project:{PROJECT_ID}/shared/"


def retrieve_shared_context(
    query: str,
) -> tuple[list[str], list[dict[str, Any]]]:
    try:
        response = MEMORY.retrieve_memory_records(
            memoryId=SHARED_MEMORY_ID,
            namespace=shared_namespace(),
            searchCriteria={
                "searchQuery": query,
                "topK": 5,
                "metadataFilters": [
                    {
                        "left": {"metadataKey": "project_id"},
                        "operator": "EQUALS_TO",
                        "right": {
                            "metadataValue": {"stringValue": PROJECT_ID}
                        },
                    },
                    {
                        "left": {"metadataKey": "review_status"},
                        "operator": "EQUALS_TO",
                        "right": {
                            "metadataValue": {"stringValue": "approved"}
                        },
                    },
                ],
            },
            maxResults=5,
        )
    except ClientError as error:
        LOGGER.warning(
            "Shared-memory retrieval failed: %s",
            error.response.get("Error", {}).get("Code", "unknown"),
        )
        return [], []

    texts: list[str] = []
    citations: list[dict[str, Any]] = []
    for record in response.get("memoryRecordSummaries", []):
        text = record.get("content", {}).get("text")
        if text:
            texts.append(text)
        citations.append(
            {
                "memory_record_id": record.get("memoryRecordId"),
                "namespaces": record.get("namespaces", []),
                "score": record.get("score"),
                "memory_strategy_id": record.get("memoryStrategyId"),
            }
        )
    return texts, citations


def build_agent(
    *,
    actor_id: str,
    session_id: str,
    shared_context: list[str],
) -> Agent:
    preferences_namespace = f"/users/{actor_id}/preferences/"
    memory_config = AgentCoreMemoryConfig(
        memory_id=PERSONAL_MEMORY_ID,
        actor_id=actor_id,
        session_id=session_id,
        retrieval_config={
            preferences_namespace: RetrievalConfig(
                top_k=5,
                relevance_score=0.2,
                initialization_query="How does this user prefer responses?",
            )
        },
        default_metadata={
            "project_id": PROJECT_ID,
            "data_class": "conversation",
        },
    )
    session_manager = AgentCoreMemorySessionManager(
        memory_config,
        region_name=REGION,
        boto_client_config=AWS_CONFIG,
    )
    shared_text = (
        "\n".join(f"- {item}" for item in shared_context)
        if shared_context
        else "- No approved project memory was retrieved."
    )
    system_prompt = (
        "You are a concise data-analysis assistant used to test AgentCore "
        "Memory. Use the restored personal conversation and preferences only "
        "for this actor. Approved project memory is shared with all project "
        "members and may inform answers, but do not invent missing details.\n"
        "Approved project memory:\n"
        f"{shared_text}"
    )
    return Agent(
        model=BedrockModel(
            model_id=MODEL_ID,
            max_tokens=512,
            temperature=0.1,
        ),
        session_manager=session_manager,
        system_prompt=system_prompt,
    )


@app.entrypoint
def invoke(payload: dict[str, Any], context: Any) -> dict[str, Any]:
    prompt = str(payload.get("prompt", "")).strip()
    actor_id = str(payload.get("actor_id", "")).strip()
    if not prompt or len(prompt) > 4000:
        raise ValueError("prompt must contain 1-4000 characters")
    if not ACTOR_ID.fullmatch(actor_id):
        raise ValueError("actor_id must be a validated user-scoped identifier")

    session_id = context.session_id
    shared_context, citations = retrieve_shared_context(prompt)
    agent = build_agent(
        actor_id=actor_id,
        session_id=session_id,
        shared_context=shared_context,
    )
    response = agent(prompt)
    text = response.message["content"][0]["text"]
    return {
        "response": text,
        "actor_id": actor_id,
        "session_id": session_id,
        "shared_memory_citations": citations,
    }


if __name__ == "__main__":
    app.run()
