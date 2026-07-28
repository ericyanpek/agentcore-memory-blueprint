import json
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from blueprint.domain import (  # noqa: E402
    MemoryCandidate,
    ValidationError,
    has_reviewer_group,
    personal_actor_id,
    project_actor_id,
)


class CandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        path = ROOT / "contracts" / "memory-candidate-proposed.json"
        self.event = json.loads(path.read_text())

    def test_contract_is_eligible(self) -> None:
        candidate = MemoryCandidate.from_event(self.event)
        self.assertTrue(candidate.eligible_for_review)
        self.assertEqual(candidate.project_id, "analytics-poc")

    def test_restricted_candidate_is_not_eligible(self) -> None:
        self.event["detail"]["privacy_classification"] = "restricted"
        candidate = MemoryCandidate.from_event(self.event)
        self.assertFalse(candidate.eligible_for_review)

    def test_low_confidence_candidate_is_not_eligible(self) -> None:
        self.event["detail"]["confidence"] = 0.2
        candidate = MemoryCandidate.from_event(self.event)
        self.assertFalse(candidate.eligible_for_review)

    def test_raw_evidence_reference_is_rejected(self) -> None:
        self.event["detail"]["evidence_ref"] = "the user said so"
        with self.assertRaises(ValidationError):
            MemoryCandidate.from_event(self.event)

    def test_candidate_id_matches_memory_request_identifier(self) -> None:
        self.event["detail"]["candidate_id"] = "cand-invalid/path"
        with self.assertRaises(ValidationError):
            MemoryCandidate.from_event(self.event)

    def test_actor_ids_are_scope_explicit(self) -> None:
        self.assertEqual(personal_actor_id("alice-123"), "user:alice-123")
        self.assertEqual(project_actor_id("analytics-poc"), "project:analytics-poc")

    def test_reviewer_group_requires_exact_membership(self) -> None:
        self.assertTrue(has_reviewer_group("[admins,memory-reviewers]"))
        self.assertTrue(has_reviewer_group(["memory-reviewers"]))
        self.assertFalse(has_reviewer_group("not-memory-reviewers"))
        self.assertTrue(
            has_reviewer_group(
                "[memory-reviewers-analytics-poc]",
                "memory-reviewers-analytics-poc",
            )
        )


if __name__ == "__main__":
    unittest.main()
