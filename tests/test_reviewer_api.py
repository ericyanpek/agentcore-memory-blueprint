import json
import os
import pathlib
import sys
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

REVIEWER_GROUP = "memory-reviewers-memory-poc"
REVIEWER_ORIGIN = "http://localhost:3000"
CANDIDATES = [
    {"candidate_id": "cand-a", "status": "PENDING_REVIEW", "created_at": "2026-07-28T01:00:00Z"},
    {"candidate_id": "cand-b", "status": "PUBLISHED", "created_at": "2026-07-28T03:00:00Z"},
    {
        "candidate_id": "cand-c",
        "status": "PUBLISH_FAILED",
        "created_at": "2026-07-28T02:00:00Z",
        "task_token": "secret-token",
    },
]


class FakePaginator:
    def paginate(self, **_kwargs):
        return [{"Items": list(CANDIDATES)}]


class FakeTable:
    name = "memory-poc-poc-memory-candidates"

    def __init__(self) -> None:
        self.meta = mock.Mock()
        self.meta.client.get_paginator.return_value = FakePaginator()


def load_handler():
    environment = {
        "CANDIDATE_TABLE_NAME": "candidates",
        "CALLBACK_TABLE_NAME": "callbacks",
        "REVIEWER_GROUP": REVIEWER_GROUP,
        "REVIEWER_ORIGIN": REVIEWER_ORIGIN,
    }
    with mock.patch.dict(os.environ, environment, clear=False), mock.patch(
        "boto3.resource"
    ), mock.patch("boto3.client"):
        sys.modules.pop("handlers.reviewer_api", None)
        from handlers import reviewer_api

        return reviewer_api


def reviewer_event(method: str, path_parameters=None) -> dict:
    return {
        "httpMethod": method,
        "pathParameters": path_parameters,
        "requestContext": {
            "authorizer": {
                "claims": {
                    "sub": "reviewer-sub",
                    "cognito:groups": [REVIEWER_GROUP],
                }
            }
        },
    }


class ReviewerApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_handler()
        self.module.CANDIDATES = FakeTable()

    def test_list_route_handles_null_path_parameters(self) -> None:
        response = self.module.handler(reviewer_event("GET"), None)

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(body["matched"], len(CANDIDATES))
        self.assertEqual(
            [item["candidate_id"] for item in body["candidates"]],
            ["cand-b", "cand-c", "cand-a"],
        )

    def test_list_never_returns_task_tokens(self) -> None:
        response = self.module.handler(reviewer_event("GET"), None)

        self.assertNotIn("task_token", response["body"])

    def test_status_filter_selects_failed_candidates(self) -> None:
        event = reviewer_event("GET")
        event["queryStringParameters"] = {"status": "publish_failed"}

        body = json.loads(self.module.handler(event, None)["body"])

        self.assertEqual(
            [item["candidate_id"] for item in body["candidates"]], ["cand-c"]
        )

    def test_responses_allow_the_reviewer_origin(self) -> None:
        response = self.module.handler(reviewer_event("GET"), None)

        self.assertEqual(
            response["headers"]["access-control-allow-origin"], REVIEWER_ORIGIN
        )

    def test_non_reviewer_is_rejected(self) -> None:
        event = reviewer_event("GET")
        event["requestContext"]["authorizer"]["claims"]["cognito:groups"] = ["other"]

        response = self.module.handler(event, None)

        self.assertEqual(response["statusCode"], 403)


if __name__ == "__main__":
    unittest.main()
