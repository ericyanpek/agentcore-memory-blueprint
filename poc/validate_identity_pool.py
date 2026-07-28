"""Validate the Identity Pool → session tag → IAM isolation path.

Question under test: can a desktop client (Claude Code / Codex) hold AWS
credentials that are *incapable* of touching another user's memory, with the
boundary enforced by IAM rather than by application code?

Design: one shared IAM role for every engineer. Cognito Identity Pool maps the
User Pool `sub` claim to a `userId` principal tag, and the role's policy refers
to `${aws:PrincipalTag/userId}` in `bedrock-agentcore:actorId` and
`bedrock-agentcore:namespace` conditions. No per-user roles.

The script asserts both directions: allowed access must succeed AND forbidden
access must be denied by AWS. A test that only checks denial would pass on a
misconfigured role that can do nothing at all.
"""

from __future__ import annotations

import argparse
import base64
import json
import pathlib
import secrets
import string
import sys
import time
from typing import Any

import boto3
from datetime import datetime, timezone
from botocore.config import Config
from botocore.exceptions import ClientError


AWS_CONFIG = Config(retries={"total_max_attempts": 8, "mode": "adaptive"})
POOL_NAME = "agentcore-memory-desktop-clients"
ROLE_NAME = "agentcore-memory-desktop-client-role"
POLICY_NAME = "agentcore-memory-desktop-client-access"
TAG_KEY = "userId"
USERS = {
    "alice": "memory-desktop-alice@example.com",
    "bob": "memory-desktop-bob@example.com",
}


def now() -> datetime:
    return datetime.now(timezone.utc)


def password() -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "Aa1!" + "".join(secrets.choice(alphabet) for _ in range(20))


def ensure_identity_pool(cognito_identity: Any, provider: str) -> str:
    for page in cognito_identity.get_paginator("list_identity_pools").paginate(
        MaxResults=60
    ):
        for pool in page.get("IdentityPools", []):
            if pool["IdentityPoolName"] == POOL_NAME:
                pool_id = pool["IdentityPoolId"]
                break
        else:
            continue
        break
    else:
        pool_id = cognito_identity.create_identity_pool(
            IdentityPoolName=POOL_NAME,
            AllowUnauthenticatedIdentities=False,
            CognitoIdentityProviders=[
                {
                    "ProviderName": provider,
                    "ClientId": CLIENT_ID,
                    "ServerSideTokenCheck": True,
                }
            ],
        )["IdentityPoolId"]
        print(f"created identity pool {pool_id}")
    cognito_identity.update_identity_pool(
        IdentityPoolId=pool_id,
        IdentityPoolName=POOL_NAME,
        AllowUnauthenticatedIdentities=False,
        CognitoIdentityProviders=[
            {
                "ProviderName": provider,
                "ClientId": CLIENT_ID,
                "ServerSideTokenCheck": True,
            }
        ],
    )
    # The whole isolation model rests on this mapping: the tag value comes from
    # the IdP-verified `sub` claim, never from anything the client supplies.
    cognito_identity.set_principal_tag_attribute_map(
        IdentityPoolId=pool_id,
        IdentityProviderName=provider,
        UseDefaults=False,
        PrincipalTags={TAG_KEY: "sub"},
    )
    return pool_id


def role_policy(
    personal_arn: str,
    shared_arn: str,
    evidence_bucket_arn: str,
    shared_namespace: str,
    memory_key_arn: str,
) -> dict[str, Any]:
    actor = f"user:${{aws:PrincipalTag/{TAG_KEY}}}"
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "OwnShortTermMemoryOnly",
                "Effect": "Allow",
                "Action": [
                    "bedrock-agentcore:CreateEvent",
                    "bedrock-agentcore:ListEvents",
                    "bedrock-agentcore:GetEvent",
                ],
                "Resource": personal_arn,
                "Condition": {"StringEquals": {"bedrock-agentcore:actorId": actor}},
            },
            {
                "Sid": "OwnLongTermMemoryOnly",
                "Effect": "Allow",
                "Action": [
                    "bedrock-agentcore:RetrieveMemoryRecords",
                    "bedrock-agentcore:ListMemoryRecords",
                ],
                "Resource": personal_arn,
                "Condition": {
                    "StringLike": {
                        "bedrock-agentcore:namespace": f"/users/{actor}/*"
                    }
                },
            },
            {
                # Pinned to one project namespace, not `project:*`. A wildcard
                # would let any signed-in user read every project's shared
                # memory, which is the wrong default once a second project
                # exists. Multi-project membership belongs in an IdP claim
                # mapped to its own session tag.
                "Sid": "ReadApprovedSharedMemory",
                "Effect": "Allow",
                "Action": [
                    "bedrock-agentcore:RetrieveMemoryRecords",
                    "bedrock-agentcore:ListMemoryRecords",
                ],
                "Resource": shared_arn,
                "Condition": {
                    "StringEquals": {
                        "bedrock-agentcore:namespace": shared_namespace
                    }
                },
            },
            {
                # The client may add objects under its own prefix and nothing
                # else. It CAN re-PUT the same key, which is why the evidence
                # reference pins a versionId: version deletion is denied by the
                # bucket policy, so the pinned version stays exactly as reviewed.
                "Sid": "AppendOwnEvidenceOnly",
                "Effect": "Allow",
                "Action": ["s3:PutObject"],
                "Resource": f"{evidence_bucket_arn}/evidence/{actor}/*",
            },
            {
                # Scoped to the memory key: `Resource: "*"` would let a stolen
                # desktop credential decrypt ciphertext from every other KMS-
                # protected system in the account.
                "Sid": "DecryptMemory",
                "Effect": "Allow",
                "Action": ["kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"],
                "Resource": memory_key_arn,
            },
        ],
    }


def ensure_role(
    iam: Any,
    pool_id: str,
    personal_arn: str,
    shared_arn: str,
    evidence_bucket_arn: str,
    shared_namespace: str,
    memory_key_arn: str,
) -> str:
    trust = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Federated": "cognito-identity.amazonaws.com"},
                "Action": ["sts:AssumeRoleWithWebIdentity", "sts:TagSession"],
                "Condition": {
                    "StringEquals": {
                        "cognito-identity.amazonaws.com:aud": pool_id
                    },
                    "ForAnyValue:StringLike": {
                        "cognito-identity.amazonaws.com:amr": "authenticated"
                    },
                },
            }
        ],
    }
    try:
        arn = iam.create_role(
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(trust),
            Description="Shared role for desktop coding agents using AgentCore Memory",
            MaxSessionDuration=3600,
        )["Role"]["Arn"]
        print(f"created role {arn}")
    except iam.exceptions.EntityAlreadyExistsException:
        iam.update_assume_role_policy(
            RoleName=ROLE_NAME, PolicyDocument=json.dumps(trust)
        )
        arn = iam.get_role(RoleName=ROLE_NAME)["Role"]["Arn"]
    iam.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName=POLICY_NAME,
        PolicyDocument=json.dumps(
            role_policy(
                personal_arn,
                shared_arn,
                evidence_bucket_arn,
                shared_namespace,
                memory_key_arn,
            )
        ),
    )
    return arn


def ensure_user(cognito_idp: Any, user_pool_id: str, email: str) -> tuple[str, str]:
    try:
        cognito_idp.admin_create_user(
            UserPoolId=user_pool_id,
            Username=email,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
            ],
            MessageAction="SUPPRESS",
        )
    except cognito_idp.exceptions.UsernameExistsException:
        pass
    secret = password()
    cognito_idp.admin_set_user_password(
        UserPoolId=user_pool_id, Username=email, Password=secret, Permanent=True
    )
    auth = cognito_idp.initiate_auth(
        ClientId=CLIENT_ID,
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": email, "PASSWORD": secret},
    )
    id_token = auth["AuthenticationResult"]["IdToken"]
    claims = id_token.split(".")[1]
    sub = json.loads(
        base64.urlsafe_b64decode(claims + "=" * (-len(claims) % 4))
    )["sub"]
    return id_token, sub


def desktop_credentials(
    cognito_identity: Any, *, pool_id: str, provider: str, id_token: str
) -> dict[str, Any]:
    identity_id = cognito_identity.get_id(
        IdentityPoolId=pool_id, Logins={provider: id_token}
    )["IdentityId"]
    return cognito_identity.get_credentials_for_identity(
        IdentityId=identity_id, Logins={provider: id_token}
    )["Credentials"]


def memory_client(credentials: dict[str, Any], region: str) -> Any:
    return boto3.client(
        "bedrock-agentcore",
        region_name=region,
        aws_access_key_id=credentials["AccessKeyId"],
        aws_secret_access_key=credentials["SecretKey"],
        aws_session_token=credentials["SessionToken"],
        config=AWS_CONFIG,
    )


def attempt(label: str, call) -> tuple[bool, str]:
    try:
        call()
        return True, "ALLOWED"
    except ClientError as error:
        return False, error.response["Error"]["Code"]


def main() -> int:
    global CLIENT_ID
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--deployment",
        type=pathlib.Path,
        default=pathlib.Path("build/poc-deployment.json"),
    )
    parser.add_argument(
        "--result",
        type=pathlib.Path,
        default=pathlib.Path("build/identity-pool-validation.json"),
    )
    args = parser.parse_args()
    config = json.loads(args.deployment.read_text())
    region = config["region"]
    account = config["account_id"]
    user_pool_id = config["reviewer_user_pool_id"]
    CLIENT_ID = config["reviewer_client_id"]
    provider = f"cognito-idp.{region}.amazonaws.com/{user_pool_id}"
    personal_id = config["personal_memory_id"]
    shared_id = config["shared_memory_id"]
    personal_arn = f"arn:aws:bedrock-agentcore:{region}:{account}:memory/{personal_id}"
    shared_arn = f"arn:aws:bedrock-agentcore:{region}:{account}:memory/{shared_id}"
    shared_namespace = f"/projects/project:{config['project_id']}/shared/"

    session = boto3.Session(region_name=region)
    cognito_idp = session.client("cognito-idp", config=AWS_CONFIG)
    cognito_identity = session.client("cognito-identity", config=AWS_CONFIG)
    iam = session.client("iam", config=AWS_CONFIG)

    pool_id = ensure_identity_pool(cognito_identity, provider)
    evidence_bucket = config.get("evidence_bucket_name")
    if not evidence_bucket:
        raise SystemExit(
            "deployment file has no evidence_bucket_name; redeploy the stack and "
            "re-run poc/deploy_runtime.py so the bucket name is recorded"
        )
    evidence_bucket_arn = f"arn:aws:s3:::{evidence_bucket}"
    memory_key_arn = boto3.client(
        "bedrock-agentcore-control", region_name=region, config=AWS_CONFIG
    ).get_memory(memoryId=personal_id)["memory"]["encryptionKeyArn"]
    role_arn = ensure_role(
        iam,
        pool_id,
        personal_arn,
        shared_arn,
        evidence_bucket_arn,
        shared_namespace,
        memory_key_arn,
    )
    cognito_identity.set_identity_pool_roles(
        IdentityPoolId=pool_id, Roles={"authenticated": role_arn}
    )
    print(f"identity pool {pool_id} → single shared role {role_arn}")

    identities: dict[str, dict[str, Any]] = {}
    for name, email in USERS.items():
        id_token, sub = ensure_user(cognito_idp, user_pool_id, email)
        identities[name] = {"email": email, "sub": sub, "id_token": id_token}
        print(f"{name}: sub={sub}")

    print("waiting for IAM propagation")
    time.sleep(12)

    checks: list[dict[str, Any]] = []
    alice, bob = identities["alice"], identities["bob"]
    alice_actor = f"user:{alice['sub']}"
    bob_actor = f"user:{bob['sub']}"
    alice_credentials = desktop_credentials(
        cognito_identity, pool_id=pool_id, provider=provider, id_token=alice["id_token"]
    )
    client = memory_client(alice_credentials, region)
    session_id = f"desktop-identity-pool-check-{alice['sub'][:8]}-0001"

    def record(title: str, expected_allow: bool, allowed: bool, detail: str) -> None:
        passed = allowed == expected_allow
        checks.append(
            {
                "title": title,
                "expected": "ALLOW" if expected_allow else "DENY",
                "observed": detail,
                "passed": passed,
            }
        )
        print(f"[{'PASS' if passed else 'FAIL'}] {title} → {detail}")

    allowed, detail = attempt(
        "own write",
        lambda: client.create_event(
            memoryId=personal_id,
            actorId=alice_actor,
            sessionId=session_id,
            eventTimestamp=now(),
            payload=[
                {
                    "conversational": {
                        "role": "USER",
                        "content": {"text": "Identity Pool isolation check."},
                    }
                }
            ],
        ),
    )
    record("Alice writes her own short-term memory", True, allowed, detail)

    allowed, detail = attempt(
        "cross write",
        lambda: client.create_event(
            memoryId=personal_id,
            actorId=bob_actor,
            sessionId=session_id,
            eventTimestamp=now(),
            payload=[
                {
                    "conversational": {
                        "role": "USER",
                        "content": {"text": "Should never be written."},
                    }
                }
            ],
        ),
    )
    record("Alice writes into Bob's actor (impersonation)", False, allowed, detail)

    allowed, detail = attempt(
        "own read",
        lambda: client.list_events(
            memoryId=personal_id,
            actorId=alice_actor,
            sessionId=session_id,
            includePayloads=True,
            maxResults=5,
        ),
    )
    record("Alice reads her own events", True, allowed, detail)

    allowed, detail = attempt(
        "cross read",
        lambda: client.list_events(
            memoryId=personal_id,
            actorId=bob_actor,
            sessionId=session_id,
            includePayloads=True,
            maxResults=5,
        ),
    )
    record("Alice reads Bob's events", False, allowed, detail)

    allowed, detail = attempt(
        "own namespace",
        lambda: client.retrieve_memory_records(
            memoryId=personal_id,
            namespace=f"/users/{alice_actor}/preferences/",
            searchCriteria={"searchQuery": "preference", "topK": 3},
            maxResults=3,
        ),
    )
    record("Alice retrieves her own preference namespace", True, allowed, detail)

    allowed, detail = attempt(
        "cross namespace",
        lambda: client.retrieve_memory_records(
            memoryId=personal_id,
            namespace=f"/users/{bob_actor}/preferences/",
            searchCriteria={"searchQuery": "preference", "topK": 3},
            maxResults=3,
        ),
    )
    record("Alice retrieves Bob's preference namespace", False, allowed, detail)

    allowed, detail = attempt(
        "shared read",
        lambda: client.retrieve_memory_records(
            memoryId=shared_id,
            namespace=shared_namespace,
            searchCriteria={"searchQuery": "churn", "topK": 3},
            maxResults=3,
        ),
    )
    record("Alice reads approved shared project memory", True, allowed, detail)

    allowed, detail = attempt(
        "shared write",
        lambda: client.batch_create_memory_records(
            memoryId=shared_id,
            records=[
                {
                    "requestIdentifier": "desktop-bypass-attempt",
                    "namespaces": [shared_namespace],
                    "content": {
                        "text": "Unreviewed knowledge injected from a desktop client."
                    },
                    "timestamp": now(),
                }
            ],
        ),
    )
    record(
        "Alice writes shared memory directly, bypassing review",
        False,
        allowed,
        detail,
    )

    passed = sum(1 for check in checks if check["passed"])
    result = {
        "identity_pool_id": pool_id,
        "shared_role_arn": role_arn,
        "principal_tag": {TAG_KEY: "sub (IdP-verified claim)"},
        "users": {
            name: {"email": data["email"], "sub": data["sub"]}
            for name, data in identities.items()
        },
        "checks": checks,
        "all_passed": passed == len(checks),
    }
    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(json.dumps(result, indent=2, default=str) + "\n")
    print(f"\n{passed}/{len(checks)} checks passed → {args.result}")
    return 0 if result["all_passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
