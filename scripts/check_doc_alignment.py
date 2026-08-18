#!/usr/bin/env python3
"""Check that each bilingual document pair has not drifted apart.

Documentation here is maintained in Chinese and English, and a change to one side is
easy to forget on the other. Structural drift is the detectable part: if one version
gained a section, a table row, or a citation, the counts stop matching.

Compares heading structure, table rows, code fences, verbatim test-output lines, and
external URLs. Exits non-zero on divergence so it can gate a commit.
"""

from __future__ import annotations

import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]

# Chinese is the primary version in every pair except SKILL.md, where the English file
# is the source and the Chinese one is the translation.
PAIRS = [
    ("README.md", "README.en.md"),
    ("SECURITY.md", "SECURITY.en.md"),
    ("docs/架构设计.md", "docs/architecture.md"),
    ("docs/设计取舍依据.md", "docs/design-rationale.md"),
    ("docs/下一步演进.md", "docs/roadmap.md"),
    ("docs/演示手册.md", "docs/demo-runbook.md"),
    ("docs/评估记录.md", "docs/sample-review.md"),
    ("docs/参考资料.md", "docs/references.md"),
    ("docs/记忆产品横评.md", "docs/memory-landscape.md"),
    ("docs/AWS官方背书.md", "docs/aws-alignment.md"),
    ("docs/桌面客户端集成设计.md", "docs/desktop-client-integration.md"),
    ("docs/为什么按写入权威分层.md", "docs/why-layer-by-write-authority.md"),
    ("docs/ENTERPRISE_GOVERNANCE_BLUEPRINT.md",
     "docs/ENTERPRISE_GOVERNANCE_BLUEPRINT.en.md"),
    ("docs/CONTROL_BASELINE.md", "docs/CONTROL_BASELINE.en.md"),
    ("docs/OBSERVABILITY_BLUEPRINT.md",
     "docs/OBSERVABILITY_BLUEPRINT.en.md"),
    ("docs/AWS_SAMPLE_CATALOG.md", "docs/AWS_SAMPLE_CATALOG.en.md"),
    ("experiments/README.md", "experiments/README.en.md"),
    ("experiments/observability-evidence.md",
     "experiments/observability-evidence.en.md"),
    ("HANDOFF_REPORT.md", "HANDOFF_REPORT.en.md"),
    ("skills/validate-revenue-metric/SKILL.md",
     "skills/validate-revenue-metric/SKILL.zh-CN.md"),
]

# Generated or independently authored; no translation duty.
UNPAIRED = {"docs/scenario-test-report.md", "docs/实验报告.md", "CLAUDE.md"}


def headings(text: str) -> list[int]:
    return [
        len(match.group(1))
        for match in re.finditer(r"^(#{1,6})\s+\S", text, re.MULTILINE)
    ]


def table_rows(text: str) -> int:
    # A row is a line starting with '|' that is not a separator like |---|---|.
    return sum(
        1
        for line in text.splitlines()
        if line.lstrip().startswith("|") and not re.fullmatch(r"[|\s:-]+", line.strip())
    )


def code_fences(text: str) -> int:
    return len(re.findall(r"^```", text, re.MULTILINE))


def evidence_lines(text: str) -> list[str]:
    """Measured test output. Must be reproduced character for character."""
    return [
        line.strip()
        for line in text.splitlines()
        if line.lstrip().startswith("[PASS]") or line.lstrip().startswith("[FAIL]")
    ]


def urls(text: str) -> set[str]:
    # Stop at CJK characters and backticks too: Chinese prose often follows a URL with
    # no space, and without this the trailing text is captured as part of the URL.
    return {
        url.rstrip(").,;`")
        for url in re.findall(r"https?://[^\s)>\"`　-〿一-鿿]+", text)
    }


def doc_links(path: pathlib.Path, text: str) -> list[str]:
    broken = []
    for target in re.findall(r"\]\(([^)#]+\.md)(?:#[^)]*)?\)", text):
        if target.startswith("http"):
            continue
        if not (path.parent / target).is_file():
            broken.append(target)
    return broken


def compare(primary: pathlib.Path, secondary: pathlib.Path) -> list[str]:
    problems: list[str] = []
    a, b = primary.read_text(), secondary.read_text()

    if headings(a) != headings(b):
        problems.append(
            f"heading structure differs: {len(headings(a))} vs {len(headings(b))} "
            f"headings (levels {headings(a)} vs {headings(b)})"
        )
    if table_rows(a) != table_rows(b):
        problems.append(f"table rows differ: {table_rows(a)} vs {table_rows(b)}")
    if code_fences(a) != code_fences(b):
        problems.append(f"code fences differ: {code_fences(a)} vs {code_fences(b)}")

    primary_evidence, secondary_evidence = evidence_lines(a), evidence_lines(b)
    if primary_evidence != secondary_evidence:
        problems.append(
            f"test-output lines differ: {len(primary_evidence)} vs "
            f"{len(secondary_evidence)}; these are measured evidence and must match "
            f"character for character"
        )

    only_primary = urls(a) - urls(b)
    only_secondary = urls(b) - urls(a)
    if only_primary:
        problems.append(f"URLs only in {primary.name}: {sorted(only_primary)[:3]}")
    if only_secondary:
        problems.append(f"URLs only in {secondary.name}: {sorted(only_secondary)[:3]}")

    for path, text in ((primary, a), (secondary, b)):
        broken = doc_links(path, text)
        if broken:
            problems.append(f"{path.name} links to missing files: {broken}")

    return problems


def main() -> int:
    failures = 0
    paired: set[str] = set()

    for primary_name, secondary_name in PAIRS:
        primary, secondary = ROOT / primary_name, ROOT / secondary_name
        paired.update({primary_name, secondary_name})

        missing = [p.name for p in (primary, secondary) if not p.is_file()]
        if missing:
            print(f"MISSING  {primary_name} <-> {secondary_name}: {missing}")
            failures += 1
            continue

        problems = compare(primary, secondary)
        if problems:
            failures += 1
            print(f"DRIFT    {primary_name} <-> {secondary_name}")
            for problem in problems:
                print(f"         - {problem}")
        else:
            print(f"ok       {primary_name} <-> {secondary_name}")

    # Catch documents that exist but were never added to PAIRS.
    tracked = paired | UNPAIRED
    for path in sorted(ROOT.glob("docs/*.md")) + sorted(ROOT.glob("*.md")):
        relative = path.relative_to(ROOT).as_posix()
        if relative not in tracked:
            print(f"UNPAIRED {relative}: not in PAIRS and not declared unpaired")
            failures += 1

    print()
    print(
        f"{len(PAIRS) - failures if failures <= len(PAIRS) else 0}/{len(PAIRS)} pairs aligned"
        if failures
        else f"all {len(PAIRS)} pairs aligned"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
