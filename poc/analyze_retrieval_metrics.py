#!/usr/bin/env python3
"""Aggregate shared_memory_retrieval log records into a hit rate and a repeat rate.

Two numbers decide whether a governed shared tier repays its cost. The hit rate says
whether approved memory is retrieved at all. The repeat rate says whether the same
question keeps being asked, which is what makes writing an answer down worth the
review it costs. Both are aggregate, so neither is visible in a single turn.

Usage: python3 poc/analyze_retrieval_metrics.py <log-file> [<log-file> ...]

Input is JSON Lines. Lines that are not shared_memory_retrieval records are ignored, so
a raw CloudWatch export can be passed without pre-filtering.
"""

from __future__ import annotations

import json
import pathlib
import sys
from itertools import combinations
from typing import Any


REPEAT_THRESHOLD = 0.5


def load_records(paths: list[pathlib.Path]) -> list[dict[str, Any]]:
    records = []
    for path in paths:
        for line in path.read_text().splitlines():
            start = line.find("{")
            if start < 0:
                continue
            try:
                candidate = json.loads(line[start:])
            except json.JSONDecodeError:
                continue
            if candidate.get("metric") == "shared_memory_retrieval":
                records.append(candidate)
    return records


def jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    if not total:
        return {
            "retrievals": 0,
            "shared_hit_rate": None,
            "mean_pairwise_overlap": None,
            "repeat_query_rate": None,
        }

    hits = sum(1 for record in records if record.get("shared_hit"))
    fingerprints = [set(record.get("query_fingerprint", [])) for record in records]
    # O(n²) in records — acceptable for a POC analyzing a demo run
    pairs = [jaccard(a, b) for a, b in combinations(fingerprints, 2)]

    return {
        "retrievals": total,
        "shared_hit_rate": hits / total,
        "mean_pairwise_overlap": sum(pairs) / len(pairs) if pairs else None,
        "repeat_query_rate": (
            sum(1 for value in pairs if value >= REPEAT_THRESHOLD) / len(pairs)
            if pairs
            else None
        ),
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    paths = [pathlib.Path(argument) for argument in argv[1:]]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        print(f"no such file: {missing}")
        return 2
    print(json.dumps(summarize(load_records(paths)), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
