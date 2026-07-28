import json
import os
import pathlib
import sys
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

PROJECT_ID = "analytics-poc"
REVIEWER_ORIGIN = "http://localhost:3000"
SUBJECT = "34e8b408-a091-7010-aad5-6d7b0230f7c8"
VALID_BODY = {
    "candidate_id": "cand-desktop-abc123456789",
    "statement": (
        "The curated churn view counts a downgrade as churn; true logo churn "
        "must be measured from the subscription ledger instead."
    ),
    "category": "constraint",
    "evidence_ref": "s3://audit-bucket/traces/2026-07-28/abc123.json",
    "confidence": 0.95,
    "privacy_classification": "internal",
}


def load_handler():
    environment = {
        "EVENT_BUS_NAME": "analytics-poc-demo-events",
        "PROJECT_ID": PROJECT_ID,
        "REVIEWER_ORIGIN": REVIEWER_ORIGIN,
    }
    with mock.patch.dict(os.environ, environment, clear=False), mock.patch(
        "boto3.client"
    ):
        sys.modules.pop("handlers.propose_candidate", None)
        from handlers import propose_candidate

        return propose_candidate


def request(body: dict, subject: str | None = SUBJECT) -> dict:
    claims = {"sub": subject} if subject else {}
    return {
        "httpMethod": "POST",
        "requestContext": {"authorizer": {"claims": claims}},
        "body": json.dumps(body),
    }


class ProposeCandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_handler()
        self.events = mock.Mock()
        self.events.put_events.return_value = {"FailedEntryCount": 0}
        self.module.EVENTS = self.events

    def emitted_detail(self) -> dict:
        entry = self.events.put_events.call_args.kwargs["Entries"][0]
        return json.loads(entry["Detail"])

    def test_accepts_a_well_formed_proposal(self) -> None:
        response = self.module.handler(request(VALID_BODY), None)

        self.assertEqual(response["statusCode"], 202)
        body = json.loads(response["body"])
        self.assertTrue(body["eligible_for_review"])
        self.assertEqual(self.emitted_detail()["statement"], VALID_BODY["statement"])

    def test_proposer_comes_from_the_token_not_the_body(self) -> None:
        spoofed = {**VALID_BODY, "proposer_actor_id": "user:someone-else"}

        self.module.handler(request(spoofed), None)

        self.assertEqual(
            self.emitted_detail()["proposer_actor_id"], f"user:{SUBJECT}"
        )

    def test_project_id_cannot_be_overridden_by_the_body(self) -> None:
        self.module.handler(request({**VALID_BODY, "project_id": "other"}), None)

        self.assertEqual(self.emitted_detail()["project_id"], PROJECT_ID)

    def test_unauthenticated_request_is_rejected(self) -> None:
        response = self.module.handler(request(VALID_BODY, subject=None), None)

        self.assertEqual(response["statusCode"], 403)
        self.events.put_events.assert_not_called()

    def test_local_transcript_path_is_not_valid_evidence(self) -> None:
        body = {**VALID_BODY, "evidence_ref": "/Users/alice/.claude/transcript.jsonl"}

        response = self.module.handler(request(body), None)

        self.assertEqual(response["statusCode"], 400)
        self.events.put_events.assert_not_called()

    def test_restricted_candidate_is_reported_as_ineligible(self) -> None:
        body = {**VALID_BODY, "privacy_classification": "restricted"}

        response = self.module.handler(request(body), None)

        # The event is still emitted so the policy rejection is audited, but the
        # caller must not be told a reviewer will see it.
        self.assertEqual(response["statusCode"], 202)
        self.assertFalse(json.loads(response["body"])["eligible_for_review"])

    def test_malformed_body_is_rejected(self) -> None:
        event = request(VALID_BODY)
        event["body"] = "not json"

        response = self.module.handler(event, None)

        self.assertEqual(response["statusCode"], 400)
        self.events.put_events.assert_not_called()

    def test_response_allows_the_reviewer_origin(self) -> None:
        response = self.module.handler(request(VALID_BODY), None)

        self.assertEqual(
            response["headers"]["access-control-allow-origin"], REVIEWER_ORIGIN
        )


if __name__ == "__main__":
    unittest.main()
