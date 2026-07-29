"""Drive the memory-bridge MCP server over stdio as two different users.

Proves the property that matters for a shared cloud memory: the desktop client
cannot reach another user's memory or write shared memory, and the boundary is
enforced by AWS rather than by the bridge trusting its own inputs.

Speaks raw MCP JSON-RPC over the server's stdin/stdout, so it exercises exactly
what Claude Code or Codex would exercise.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import secrets
import string
import subprocess
import sys
from typing import Any

import boto3


BRIDGE_DIR = pathlib.Path(__file__).resolve().parent
USERS = {
    "alice": "memory-desktop-alice@example.com",
    "bob": "memory-desktop-bob@example.com",
}
# Mirrors server.CATEGORIES. Duplicated rather than imported so this validator
# stays a standalone client that drives the bridge over the real MCP protocol.
CATEGORIES = ("fact", "decision", "constraint", "incident", "procedure_hint")


class Bridge:
    """Minimal MCP stdio client."""

    def __init__(self, python: str, env: dict[str, str]) -> None:
        self.process = subprocess.Popen(
            [python, str(BRIDGE_DIR / "server.py")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=str(BRIDGE_DIR),
            env={**os.environ, **env},
        )
        self._id = 0
        self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "bridge-validator", "version": "1.0"},
            },
        )
        self._notify("notifications/initialized")

    def _send(self, message: dict[str, Any]) -> None:
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()

    def _notify(self, method: str) -> None:
        self._send({"jsonrpc": "2.0", "method": method})

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._id += 1
        self._send(
            {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}
        )
        while True:
            line = self.process.stdout.readline()
            if not line:
                stderr = self.process.stderr.read()
                raise RuntimeError(f"bridge exited: {stderr[:600]}")
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if message.get("id") == self._id:
                if "error" in message:
                    raise RuntimeError(f"{method} failed: {message['error']}")
                return message["result"]

    def tools(self) -> list[str]:
        return [tool["name"] for tool in self._request("tools/list", {})["tools"]]

    def tool_specs(self) -> dict[str, dict[str, Any]]:
        return {
            tool["name"]: tool for tool in self._request("tools/list", {})["tools"]
        }

    def call(self, name: str, **arguments: Any) -> Any:
        result = self._request(
            "tools/call", {"name": name, "arguments": arguments}
        )
        blocks = result.get("content", [])
        text = "".join(block.get("text", "") for block in blocks)
        try:
            return json.loads(text)
        except ValueError:
            # A tool that raised surfaces as isError with a plain-text message;
            # normalise it so callers see the same shape as a handled failure.
            return {"ok": False, "error": text, "tool_raised": result.get("isError")}

    def close(self) -> None:
        try:
            self.process.stdin.close()
            self.process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            self.process.kill()


def _cross_user_probe(
    deployment: dict[str, Any],
    identity_pool_id: str,
    provider: str,
    *,
    bob_email: str,
    bob_password: str,
    alice_actor: str,
) -> dict[str, str]:
    """Ask AWS directly whether Bob's own credentials can reach Alice's memory."""
    from botocore.exceptions import ClientError

    region = deployment["region"]
    idp = boto3.client("cognito-idp", region_name=region)
    identity = boto3.client("cognito-identity", region_name=region)
    token = idp.initiate_auth(
        ClientId=deployment["reviewer_client_id"],
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": bob_email, "PASSWORD": bob_password},
    )["AuthenticationResult"]["IdToken"]
    logins = {provider: token}
    identity_id = identity.get_id(
        IdentityPoolId=identity_pool_id, Logins=logins
    )["IdentityId"]
    raw = identity.get_credentials_for_identity(
        IdentityId=identity_id, Logins=logins
    )["Credentials"]
    client = boto3.client(
        "bedrock-agentcore",
        region_name=region,
        aws_access_key_id=raw["AccessKeyId"],
        aws_secret_access_key=raw["SecretKey"],
        aws_session_token=raw["SessionToken"],
    )
    outcome: dict[str, str] = {}
    try:
        client.list_events(
            memoryId=deployment["personal_memory_id"],
            actorId=alice_actor,
            sessionId="desktop-bridge-probe-000000000000000000",
            includePayloads=True,
            maxResults=1,
        )
        outcome["events"] = "ALLOWED"
    except ClientError as error:
        outcome["events"] = error.response["Error"]["Code"]
    try:
        client.retrieve_memory_records(
            memoryId=deployment["personal_memory_id"],
            namespace=f"/users/{alice_actor}/preferences/",
            searchCriteria={"searchQuery": "secret", "topK": 3},
            maxResults=3,
        )
        outcome["namespace"] = "ALLOWED"
    except ClientError as error:
        outcome["namespace"] = error.response["Error"]["Code"]
    return outcome


def _desktop_credentials(
    deployment: dict[str, Any],
    identity_pool_id: str,
    provider: str,
    email: str,
    p_word: str,
) -> dict[str, str]:
    region = deployment["region"]
    token = boto3.client("cognito-idp", region_name=region).initiate_auth(
        ClientId=deployment["reviewer_client_id"],
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": email, "PASSWORD": p_word},
    )["AuthenticationResult"]["IdToken"]
    identity = boto3.client("cognito-identity", region_name=region)
    logins = {provider: token}
    identity_id = identity.get_id(
        IdentityPoolId=identity_pool_id, Logins=logins
    )["IdentityId"]
    raw = identity.get_credentials_for_identity(
        IdentityId=identity_id, Logins=logins
    )["Credentials"]
    return {
        "aws_access_key_id": raw["AccessKeyId"],
        "aws_secret_access_key": raw["SecretKey"],
        "aws_session_token": raw["SessionToken"],
    }


def _evidence_tamper_probe(
    deployment: dict[str, Any],
    identity_pool_id: str,
    provider: str,
    *,
    email: str,
    password: str,
    evidence_ref: str,
) -> dict[str, str]:
    """Evidence is only evidence if its author cannot alter or remove it."""
    from botocore.exceptions import ClientError

    bucket, _, key = evidence_ref.removeprefix("s3://").partition("/")
    client = boto3.client(
        "s3",
        region_name=deployment["region"],
        **_desktop_credentials(
            deployment, identity_pool_id, provider, email, password
        ),
    )
    key, _, query = key.partition("?")
    version_id = query.removeprefix("versionId=") if query else ""
    outcome: dict[str, str] = {}
    outcome["ref_pins_version"] = "yes" if version_id else "no"
    try:
        client.delete_object(Bucket=bucket, Key=key)
        outcome["delete"] = "ALLOWED"
    except ClientError as error:
        outcome["delete"] = error.response["Error"]["Code"]
    # An author CAN re-PUT the same key; what must hold is that the pinned version
    # still returns the original bytes. Checking only delete missed this entirely.
    try:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=b'{"excerpt":"FORGED"}',
            ServerSideEncryption="aws:kms",
        )
        outcome["overwrite_key"] = "ALLOWED"
    except ClientError as error:
        outcome["overwrite_key"] = error.response["Error"]["Code"]
    try:
        client.delete_object(Bucket=bucket, Key=key, VersionId=version_id)
        outcome["delete_pinned_version"] = "ALLOWED"
    except ClientError as error:
        outcome["delete_pinned_version"] = error.response["Error"]["Code"]
    try:
        client.put_object(
            Bucket=bucket,
            Key="evidence/user:someone-else/forged.json",
            Body=b"{}",
            ServerSideEncryption="aws:kms",
        )
        outcome["other_prefix"] = "ALLOWED"
    except ClientError as error:
        outcome["other_prefix"] = error.response["Error"]["Code"]
    return outcome


def reset_password(cognito: Any, user_pool_id: str, email: str) -> str:
    secret = "Aa1!" + "".join(
        secrets.choice(string.ascii_letters + string.digits) for _ in range(20)
    )
    cognito.admin_set_user_password(
        UserPoolId=user_pool_id, Username=email, Password=secret, Permanent=True
    )
    return secret


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--deployment",
        type=pathlib.Path,
        default=pathlib.Path("build/poc-deployment.json"),
    )
    parser.add_argument(
        "--identity-pool-file",
        type=pathlib.Path,
        default=pathlib.Path("build/identity-pool-validation.json"),
    )
    parser.add_argument(
        "--result",
        type=pathlib.Path,
        default=pathlib.Path("build/bridge-validation.json"),
    )
    parser.add_argument("--python", default=str(BRIDGE_DIR / ".venv/bin/python"))
    args = parser.parse_args()

    deployment = json.loads(args.deployment.read_text())
    identity_pool_id = json.loads(args.identity_pool_file.read_text())[
        "identity_pool_id"
    ]
    cognito = boto3.client("cognito-idp", region_name=deployment["region"])
    passwords = {
        name: reset_password(cognito, deployment["reviewer_user_pool_id"], email)
        for name, email in USERS.items()
    }

    provider = (
        f"cognito-idp.{deployment['region']}.amazonaws.com/"
        f"{deployment['reviewer_user_pool_id']}"
    )
    env = {
        "MEMORY_BRIDGE_DEPLOYMENT": str(args.deployment.resolve()),
        "MEMORY_BRIDGE_IDENTITY_POOL_ID": identity_pool_id,
    }
    checks: list[dict[str, Any]] = []

    def record(title: str, expected: str, observed: str, passed: bool) -> None:
        checks.append(
            {
                "title": title,
                "expected": expected,
                "observed": observed,
                "passed": passed,
            }
        )
        print(f"[{'PASS' if passed else 'FAIL'}] {title}\n       {observed}", flush=True)

    # Separate token caches so the two users cannot inherit each other's session.
    alice_env = {**env, "MEMORY_BRIDGE_TOKEN_CACHE": "/tmp/bridge-alice.json"}
    bob_env = {**env, "MEMORY_BRIDGE_TOKEN_CACHE": "/tmp/bridge-bob.json"}
    for path in ("/tmp/bridge-alice.json", "/tmp/bridge-bob.json"):
        pathlib.Path(path).unlink(missing_ok=True)

    alice = Bridge(args.python, alice_env)
    bob = Bridge(args.python, bob_env)
    try:
        exposed = alice.tools()
        writes_shared = any("write_shared" in name for name in exposed)
        record(
            "Tool surface offers no direct shared-memory write",
            "no tool named *write_shared*",
            f"tools={exposed}",
            not writes_shared and "memory_propose_shared" in exposed,
        )

        # The category enum is only useful to a model if its meaning travels with
        # the tool. Asserting the names appear is not enough: a bare tuple of five
        # words is what the model already had, and it could not choose between them.
        propose_spec = alice.tool_specs().get("memory_propose_shared", {})
        described = propose_spec.get("description", "")
        documented = [name for name in CATEGORIES if f"{name} " in described]
        states_exclusions = "Not worth proposing" in described
        record(
            "Proposal tool conveys the category semantics, not just their names",
            "every category defined in the description, plus what not to propose",
            f"defined={len(documented)}/{len(CATEGORIES)} "
            f"exclusions_stated={states_exclusions}",
            len(documented) == len(CATEGORIES) and states_exclusions,
        )

        before = alice.call("memory_whoami")
        record(
            "Tools refuse to act before sign-in",
            "signed_in is false, no identity assumed",
            f"signed_in={before.get('signed_in')}",
            before.get("signed_in") is False,
        )

        blind = alice.call(
            "memory_write_turn", user_message="x", assistant_message="y"
        )
        record(
            "Writing without sign-in is refused",
            "ok=false, no actor inferred",
            f"ok={blind.get('ok')} error={str(blind.get('error'))[:70]}",
            blind.get("ok") is False,
        )

        signed = alice.call(
            "memory_sign_in",
            username=USERS["alice"],
            password=passwords["alice"],
        )
        record(
            "Sign-in derives actor_id from the verified token",
            "actor_id equals user:<sub> from the ID token",
            f"actor_id={signed.get('actor_id')} expires_in={signed.get('credentials_expire_in_seconds')}s",
            signed.get("ok") is True and str(signed.get("actor_id", "")).startswith("user:"),
        )
        alice_actor = signed["actor_id"]

        bob_signed = bob.call(
            "memory_sign_in", username=USERS["bob"], password=passwords["bob"]
        )
        bob_actor = bob_signed["actor_id"]
        record(
            "Two clients get two distinct identities from one shared IAM role",
            "different actor_id per signed-in user",
            f"alice={alice_actor} bob={bob_actor}",
            bob_signed.get("ok") is True and alice_actor != bob_actor,
        )

        written = alice.call(
            "memory_write_turn",
            user_message=(
                "My desktop workflow secret code is BRIDGE-9137. Remember it."
            ),
            assistant_message="Noted: BRIDGE-9137.",
            session_key="bridge-validation-alice",
        )
        record(
            "Alice writes a turn into her own memory",
            "ok=true, event written under Alice's actor",
            f"event_id={written.get('event_id')} actor={written.get('actor_id')}",
            written.get("ok") is True
            and written.get("actor_id") == alice_actor,
        )

        alice_search = alice.call("memory_search", query="desktop workflow secret code")
        bob_search = bob.call("memory_search", query="desktop workflow secret code")

        # Searching as Bob and finding nothing proves little: personal extraction
        # is asynchronous, so both namespaces are empty for minutes after the
        # write. Assert the boundary directly instead — Bob's own credentials must
        # be refused on Alice's actor and namespace, which is true immediately.
        cross = _cross_user_probe(
            deployment, identity_pool_id, provider, bob_email=USERS["bob"],
            bob_password=passwords["bob"], alice_actor=alice_actor,
        )
        record(
            "Bob's credentials are refused on Alice's actor and namespace",
            "AccessDeniedException on both Alice's events and Alice's namespace",
            f"read_alice_events={cross['events']} read_alice_namespace={cross['namespace']}",
            cross["events"] == "AccessDeniedException"
            and cross["namespace"] == "AccessDeniedException",
        )
        record(
            "Bob's search returns no trace of Alice's content",
            "Alice's secret never appears in Bob's results",
            f"bob_hits={len(bob_search.get('personal_preferences', []))}, "
            f"BRIDGE-9137 present={'BRIDGE-9137' in json.dumps(bob_search)}",
            bob_search.get("ok") is True
            and "BRIDGE-9137" not in json.dumps(bob_search),
        )

        record(
            "Search separates personal from approved shared knowledge",
            "distinct result lists plus an explicit precedence rule",
            f"keys={sorted(k for k in alice_search if k != 'ok')}",
            "personal_preferences" in alice_search
            and "approved_shared_knowledge" in alice_search
            and "precedence" in alice_search,
        )

        shared_visible = alice.call("memory_search", query="churn ledger downgrade")
        record(
            "Approved shared knowledge is readable by any signed-in member",
            "at least one approved shared record returned",
            f"shared_hits={len(shared_visible.get('approved_shared_knowledge', []))} "
            f"error={shared_visible.get('shared_lookup_error')}",
            bool(shared_visible.get("approved_shared_knowledge")),
        )

        bad_category = alice.call(
            "memory_propose_shared",
            statement=(
                "Churn is probably driven by the pricing change but this is a guess."
            ),
            category="rumour",
            evidence_ref="trace://1-bbbb2222-3333444455556666777788/tool/1",
            confidence=0.9,
        )
        out_of_range = alice.call(
            "memory_propose_shared",
            statement=(
                "The curated churn view counts downgrades as churn, inflating rates."
            ),
            category="constraint",
            evidence_ref="trace://1-bbbb2222-3333444455556666777789/tool/2",
            confidence=7.5,
        )
        bad_evidence = alice.call(
            "memory_propose_shared",
            statement=(
                "The curated churn view counts downgrades as churn, which inflates rates."
            ),
            category="constraint",
            evidence_ref="/Users/alice/.claude/transcript.jsonl",
            confidence=0.95,
        )
        record(
            "Proposals validate evidence provenance locally",
            "a local transcript path is refused as evidence",
            f"ok={bad_evidence.get('ok')} error={str(bad_evidence.get('error'))[:80]}",
            bad_evidence.get("ok") is False,
        )
        record(
            "Proposals validate category and confidence range locally",
            "unknown category and out-of-range confidence both refused",
            f"bad_category_ok={bad_category.get('ok')} "
            f"out_of_range_ok={out_of_range.get('ok')}",
            bad_category.get("ok") is False and out_of_range.get("ok") is False,
        )

        well_formed = alice.call(
            "memory_propose_shared",
            statement=(
                "Session-level dedupe must run before cohort aggregation to avoid "
                "double-counting replayed sessions."
            ),
            category="constraint",
            evidence_ref="s3://audit-bucket/traces/2026-07-28/abc123.json",
            confidence=0.93,
        )
        record(
            "A well-formed proposal is accepted for review",
            "PENDING_REVIEW with a candidate id",
            f"ok={well_formed.get('ok')} candidate={well_formed.get('candidate_id')} "
            f"detail={str(well_formed.get('error') or well_formed.get('status'))[:90]}",
            well_formed.get("status") == "PENDING_REVIEW"
            and bool(well_formed.get("candidate_id")),
        )

        # The policy gate accepts the submission (HTTP 202) but marks it
        # ineligible. Reporting PENDING_REVIEW here would tell the user a
        # reviewer will see something that was already rejected.
        restricted = alice.call(
            "memory_propose_shared",
            statement=(
                "Customer ACME churned after their CFO disclosed an internal "
                "budget freeze during a private call."
            ),
            category="fact",
            evidence_ref="s3://audit-bucket/traces/2026-07-28/restricted.json",
            confidence=0.98,
            privacy_classification="restricted",
        )
        record(
            "A policy-rejected proposal is not reported as awaiting review",
            "status reflects REJECTED_POLICY, not PENDING_REVIEW",
            f"status={restricted.get('status')} "
            f"eligible={restricted.get('eligible_for_review')}",
            restricted.get("status") != "PENDING_REVIEW"
            and restricted.get("eligible_for_review") is False,
        )

        captured = alice.call(
            "memory_capture_evidence",
            excerpt=(
                "User: our churn number looks too high.\n"
                "Assistant: the curated view counts downgrades as churn; the "
                "subscription ledger shows true logo churn is lower."
            ),
            description="bridge validation evidence",
        )
        evidence_ref = captured.get("evidence_ref", "")
        record(
            "Evidence capture returns an immutable s3:// reference",
            "s3:// ref under the caller's own prefix, with a content digest",
            f"ok={captured.get('ok')} ref={evidence_ref[:80]} "
            f"sha256={str(captured.get('sha256'))[:12]}",
            captured.get("ok") is True
            and evidence_ref.startswith("s3://")
            and alice_actor in evidence_ref,
        )

        if evidence_ref.startswith("s3://"):
            tamper = _evidence_tamper_probe(
                deployment, identity_pool_id, provider,
                email=USERS["alice"], password=passwords["alice"],
                evidence_ref=evidence_ref,
            )
            record(
                "The reviewed evidence version cannot be altered by its author",
                "ref pins a versionId; version deletion denied; no cross-prefix write",
                f"pins_version={tamper['ref_pins_version']} "
                f"delete={tamper['delete']} "
                f"overwrite_key={tamper['overwrite_key']} "
                f"delete_pinned={tamper['delete_pinned_version']} "
                f"other_prefix={tamper['other_prefix']}",
                # Re-PUTting the key is allowed and harmless; what must hold is
                # that the pinned version survives and other prefixes are closed.
                tamper["ref_pins_version"] == "yes"
                and tamper["delete"] != "ALLOWED"
                and tamper["delete_pinned_version"] != "ALLOWED"
                and tamper["other_prefix"] != "ALLOWED",
            )

            proposed = alice.call(
                "memory_propose_shared",
                statement=(
                    "The curated churn view counts a downgrade as churn; measure "
                    "true logo churn from the subscription ledger."
                ),
                category="constraint",
                evidence_ref=evidence_ref,
                confidence=0.94,
            )
            record(
                "Desktop proposal with real evidence reaches the review pipeline",
                "accepted for review, attributed to the signed-in user",
                f"ok={proposed.get('ok')} candidate={proposed.get('candidate_id')} "
                f"detail={str(proposed.get('error') or proposed.get('status'))[:70]}",
                proposed.get("ok") is True,
            )
            if proposed.get("ok"):
                checks[-1]["candidate_id"] = proposed.get("candidate_id")

        queue = bob.call("memory_review_queue")
        record(
            "Non-reviewer is refused the review queue",
            "explicit refusal, not a silently filtered list",
            f"ok={queue.get('ok')} detail={str(queue.get('error') or queue.get('matched'))[:80]}",
            queue.get("ok") is False,
        )
    finally:
        alice.close()
        bob.close()

    passed = sum(1 for check in checks if check["passed"])
    result = {
        "identity_pool_id": identity_pool_id,
        "checks": checks,
        "all_passed": passed == len(checks),
    }
    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(json.dumps(result, indent=2, default=str) + "\n")
    print(f"\n{passed}/{len(checks)} checks passed → {args.result}")
    return 0 if result["all_passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
