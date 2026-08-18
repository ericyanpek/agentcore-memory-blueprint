import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent.context_builder import RetrievalMetrics, fingerprint_query  # noqa: E402


class FingerprintQueryTests(unittest.TestCase):
    def test_is_order_and_case_insensitive(self) -> None:
        self.assertEqual(
            fingerprint_query("How is Revenue calculated?"),
            fingerprint_query("calculated revenue how IS"),
        )

    def test_drops_short_tokens(self) -> None:
        self.assertEqual(
            fingerprint_query("revenue"),
            fingerprint_query("is revenue"),
        )

    def test_does_not_contain_the_original_words(self) -> None:
        fingerprint = fingerprint_query("quarterly revenue")
        self.assertNotIn("revenue", fingerprint)
        self.assertNotIn("quarterly", fingerprint)

    def test_different_queries_differ(self) -> None:
        self.assertNotEqual(
            fingerprint_query("revenue definition"),
            fingerprint_query("churn definition"),
        )


class RetrievalMetricsTests(unittest.TestCase):
    def test_reports_a_hit_with_the_top_score(self) -> None:
        metrics = RetrievalMetrics.from_records(
            query="How is revenue calculated?",
            records=[{"score": 0.42}, {"score": 0.91}],
        )
        record = metrics.as_log_record()
        self.assertEqual(record["metric"], "shared_memory_retrieval")
        self.assertTrue(record["shared_hit"])
        self.assertEqual(record["shared_candidates"], 2)
        self.assertEqual(record["shared_top_score"], 0.91)

    def test_reports_a_miss_without_a_score(self) -> None:
        metrics = RetrievalMetrics.from_records(query="anything", records=[])
        record = metrics.as_log_record()
        self.assertFalse(record["shared_hit"])
        self.assertEqual(record["shared_candidates"], 0)
        self.assertIsNone(record["shared_top_score"])


if __name__ == "__main__":
    unittest.main()
