#!/usr/bin/env python3
"""Local stdio MCP server bridging a desktop coding agent to AgentCore Memory.

Works with any MCP client (Claude Code, Codex CLI, Claude Desktop). Runs as a
local subprocess, so it needs none of the MCP OAuth machinery that Cognito
cannot currently satisfy (no dynamic client registration, no RFC 8414 metadata,
no loopback redirect).

Three properties make this safe for a shared cloud memory:

1. No tool takes an actor or namespace parameter. Identity comes from the signed
   ID token, so a client cannot ask to be someone else.
2. The AWS credentials are short-lived and tagged with the user's `sub`. A single
   shared IAM role denies cross-user access, so even a bug here cannot leak.
3. There is no tool that writes shared memory. Team knowledge can only be
   *proposed*; it reaches shared memory through the existing EventBridge →
   Step Functions → human review pipeline.

Setup:
    MEMORY_BRIDGE_DEPLOYMENT=build/poc-deployment.json
    MEMORY_BRIDGE_IDENTITY_POOL_ID=us-east-1:...
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any

from botocore.exceptions import ClientError
from mcp.server.mcpserver import MCPServer

from identity import BridgeConfig, IdentityBroker, IdentityError


try:
    CONFIG = BridgeConfig.from_env()
except (IdentityError, KeyError, OSError) as error:
    print(f"memory-bridge configuration error: {error}", file=sys.stderr)
    sys.exit(1)

BROKER = IdentityBroker(CONFIG)
mcp = MCPServer("agentcore-memory-bridge")

CATEGORIES = ("fact", "decision", "constraint", "incident", "procedure_hint")
MIN_STATEMENT, MAX_STATEMENT = 20, 2000


def _fail(message: str) -> dict[str, Any]:
    return {"ok": False, "error": message}


def _aws_error(error: ClientError) -> dict[str, Any]:
    code = error.response.get("Error", {}).get("Code", "UnknownError")
    if code == "AccessDeniedException":
        return _fail(
            "AWS denied this request. Your credentials are scoped to your own "
            "memory only; cross-user and shared-memory writes are blocked by IAM."
        )
    return _fail(f"AWS call failed: {code}")


def _session_id(raw: str | None) -> str:
    # Runtime requires >= 33 characters, and a stable id keeps a conversation's
    # turns in one session so extraction sees the whole thread.
    candidate = (raw or "").strip()
    if len(candidate) >= 33:
        return candidate
    seed = candidate or "default"
    digest = hashlib.sha256(seed.encode()).hexdigest()[:24]
    return f"desktop-bridge-{digest}"


@mcp.tool()
def memory_sign_in(username: str, password: str) -> dict[str, Any]:
    """Sign in to the memory service. Establishes who you are for every later call.

    Your identity is taken from the verified token, not from any parameter, so
    other tools cannot act on another user's behalf.
    """
    try:
        identity = BROKER.sign_in(username, password)
        BROKER.credentials()
    except IdentityError as error:
        return _fail(str(error))
    except ClientError as error:
        return _aws_error(error)
    return {
        "ok": True,
        "signed_in_as": identity["email"] or identity["subject"],
        "actor_id": identity["actor_id"],
        "groups": identity["groups"],
        "credentials_expire_in_seconds": BROKER.credentials_expire_in(),
        "note": (
            "AWS credentials are short-lived and refresh automatically. "
            "They permit only your own memory plus approved shared memory."
        ),
    }


@mcp.tool()
def memory_sign_out() -> dict[str, Any]:
    """Sign out and discard the cached session and AWS credentials."""
    BROKER.sign_out()
    return {"ok": True, "signed_out": True}


@mcp.tool()
def memory_whoami() -> dict[str, Any]:
    """Show the identity and permissions currently in effect."""
    if not BROKER.signed_in:
        return {"ok": True, "signed_in": False, "hint": "call memory_sign_in first"}
    try:
        claims = BROKER.claims()
        BROKER.credentials()
    except IdentityError as error:
        return _fail(str(error))
    except ClientError as error:
        return _aws_error(error)
    return {
        "ok": True,
        "signed_in": True,
        "actor_id": BROKER.actor_id(),
        "email": claims.get("email"),
        "groups": claims.get("cognito:groups", []),
        "personal_namespace": BROKER.preferences_namespace(),
        "shared_namespace": CONFIG.shared_namespace,
        "credentials_expire_in_seconds": BROKER.credentials_expire_in(),
        "can_write_shared_memory": False,
    }


@mcp.tool()
def memory_write_turn(
    user_message: str,
    assistant_message: str,
    session_key: str | None = None,
) -> dict[str, Any]:
    """Record one conversation turn in your own short-term memory.

    Triggers asynchronous extraction of durable personal preferences. Writes only
    ever land under your own actor; IAM rejects anything else.
    """
    if not user_message.strip() and not assistant_message.strip():
        return _fail("at least one of user_message or assistant_message is required")
    session_id = _session_id(session_key)
    payload = []
    for role, text in (("USER", user_message), ("ASSISTANT", assistant_message)):
        if text.strip():
            payload.append(
                {"conversational": {"role": role, "content": {"text": text}}}
            )
    try:
        client = BROKER.memory_client()
        actor_id = BROKER.actor_id()
        response = client.create_event(
            memoryId=CONFIG.personal_memory_id,
            actorId=actor_id,
            sessionId=session_id,
            eventTimestamp=datetime.now(timezone.utc),
            payload=payload,
        )
    except IdentityError as error:
        return _fail(str(error))
    except ClientError as error:
        return _aws_error(error)
    return {
        "ok": True,
        "actor_id": actor_id,
        "session_id": session_id,
        "event_id": response.get("event", {}).get("eventId"),
        "turns_written": len(payload),
    }


@mcp.tool()
def memory_search(query: str, top_k: int = 5) -> dict[str, Any]:
    """Search your personal memory and the team's approved shared memory.

    Results are kept in separate lists on purpose: personal preferences are
    yours alone, while shared knowledge has been human-reviewed and applies to
    the whole project. Prefer shared knowledge when the two conflict, and treat
    live data or authoritative docs as outranking both.
    """
    if not query.strip():
        return _fail("query is required")
    top_k = max(1, min(int(top_k), 20))
    try:
        client = BROKER.memory_client()
        personal = _summarize(
            client.retrieve_memory_records(
                memoryId=CONFIG.personal_memory_id,
                namespace=BROKER.preferences_namespace(),
                searchCriteria={"searchQuery": query, "topK": top_k},
                maxResults=top_k,
            ).get("memoryRecordSummaries", [])
        )
    except IdentityError as error:
        return _fail(str(error))
    except ClientError as error:
        return _aws_error(error)

    shared: list[dict[str, Any]] = []
    shared_error: str | None = None
    try:
        shared = _summarize(
            client.retrieve_memory_records(
                memoryId=CONFIG.shared_memory_id,
                namespace=CONFIG.shared_namespace,
                searchCriteria={
                    "searchQuery": query,
                    "topK": top_k,
                    "metadataFilters": [
                        {
                            "left": {"metadataKey": "project_id"},
                            "operator": "EQUALS_TO",
                            "right": {
                                "metadataValue": {"stringValue": CONFIG.project_id}
                            },
                        },
                        {
                            "left": {"metadataKey": "review_status"},
                            "operator": "EQUALS_TO",
                            "right": {"metadataValue": {"stringValue": "approved"}},
                        },
                    ],
                },
                maxResults=top_k,
            ).get("memoryRecordSummaries", [])
        )
    except ClientError as error:
        shared_error = error.response.get("Error", {}).get("Code", "UnknownError")

    return {
        "ok": True,
        "query": query,
        "personal_preferences": personal,
        "approved_shared_knowledge": shared,
        "shared_lookup_error": shared_error,
        "precedence": (
            "live data and authoritative docs > approved shared knowledge > "
            "personal preferences > model inference"
        ),
    }


@mcp.tool()
def memory_capture_evidence(excerpt: str, description: str = "") -> dict[str, Any]:
    """Store a conversation excerpt as immutable evidence and return its s3:// ref.

    A reviewer approving a claim needs to see what was actually said. A local
    transcript path cannot serve that purpose because it can be edited or deleted
    after approval, so this uploads the excerpt to an append-only audit bucket
    under your own prefix and returns a reference plus a SHA-256 digest.
    """
    excerpt = excerpt.strip()
    if not 20 <= len(excerpt) <= 100_000:
        return _fail("excerpt must contain 20-100000 characters")
    if not CONFIG.evidence_bucket:
        return _fail(
            "no evidence bucket is configured; redeploy the stack and refresh "
            "build/poc-deployment.json"
        )
    digest = hashlib.sha256(excerpt.encode()).hexdigest()
    try:
        actor_id = BROKER.actor_id()
        stamp = datetime.now(timezone.utc)
        key = (
            f"evidence/{actor_id}/{stamp:%Y/%m/%d}/{stamp:%H%M%S}-{digest[:12]}.json"
        )
        body = json.dumps(
            {
                "captured_at": stamp.isoformat(),
                "proposer_actor_id": actor_id,
                "project_id": CONFIG.project_id,
                "description": description,
                "sha256": digest,
                "excerpt": excerpt,
            },
            ensure_ascii=False,
            indent=2,
        ).encode()
        stored = BROKER.s3_client().put_object(
            Bucket=CONFIG.evidence_bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
            ServerSideEncryption="aws:kms",
        )
    except IdentityError as error:
        return _fail(str(error))
    except ClientError as error:
        return _aws_error(error)
    # The reference pins a versionId. Nothing stops the author from re-PUTting the
    # same key, and a bare s3://bucket/key would then resolve to the newer object,
    # letting a proposer swap the evidence behind an approval. Deleting a version
    # is denied by the bucket policy, so a pinned version cannot be altered.
    version_id = stored.get("VersionId")
    reference = f"s3://{CONFIG.evidence_bucket}/{key}"
    if version_id:
        reference = f"{reference}?versionId={version_id}"
    return {
        "ok": True,
        "evidence_ref": reference,
        "sha256": digest,
        "version_id": version_id,
        "note": (
            "Pass this evidence_ref to memory_propose_shared. It pins an "
            "immutable object version, so the reviewer sees exactly this content "
            "even if the same key is written again."
        ),
    }


@mcp.tool()
def memory_propose_shared(
    statement: str,
    category: str,
    evidence_ref: str,
    confidence: float,
    privacy_classification: str = "internal",
) -> dict[str, Any]:
    """Propose a finding as team shared knowledge. Requires human review.

    This does NOT write shared memory. It emits a candidate that a project
    reviewer must approve; policy rejects restricted content and confidence
    below 0.70 before any reviewer sees it.

    Propose only what a *different* project member would need and could act on
    without this conversation for context. Worth proposing: a metric-definition
    trap, a constraint the data imposes, a confirmed root cause, a procedure that
    proved correct. Not worth proposing: your own formatting or tooling
    preferences (those belong in personal memory, written automatically), details
    specific to one task, restated documentation, and anything you have not
    verified — an unverified guess that reaches shared memory misleads everyone
    who retrieves it later.

    `category` selects the kind of knowledge, and reviewers filter on it:
      fact           an observation about the system or data that holds
                     independently of any one task
      decision       a choice the team made, plus what it rules out
      constraint     a hard limit or definitional trap that will silently
                     produce wrong answers if violated
      incident       something that went wrong, confirmed, with its cause
      procedure_hint a reusable operational step worth repeating

    `confidence` is your own assessment, and below 0.70 the candidate is dropped
    before review — so do not inflate it to force a submission through, and do not
    propose at all if you are guessing.

    `privacy_classification` must be `restricted` if the statement contains
    customer-identifying detail, credentials, or anything covered by an NDA. That
    stops it before a reviewer sees it, which is the intended outcome: shared
    memory is readable by every project member.

    `evidence_ref` must point at an immutable record (`trace://`, `s3://`,
    `log://`) — a local transcript path is not acceptable evidence because it can
    be edited after the fact. Call `memory_capture_evidence` first to turn a
    conversation excerpt into a version-pinned `s3://` reference.
    """
    statement = statement.strip()
    if not MIN_STATEMENT <= len(statement) <= MAX_STATEMENT:
        return _fail(
            f"statement must be {MIN_STATEMENT}-{MAX_STATEMENT} characters"
        )
    if category not in CATEGORIES:
        return _fail(f"category must be one of {', '.join(CATEGORIES)}")
    if not evidence_ref.startswith(("trace://", "s3://", "log://")):
        return _fail(
            "evidence_ref must start with trace://, s3://, or log:// so the "
            "claim stays auditable"
        )
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        return _fail("confidence must be a number between 0 and 1")
    if not 0 <= confidence <= 1:
        return _fail("confidence must be between 0 and 1")

    candidate_id = f"cand-desktop-{uuid.uuid4().hex[:12]}"
    try:
        actor_id = BROKER.actor_id()
        # EventBridge PutEvents is not part of the desktop credential scope, so
        # the proposal goes through the reviewer API with the user's ID token.
        status, body = _review_api(
            "/proposals",
            method="POST",
            payload={
                "candidate_id": candidate_id,
                "statement": statement,
                "category": category,
                "evidence_ref": evidence_ref,
                "confidence": confidence,
                "privacy_classification": privacy_classification,
                "proposer_actor_id": actor_id,
            },
        )
    except IdentityError as error:
        return _fail(str(error))
    if status in (403, 404):
        # API Gateway answers an undeployed path with a misleading SigV4-flavoured
        # 403, so surface the real situation instead of the raw message.
        return _fail(
            "The review API has no POST /proposals route deployed, so desktop "
            "clients cannot submit proposals yet. Your submission was validated "
            "locally but not accepted anywhere. Until that route exists, a "
            "project maintainer must emit the candidate event. "
            f"(HTTP {status})"
        )
    if status >= 400:
        return _fail(f"proposal rejected (HTTP {status}): {body}")
    # Report what the policy gate actually decided. Claiming PENDING_REVIEW for
    # every accepted submission would tell the user a restricted or low-confidence
    # statement is awaiting review when it was already rejected and no reviewer
    # will ever see it.
    eligible = bool(body.get("eligible_for_review")) if isinstance(body, dict) else False
    return {
        "ok": True,
        "candidate_id": candidate_id,
        "status": "PENDING_REVIEW" if eligible else "REJECTED_POLICY",
        "eligible_for_review": eligible,
        "proposer": actor_id,
        "note": (
            "Submitted for human review. It becomes shared knowledge only after "
            "a project reviewer approves it."
            if eligible
            else "Rejected by policy before reaching a reviewer: restricted "
            "classification or confidence below the 0.70 threshold."
        ),
    }


@mcp.tool()
def memory_review_queue(status: str | None = None) -> dict[str, Any]:
    """List shared-memory candidates. Requires project reviewer group membership.

    Non-reviewers get a clear 403 from the API rather than a filtered view.
    """
    path = "/reviews"
    if status:
        path += f"?status={urllib.parse.quote(status)}"
    try:
        code, body = _review_api(path)
    except IdentityError as error:
        return _fail(str(error))
    if code == 403:
        return _fail(
            "You are not in the project reviewer group, so you cannot read the "
            "review queue."
        )
    if code >= 400:
        return _fail(f"review API returned HTTP {code}: {body}")
    return {"ok": True, **body}


@mcp.tool()
def memory_review_decide(
    candidate_id: str, decision: str, status_reason: str
) -> dict[str, Any]:
    """Approve or reject a candidate. Requires project reviewer group membership.

    Approval publishes the reviewed text verbatim to shared memory through the
    review workflow. A decision cannot be replayed.

    `status_reason` is required and is stored on the audit record: state why the claim
    is sound (or why it is not), so a later reader knows the grounds and not merely
    that someone signed off. AgentCore's own approval API requires the same field.
    """
    decision = decision.strip().upper()
    if decision not in {"APPROVED", "REJECTED"}:
        return _fail("decision must be APPROVED or REJECTED")
    status_reason = status_reason.strip()
    if not 10 <= len(status_reason) <= 500:
        return _fail("status_reason is required and must be 10-500 characters")
    try:
        code, body = _review_api(
            f"/reviews/{urllib.parse.quote(candidate_id)}",
            method="POST",
            payload={"decision": decision, "status_reason": status_reason},
        )
    except IdentityError as error:
        return _fail(str(error))
    if code == 403:
        return _fail("You are not in the project reviewer group.")
    if code == 409:
        return _fail("This candidate was already decided; decisions cannot be replayed.")
    if code >= 400:
        return _fail(f"review API returned HTTP {code}: {body}")
    return {"ok": True, **body}


def _summarize(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "memory_record_id": record.get("memoryRecordId"),
            "text": record.get("content", {}).get("text"),
            "namespaces": record.get("namespaces", []),
            "score": record.get("score"),
            "memory_strategy_id": record.get("memoryStrategyId"),
        }
        for record in records
    ]


def _review_api(
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    request = urllib.request.Request(
        f"{CONFIG.review_api_url}{path}",
        method=method,
        data=json.dumps(payload).encode() if payload else None,
        headers={
            "authorization": BROKER.id_token(),
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        raw = error.read().decode(errors="replace")
        try:
            return error.code, json.loads(raw)
        except ValueError:
            return error.code, raw
    except urllib.error.URLError as error:
        return 599, str(error)


if __name__ == "__main__":
    mcp.run()
