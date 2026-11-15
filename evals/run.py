#!/usr/bin/env python3
"""Read-only retrieval and provenance smoke eval for a Second Brain vault."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import brain  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]


def evaluate(vault: Path, cases: dict) -> dict:
    errors = brain.validate(vault)
    if errors:
        return {"ok": False, "validation_errors": errors, "cases": []}

    results = []
    with tempfile.TemporaryDirectory(prefix="second-brain-eval-") as directory:
        # The normal index may be in use. Build a disposable one and leave the
        # selected vault and its existing index untouched.
        brain.db_path = lambda _vault: Path(directory) / "eval.sqlite3"
        index = brain.build_index(vault)
        for case in cases["cases"]:
            started = perf_counter()
            kind = case["kind"]
            if kind == "search":
                hits = brain.search(vault, case["query"], limit=max(10, case["top_k"]))
                ids = [hit["id"] for hit in hits]
                rank = ids.index(case["expected_page"]) + 1 if case["expected_page"] in ids else None
                passed = rank is not None and rank <= case["top_k"]
                detail = {"rank": rank, "top_k": case["top_k"], "returned": ids[:case["top_k"]]}
            elif kind == "walk":
                paths = brain.walk(vault, case["seed"], hops=case["max_hops"])
                match = next((item for item in paths if item["page"] == case["expected_page"]), None)
                passed = match is not None
                detail = {"hops": match["hops"] if match else None,
                          "source_ids": [step["source"] for step in match["path"]] if match else []}
            elif kind == "source":
                record = next((r for r in brain.source_records(vault) if r["id"] == case["source_id"]), None)
                path = brain.source_path(vault, record["location"]) if record else None
                available = bool(path and path.is_file())
                passed = available and case["contains"] in path.read_text(encoding="utf-8")
                detail = {"available": available, "hash_matches": available and brain.sha256(path) == record["sha256"]}
                passed = passed and detail["hash_matches"]
            else:
                raise ValueError(f"Unknown case kind: {kind}")
            results.append({"name": case["name"], "kind": kind, "passed": passed,
                            "milliseconds": round((perf_counter() - started) * 1000, 2), **detail})

    searches = [r for r in results if r["kind"] == "search"]
    return {"ok": all(r["passed"] for r in results), "vault": str(vault),
            "index": {"pages": index["pages"], "edges": index["edges"], "location": "temporary"},
            "cases_passed": sum(r["passed"] for r in results), "cases_total": len(results),
            "search_top1": sum(r["rank"] == 1 for r in searches), "search_total": len(searches),
            "cases": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", type=Path, default=ROOT / "examples" / "demo-vault")
    parser.add_argument("--cases", type=Path, default=ROOT / "evals" / "demo.json")
    args = parser.parse_args()
    vault = args.vault.expanduser().resolve()
    cases = json.loads(args.cases.expanduser().read_text(encoding="utf-8"))
    report = evaluate(vault, cases)
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
