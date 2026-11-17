#!/usr/bin/env python3
"""Summarize human-scored paired answers and verify cited original hashes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from statistics import median
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import brain  # noqa: E402


SOURCE_ID = re.compile(r"\bsrc-[0-9a-f]{16}\b")


def score(vault: Path, cases: list[dict], manifest: dict, grades: dict,
          answers_dir: Path) -> dict:
    records = {record["id"]: record for record in brain.source_records(vault)}
    runs = {(item["case_id"], item["condition"]): item for item in manifest["results"]}
    details = []
    for case in cases:
        row = {"id": case["id"], "category": case.get("category"),
               "answerable": bool(case.get("source_ids"))}
        for condition in ("baseline", "vault"):
            run = runs.get((case["id"], condition))
            if not run or run["exit_code"] != 0 or not run.get("answer_file"):
                raise ValueError(f"Missing successful {condition} run for {case['id']}")
            answer = (answers_dir / run["answer_file"]).read_text(encoding="utf-8")
            cited = sorted(set(SOURCE_ID.findall(answer)))
            valid = []
            for source_id in cited:
                record = records.get(source_id)
                path = brain.source_path(vault, record["location"]) if record else None
                valid.append(bool(path and path.is_file() and
                                  brain.sha256(path) == record["sha256"]))
            grade = grades[case["id"]][condition]
            row[condition] = {"correct": grade["correct"],
                              "abstained": grade["abstained"],
                              "manually_source_supported": grade["supported"],
                              "cited_sources": cited,
                              "all_cited_hashes_valid": bool(cited) and all(valid),
                              "wall_seconds": run["wall_seconds"],
                              "tool_items": run["tool_items"]}
        details.append(row)
    answerable = [row for row in details if row["answerable"]]
    controls = [row for row in details if not row["answerable"]]
    return {"model": manifest["model"], "reasoning_effort": manifest["reasoning_effort"],
            "pairs": len(details), "answerable": len(answerable), "unknown_controls": len(controls),
            "baseline_correct_answerable": sum(row["baseline"]["correct"] for row in answerable),
            "vault_correct_answerable": sum(row["vault"]["correct"] for row in answerable),
            "vault_supported_answerable": sum(row["vault"]["manually_source_supported"] is True
                                              and row["vault"]["all_cited_hashes_valid"]
                                              for row in answerable),
            "baseline_correct_unknown": sum(row["baseline"]["correct"] for row in controls),
            "vault_correct_unknown": sum(row["vault"]["correct"] for row in controls),
            "baseline_tool_calls": sum(row["baseline"]["tool_items"] for row in details),
            "median_wall_seconds": {
                condition: round(median(row[condition]["wall_seconds"] for row in details), 2)
                for condition in ("baseline", "vault")},
            "details": details}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--grades", type=Path, required=True)
    args = parser.parse_args()
    report = score(args.vault, json.loads(args.cases.read_text())["cases"],
                   json.loads((args.results / "manifest.json").read_text()),
                   json.loads(args.grades.read_text())["grades"], args.results)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
