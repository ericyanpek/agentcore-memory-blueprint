from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any


ALLOWED_CATEGORIES = {
    "fact",
    "decision",
    "constraint",
    "incident",
    "procedure_hint",
}
ALLOWED_PRIVACY = {"public", "internal", "confidential", "restricted"}
ALLOWED_PROMOTIONS = {"none", "knowledge_base", "skill"}
ID_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_/-]*$")
REQUEST_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]+$")


class ValidationError(ValueError):
    pass


@dataclass(frozen=True)
class MemoryCandidate:
    candidate_id: str
    project_id: str
    proposer_actor_id: str
    category: str
    statement: str
    evidence_ref: str
    confidence: float
    privacy_classification: str
    expires_at: str | None
    promotion_hint: str

    @classmethod
    def from_event(cls, event: dict[str, Any]) -> "MemoryCandidate":
        detail = event.get("detail", event)
        required = (
            "candidate_id",
            "project_id",
            "proposer_actor_id",
            "category",
            "statement",
            "evidence_ref",
            "confidence",
            "privacy_classification",
        )
        missing = [key for key in required if key not in detail]
        if missing:
            raise ValidationError(f"missing candidate fields: {', '.join(missing)}")

        candidate = cls(
            candidate_id=str(detail["candidate_id"]),
            project_id=str(detail["project_id"]),
            proposer_actor_id=str(detail["proposer_actor_id"]),
            category=str(detail["category"]),
            statement=str(detail["statement"]).strip(),
            evidence_ref=str(detail["evidence_ref"]),
            confidence=float(detail["confidence"]),
            privacy_classification=str(detail["privacy_classification"]),
            expires_at=detail.get("expires_at"),
            promotion_hint=str(detail.get("promotion_hint", "none")),
        )
        candidate.validate()
        return candidate

    def validate(self) -> None:
        if (
            not self.candidate_id.startswith("cand-")
            or len(self.candidate_id) > 80
            or not REQUEST_IDENTIFIER.fullmatch(self.candidate_id)
        ):
            raise ValidationError(
                "candidate_id must start with 'cand-', contain only letters, "
                "numbers, underscores, or hyphens, and be at most 80 characters"
            )
        if not self.project_id or len(self.project_id) > 80:
            raise ValidationError("project_id must contain 1-80 characters")
        if not ID_COMPONENT.fullmatch(self.project_id):
            raise ValidationError("project_id contains unsupported characters")
        if not self.proposer_actor_id.startswith("user:"):
            raise ValidationError("proposer_actor_id must be a user actor")
        if self.category not in ALLOWED_CATEGORIES:
            raise ValidationError(f"unsupported category: {self.category}")
        if not 20 <= len(self.statement) <= 2000:
            raise ValidationError("statement must contain 20-2000 characters")
        if not self.evidence_ref.startswith(("trace://", "s3://", "log://")):
            raise ValidationError("evidence_ref must use trace://, s3://, or log://")
        if not 0 <= self.confidence <= 1:
            raise ValidationError("confidence must be between 0 and 1")
        if self.privacy_classification not in ALLOWED_PRIVACY:
            raise ValidationError("unsupported privacy classification")
        if self.promotion_hint not in ALLOWED_PROMOTIONS:
            raise ValidationError("unsupported promotion hint")

    @property
    def eligible_for_review(self) -> bool:
        return (
            self.privacy_classification != "restricted"
            and self.confidence >= 0.70
        )

    def as_item(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        return {
            "candidate_id": self.candidate_id,
            "project_id": self.project_id,
            "proposer_actor_id": self.proposer_actor_id,
            "category": self.category,
            "statement": self.statement,
            "evidence_ref": self.evidence_ref,
            "confidence_basis_points": int(self.confidence * 10_000),
            "privacy_classification": self.privacy_classification,
            "expires_at": self.expires_at,
            "promotion_hint": self.promotion_hint,
            "status": "PENDING_REVIEW" if self.eligible_for_review else "REJECTED_POLICY",
            "created_at": now,
            "updated_at": now,
        }


def personal_actor_id(authenticated_subject: str) -> str:
    normalized = authenticated_subject.strip()
    if not ID_COMPONENT.fullmatch(normalized):
        raise ValidationError("authenticated subject contains unsupported characters")
    return f"user:{normalized}"


def project_actor_id(project_id: str) -> str:
    normalized = project_id.strip()
    if not ID_COMPONENT.fullmatch(normalized):
        raise ValidationError("project ID contains unsupported characters")
    return f"project:{normalized}"


def shared_project_namespace(project_id: str) -> str:
    return f"/projects/{project_actor_id(project_id)}/shared/"


def has_reviewer_group(claim: Any, required_group: str = "memory-reviewers") -> bool:
    if isinstance(claim, list):
        groups = {str(value).strip() for value in claim}
    else:
        text = str(claim or "").strip().strip("[]")
        groups = {
            value.strip().strip("\"'")
            for value in text.split(",")
            if value.strip()
        }
    return required_group in groups
