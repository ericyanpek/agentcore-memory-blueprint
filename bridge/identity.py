"""Per-user AWS credentials for a desktop coding agent.

The desktop client never holds long-lived AWS keys and never declares who it is.
The user signs in to the identity provider; the Cognito Identity Pool maps the
IdP-verified `sub` claim to an `aws:PrincipalTag/userId` session tag; a single
shared IAM role then scopes AgentCore Memory access with that tag. Isolation is
therefore enforced by IAM, not by this process behaving well.

Validated against real AWS by `poc/validate_identity_pool.py`: credentials
minted for one user are denied on another user's actor and namespace, and cannot
write shared memory at all.
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import stat
import threading
import time
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


AWS_CONFIG = Config(retries={"total_max_attempts": 5, "mode": "adaptive"})
# Refresh early: a credential that expires mid-tool-call surfaces to the user as
# an opaque AccessDenied.
REFRESH_MARGIN_SECONDS = 600
TOKEN_CACHE = pathlib.Path(
    os.environ.get(
        "MEMORY_BRIDGE_TOKEN_CACHE",
        pathlib.Path.home() / ".agentcore-memory-bridge" / "session.json",
    )
)


class IdentityError(RuntimeError):
    pass


def _claims(token: str) -> dict[str, Any]:
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


@dataclass(frozen=True)
class BridgeConfig:
    region: str
    user_pool_id: str
    client_id: str
    identity_pool_id: str
    personal_memory_id: str
    shared_memory_id: str
    project_id: str
    review_api_url: str
    evidence_bucket: str | None

    @property
    def provider(self) -> str:
        return f"cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}"

    @property
    def shared_namespace(self) -> str:
        return f"/projects/project:{self.project_id}/shared/"

    @classmethod
    def from_env(cls) -> "BridgeConfig":
        deployment = os.environ.get("MEMORY_BRIDGE_DEPLOYMENT")
        values: dict[str, Any] = {}
        if deployment:
            values = json.loads(pathlib.Path(deployment).read_text())
        identity_pool = os.environ.get("MEMORY_BRIDGE_IDENTITY_POOL_ID")
        if not identity_pool:
            validation = os.environ.get("MEMORY_BRIDGE_IDENTITY_POOL_FILE")
            if validation and pathlib.Path(validation).is_file():
                identity_pool = json.loads(
                    pathlib.Path(validation).read_text()
                ).get("identity_pool_id")
        missing = [
            name
            for name, value in (
                ("MEMORY_BRIDGE_DEPLOYMENT", deployment),
                ("MEMORY_BRIDGE_IDENTITY_POOL_ID", identity_pool),
            )
            if not value
        ]
        if missing:
            raise IdentityError(f"missing configuration: {', '.join(missing)}")
        return cls(
            region=values["region"],
            user_pool_id=values["reviewer_user_pool_id"],
            client_id=values["reviewer_client_id"],
            identity_pool_id=str(identity_pool),
            personal_memory_id=values["personal_memory_id"],
            shared_memory_id=values["shared_memory_id"],
            project_id=values["project_id"],
            review_api_url=values["review_api_url"].rstrip("/"),
            evidence_bucket=values.get("evidence_bucket_name"),
        )


class IdentityBroker:
    """Signs the user in, then keeps short-lived AWS credentials fresh.

    Only this class knows the user's identity, and it learns it from the ID
    token rather than from configuration.
    """

    def __init__(self, config: BridgeConfig) -> None:
        self.config = config
        self._lock = threading.Lock()
        self._tokens: dict[str, Any] = {}
        self._credentials: dict[str, Any] | None = None
        self._credentials_expiry = 0.0
        self._idp = boto3.client(
            "cognito-idp", region_name=config.region, config=AWS_CONFIG
        )
        self._identity = boto3.client(
            "cognito-identity", region_name=config.region, config=AWS_CONFIG
        )
        self._load_cache()

    # ---------- sign-in ----------

    def sign_in(self, username: str, password: str) -> dict[str, Any]:
        try:
            auth = self._idp.initiate_auth(
                ClientId=self.config.client_id,
                AuthFlow="USER_PASSWORD_AUTH",
                AuthParameters={"USERNAME": username, "PASSWORD": password},
            )
        except ClientError as error:
            raise IdentityError(
                f"sign-in failed: {error.response['Error']['Code']}"
            ) from error
        result = auth.get("AuthenticationResult")
        if not result:
            raise IdentityError(
                f"sign-in requires an additional challenge: {auth.get('ChallengeName')}"
            )
        with self._lock:
            self._tokens = {
                "id_token": result["IdToken"],
                "refresh_token": result.get("RefreshToken"),
                "obtained_at": time.time(),
            }
            self._credentials = None
            self._credentials_expiry = 0.0
            self._save_cache()
        claims = _claims(result["IdToken"])
        return {
            "actor_id": self.actor_id(),
            "subject": claims["sub"],
            "email": claims.get("email"),
            "groups": claims.get("cognito:groups", []),
        }

    def sign_out(self) -> None:
        with self._lock:
            self._tokens = {}
            self._credentials = None
            self._credentials_expiry = 0.0
            TOKEN_CACHE.unlink(missing_ok=True)

    @property
    def signed_in(self) -> bool:
        return bool(self._tokens.get("id_token"))

    def actor_id(self) -> str:
        """Actor identity, derived from the IdP-verified `sub` claim."""
        token = self._tokens.get("id_token")
        if not token:
            raise IdentityError("not signed in; call memory_sign_in first")
        return f"user:{_claims(token)['sub']}"

    def claims(self) -> dict[str, Any]:
        token = self._tokens.get("id_token")
        if not token:
            raise IdentityError("not signed in; call memory_sign_in first")
        return _claims(token)

    def preferences_namespace(self) -> str:
        return f"/users/{self.actor_id()}/preferences/"

    # ---------- token / credential lifecycle ----------

    def _fresh_id_token(self) -> str:
        token = self._tokens.get("id_token")
        if not token:
            raise IdentityError("not signed in; call memory_sign_in first")
        claims = _claims(token)
        if claims.get("exp", 0) - time.time() > 60:
            return token

        refresh = self._tokens.get("refresh_token")
        if not refresh:
            raise IdentityError("session expired and no refresh token; sign in again")
        try:
            auth = self._idp.initiate_auth(
                ClientId=self.config.client_id,
                AuthFlow="REFRESH_TOKEN_AUTH",
                AuthParameters={"REFRESH_TOKEN": refresh},
            )
        except ClientError as error:
            raise IdentityError(
                f"session refresh failed ({error.response['Error']['Code']}); sign in again"
            ) from error
        result = auth["AuthenticationResult"]
        self._tokens["id_token"] = result["IdToken"]
        # Cognito rotates the refresh token when rotation is enabled.
        if result.get("RefreshToken"):
            self._tokens["refresh_token"] = result["RefreshToken"]
        self._save_cache()
        return result["IdToken"]

    def credentials(self) -> dict[str, Any]:
        with self._lock:
            if (
                self._credentials
                and time.time() < self._credentials_expiry - REFRESH_MARGIN_SECONDS
            ):
                return self._credentials
            id_token = self._fresh_id_token()
            logins = {self.config.provider: id_token}
            identity_id = self._identity.get_id(
                IdentityPoolId=self.config.identity_pool_id, Logins=logins
            )["IdentityId"]
            raw = self._identity.get_credentials_for_identity(
                IdentityId=identity_id, Logins=logins
            )["Credentials"]
            self._credentials = {
                "aws_access_key_id": raw["AccessKeyId"],
                "aws_secret_access_key": raw["SecretKey"],
                "aws_session_token": raw["SessionToken"],
            }
            self._credentials_expiry = raw["Expiration"].timestamp()
            return self._credentials

    def memory_client(self) -> Any:
        return boto3.client(
            "bedrock-agentcore",
            region_name=self.config.region,
            config=AWS_CONFIG,
            **self.credentials(),
        )

    def s3_client(self) -> Any:
        return boto3.client(
            "s3",
            region_name=self.config.region,
            config=AWS_CONFIG,
            **self.credentials(),
        )

    def id_token(self) -> str:
        with self._lock:
            return self._fresh_id_token()

    def credentials_expire_in(self) -> int:
        return max(0, int(self._credentials_expiry - time.time()))

    # ---------- cache ----------

    def _load_cache(self) -> None:
        if not TOKEN_CACHE.is_file():
            return
        try:
            self._tokens = json.loads(TOKEN_CACHE.read_text())
        except (ValueError, OSError):
            self._tokens = {}

    def _save_cache(self) -> None:
        # Only tighten a directory we created ourselves; chmod on a shared
        # location such as /tmp is not ours to make and fails outright.
        created = not TOKEN_CACHE.parent.exists()
        TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
        if created:
            TOKEN_CACHE.parent.chmod(stat.S_IRWXU)
        TOKEN_CACHE.write_text(json.dumps(self._tokens))
        # Refresh tokens are long-lived; keep them owner-readable only.
        TOKEN_CACHE.chmod(stat.S_IRUSR | stat.S_IWUSR)
