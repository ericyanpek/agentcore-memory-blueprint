"""Localhost dashboard backend for the AgentCore Memory governance POC.

Read-only AgentCore Memory calls run here with the operator's local AWS
credentials. The browser never receives AWS credentials and never reads
DynamoDB; review decisions go straight from the browser to the
Cognito-protected Review API.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


STATIC_ROOT = pathlib.Path(__file__).parent / "static"
ACTOR_ID = re.compile(r"^user:[A-Za-z0-9][A-Za-z0-9_/-]{0,79}$")
SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$")
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
}
AWS_CONFIG = Config(
    retries={"total_max_attempts": 5, "mode": "adaptive"},
    connect_timeout=5,
    read_timeout=30,
)


class DashboardError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def load_deployment(path: pathlib.Path) -> dict[str, Any]:
    config = json.loads(path.read_text())
    required = (
        "region",
        "project_id",
        "personal_memory_id",
        "shared_memory_id",
        "review_api_url",
        "reviewer_user_pool_id",
        "reviewer_client_id",
        "reviewer_group_name",
    )
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise SystemExit(f"deployment file is missing: {', '.join(missing)}")
    return config


def shared_namespace(project_id: str) -> str:
    return f"/projects/project:{project_id}/shared/"


def preferences_namespace(actor_id: str) -> str:
    return f"/users/{actor_id}/preferences/"


def summary_namespace(actor_id: str, session_id: str) -> str:
    return f"/users/{actor_id}/sessions/{session_id}/summary/"


def flatten_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, value in (metadata or {}).items():
        if not isinstance(value, dict):
            flattened[key] = value
            continue
        for typed_key in ("stringValue", "numberValue", "booleanValue"):
            if typed_key in value:
                flattened[key] = value[typed_key]
                break
        else:
            flattened[key] = next(
                (
                    str(item)
                    for item in value.values()
                    if not isinstance(item, dict)
                ),
                "(unsupported value type)",
            )
    return flattened


def summarize_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "memory_record_id": record.get("memoryRecordId"),
        "text": record.get("content", {}).get("text"),
        "namespaces": record.get("namespaces", []),
        "memory_strategy_id": record.get("memoryStrategyId"),
        "score": record.get("score"),
        "created_at": record.get("createdAt"),
        "metadata": flatten_metadata(record.get("metadata", {})),
    }


def parse_turn(payload_entry: dict[str, Any]) -> dict[str, Any] | None:
    conversational = payload_entry.get("conversational")
    if not conversational:
        if "blob" in payload_entry:
            return {"role": "BLOB", "text": "(non-conversational blob payload)"}
        return None

    raw_text = conversational.get("content", {}).get("text", "")
    role = conversational.get("role", "UNKNOWN")
    text = raw_text
    try:
        document = json.loads(raw_text)
    except (TypeError, ValueError):
        return {"role": role, "text": text}

    message = document.get("message") if isinstance(document, dict) else None
    if isinstance(message, dict):
        blocks = [
            block.get("text", "")
            for block in message.get("content", [])
            if isinstance(block, dict) and block.get("text")
        ]
        if blocks:
            text = "\n".join(blocks)
    return {"role": role, "text": text}


def summarize_event(event: dict[str, Any]) -> dict[str, Any]:
    turns = [
        turn
        for turn in (parse_turn(entry) for entry in event.get("payload", []))
        if turn
    ]
    return {
        "event_id": event.get("eventId"),
        "event_timestamp": event.get("eventTimestamp"),
        "actor_id": event.get("actorId"),
        "session_id": event.get("sessionId"),
        "turns": turns,
    }


def require_actor(parameters: dict[str, list[str]]) -> str:
    actor_id = (parameters.get("actor_id") or [""])[0].strip()
    if not ACTOR_ID.fullmatch(actor_id):
        raise DashboardError(400, "actor_id must match user:<identifier>")
    return actor_id


def require_session(parameters: dict[str, list[str]]) -> str:
    session_id = (parameters.get("session_id") or [""])[0].strip()
    if not SESSION_ID.fullmatch(session_id):
        raise DashboardError(400, "session_id is required and must be simple")
    return session_id


class MemoryReader:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.client = boto3.client(
            "bedrock-agentcore",
            region_name=config["region"],
            config=AWS_CONFIG,
        )

    def actors(self) -> list[dict[str, Any]]:
        response = self.client.list_actors(
            memoryId=self.config["personal_memory_id"],
            maxResults=100,
        )
        return response.get("actorSummaries", [])

    def sessions(self, actor_id: str) -> list[dict[str, Any]]:
        response = self.client.list_sessions(
            memoryId=self.config["personal_memory_id"],
            actorId=actor_id,
            maxResults=100,
        )
        return response.get("sessionSummaries", [])

    def events(self, actor_id: str, session_id: str) -> list[dict[str, Any]]:
        response = self.client.list_events(
            memoryId=self.config["personal_memory_id"],
            actorId=actor_id,
            sessionId=session_id,
            includePayloads=True,
            maxResults=100,
        )
        events = [summarize_event(event) for event in response.get("events", [])]
        events.sort(key=lambda event: str(event["event_timestamp"]))
        return events

    def records(self, memory_id: str, namespace: str) -> list[dict[str, Any]]:
        response = self.client.list_memory_records(
            memoryId=memory_id,
            namespace=namespace,
            maxResults=100,
        )
        return [
            summarize_record(record)
            for record in response.get("memoryRecordSummaries", [])
        ]

    def search_shared(self, query: str, top_k: int) -> list[dict[str, Any]]:
        project_id = self.config["project_id"]
        response = self.client.retrieve_memory_records(
            memoryId=self.config["shared_memory_id"],
            namespace=shared_namespace(project_id),
            searchCriteria={
                "searchQuery": query,
                "topK": top_k,
                "metadataFilters": [
                    {
                        "left": {"metadataKey": "project_id"},
                        "operator": "EQUALS_TO",
                        "right": {"metadataValue": {"stringValue": project_id}},
                    },
                    {
                        "left": {"metadataKey": "review_status"},
                        "operator": "EQUALS_TO",
                        "right": {"metadataValue": {"stringValue": "approved"}},
                    },
                ],
            },
            maxResults=top_k,
        )
        return [
            summarize_record(record)
            for record in response.get("memoryRecordSummaries", [])
        ]


def route(reader: MemoryReader, path: str, parameters: dict[str, list[str]]) -> Any:
    config = reader.config
    if path == "/api/config":
        return {
            "region": config["region"],
            "project_id": config["project_id"],
            "personal_memory_id": config["personal_memory_id"],
            "shared_memory_id": config["shared_memory_id"],
            "shared_namespace": shared_namespace(config["project_id"]),
            "review_api_url": config["review_api_url"].rstrip("/"),
            "reviewer_user_pool_id": config["reviewer_user_pool_id"],
            "reviewer_client_id": config["reviewer_client_id"],
            "reviewer_group_name": config["reviewer_group_name"],
        }
    if path == "/api/personal/actors":
        return {"actors": reader.actors()}
    if path == "/api/personal/sessions":
        actor_id = require_actor(parameters)
        return {"actor_id": actor_id, "sessions": reader.sessions(actor_id)}
    if path == "/api/personal/events":
        actor_id = require_actor(parameters)
        session_id = require_session(parameters)
        return {
            "actor_id": actor_id,
            "session_id": session_id,
            "events": reader.events(actor_id, session_id),
        }
    if path == "/api/personal/preferences":
        actor_id = require_actor(parameters)
        namespace = preferences_namespace(actor_id)
        return {
            "namespace": namespace,
            "records": reader.records(config["personal_memory_id"], namespace),
        }
    if path == "/api/personal/summary":
        actor_id = require_actor(parameters)
        session_id = require_session(parameters)
        namespace = summary_namespace(actor_id, session_id)
        return {
            "namespace": namespace,
            "records": reader.records(config["personal_memory_id"], namespace),
        }
    if path == "/api/shared/inventory":
        namespace = shared_namespace(config["project_id"])
        return {
            "namespace": namespace,
            "records": reader.records(config["shared_memory_id"], namespace),
        }
    if path == "/api/shared/search":
        query = (parameters.get("q") or [""])[0].strip()
        if not query:
            raise DashboardError(400, "q is required for semantic search")
        if len(query) > 500:
            raise DashboardError(400, "q must be at most 500 characters")
        try:
            top_k = min(max(int((parameters.get("top_k") or ["5"])[0]), 1), 20)
        except ValueError:
            raise DashboardError(400, "top_k must be an integer") from None
        return {
            "namespace": shared_namespace(config["project_id"]),
            "query": query,
            "top_k": top_k,
            "records": reader.search_shared(query, top_k),
        }
    raise DashboardError(404, "unknown dashboard API route")


def build_handler(reader: MemoryReader) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "MemoryGovernanceDashboard/1.0"

        def do_GET(self) -> None:  # noqa: N802 - stdlib contract
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                self._serve_api(parsed.path, parse_qs(parsed.query))
            else:
                self._serve_static(parsed.path)

        def _serve_api(self, path: str, parameters: dict[str, list[str]]) -> None:
            try:
                self._send_json(200, route(reader, path, parameters))
            except DashboardError as error:
                self._send_json(error.status_code, {"message": error.message})
            except ClientError as error:
                code = error.response.get("Error", {}).get("Code", "ClientError")
                self._send_json(502, {"message": f"AWS call failed: {code}"})
            except BotoCoreError as error:
                self._send_json(502, {"message": f"AWS call failed: {error}"})

        def _serve_static(self, path: str) -> None:
            relative = "index.html" if path in ("/", "") else path.lstrip("/")
            target = (STATIC_ROOT / relative).resolve()
            if (
                not target.is_file()
                or STATIC_ROOT.resolve() not in target.parents
            ):
                self._send_json(404, {"message": "not found"})
                return
            body = target.read_bytes()
            self.send_response(200)
            self.send_header(
                "content-type",
                CONTENT_TYPES.get(target.suffix, "application/octet-stream"),
            )
            self.send_header("content-length", str(len(body)))
            self.send_header("cache-control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, status_code: int, body: Any) -> None:
            payload = json.dumps(body, default=str).encode()
            self.send_response(status_code)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(payload)))
            self.send_header("cache-control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: Any) -> None:
            sys.stderr.write(f"dashboard {format % args}\n")

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--deployment",
        type=pathlib.Path,
        default=pathlib.Path("build/poc-deployment.json"),
    )
    parser.add_argument("--port", type=int, default=3000)
    args = parser.parse_args()

    config = load_deployment(args.deployment)
    reader = MemoryReader(config)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), build_handler(reader))
    print(f"Dashboard on http://localhost:{args.port} (127.0.0.1 only)")
    print(f"Personal memory: {config['personal_memory_id']}")
    print(f"Shared memory:   {config['shared_memory_id']}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopping dashboard")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
