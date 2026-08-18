import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "poc"))

from analyze_retrieval_metrics import summarize  # noqa: E402


class SummarizeTests(unittest.TestCase):
    def test_reports_hit_rate(self) -> None:
        summary = summarize(
            [
                {"shared_hit": True, "query_fingerprint": ["aaa"]},
                {"shared_hit": False, "query_fingerprint": ["bbb"]},
                {"shared_hit": True, "query_fingerprint": ["ccc"]},
                {"shared_hit": False, "query_fingerprint": ["ddd"]},
            ]
        )
        self.assertEqual(summary["retrievals"], 4)
        self.assertEqual(summary["shared_hit_rate"], 0.5)

    def test_identical_queries_are_fully_overlapping_repeats(self) -> None:
        summary = summarize(
            [
                {"shared_hit": True, "query_fingerprint": ["aaa", "bbb"]},
                {"shared_hit": True, "query_fingerprint": ["bbb", "aaa"]},
            ]
        )
        self.assertEqual(summary["mean_pairwise_overlap"], 1.0)
        self.assertEqual(summary["repeat_query_rate"], 1.0)

    def test_disjoint_queries_do_not_overlap(self) -> None:
        summary = summarize(
            [
                {"shared_hit": True, "query_fingerprint": ["aaa"]},
                {"shared_hit": True, "query_fingerprint": ["bbb"]},
            ]
        )
        self.assertEqual(summary["mean_pairwise_overlap"], 0.0)
        self.assertEqual(summary["repeat_query_rate"], 0.0)

    def test_half_overlap_is_not_counted_as_a_repeat(self) -> None:
        summary = summarize(
            [
                {"shared_hit": True, "query_fingerprint": ["aaa", "bbb"]},
                {"shared_hit": True, "query_fingerprint": ["bbb", "ccc"]},
            ]
        )
        self.assertAlmostEqual(summary["mean_pairwise_overlap"], 1 / 3)
        self.assertEqual(summary["repeat_query_rate"], 0.0)

    def test_a_single_retrieval_has_no_pairs(self) -> None:
        summary = summarize([{"shared_hit": True, "query_fingerprint": ["aaa"]}])
        self.assertIsNone(summary["mean_pairwise_overlap"])
        self.assertIsNone(summary["repeat_query_rate"])

    def test_no_retrievals_is_not_a_crash(self) -> None:
        summary = summarize([])
        self.assertEqual(summary["retrievals"], 0)
        self.assertIsNone(summary["shared_hit_rate"])


if __name__ == "__main__":
    unittest.main()
