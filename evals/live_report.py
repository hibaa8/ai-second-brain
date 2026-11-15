#!/usr/bin/env python3
"""Summarize private live hook telemetry without claiming answer-quality gains."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile


def summarize(vault: Path) -> str:
    log = vault / "evals" / "live.jsonl"
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()
            if line.strip()] if log.exists() else []
    offered = sum(bool(row.get("retrieved_pages")) for row in rows)
    instrumented = [row for row in rows if "source_use" in row]
    cited = sum(bool(row["source_use"]) for row in instrumented)
    pairs = [entry for row in rows for entry in row.get("source_use", [])]
    regressions = [row["regression"] for row in rows if "regression" in row]
    latest_file = vault / "evals" / "latest.json"
    latest = json.loads(latest_file.read_text(encoding="utf-8")) if latest_file.exists() else None
    lines = ["# Live Second Brain evaluation", "",
             "Updated after each completed local Codex turn when the Stop hook runs.", "",
             "| Signal | Count |", "| --- | ---: |",
             f"| Completed turns recorded | {len(rows)} |",
             f"| Turns offered at least one wiki page | {offered} |",
             f"| Turns with source-use instrumentation | {len(instrumented)} |",
             f"| Turns citing a registered original | {cited} |",
             f"| Cited original references | {len(pairs)} |",
             f"| Cited originals with valid hashes | {sum(x.get('source_valid') is True for x in pairs)} |",
             f"| Regression runs after vault changes | {len(regressions)} |",
             f"| Regression runs passing | {sum(x.get('ok') is True for x in regressions)} |",
             ""]
    if latest:
        lines += [f"Current regression snapshot: **{latest.get('cases_passed', latest.get('passed', 0))}/"
                  f"{latest.get('cases_total', latest.get('total', 0))}** "
                  f"cases; status **{'pass' if latest.get('ok') else 'fail'}**.", ""]
    lines += ["## Recent turns", "",
              "| Time (UTC) | Pages offered | Sources cited | Regression |",
              "| --- | ---: | ---: | --- |"]
    for row in rows[-10:]:
        regression = row.get("regression")
        state = (f"{regression.get('passed', 0)}/{regression.get('total', 0)}"
                 if regression else "—")
        lines.append(f"| {row.get('at', '')} | {len(row.get('retrieved_pages', []))} | "
                     f"{len(row.get('source_use', []))} | {state} |")
    lines += ["", "Older turns without source-use instrumentation are not counted as uncited. "
              "A page offered by retrieval is not counted as used. Source use requires a "
              "final-answer citation to a registered original; a cited wiki page is linked when available. See "
              "[the usage log](USAGE.md) for the cited claim and why it mattered. "
              "Missing citations can undercount use. These signals do not grade answer correctness "
              "or show improvement over Codex's existing memory. A paired baseline and vault-assisted "
              "answer evaluation is still required.", ""]
    return "\n".join(lines)


def write_report(vault: Path) -> Path:
    target = vault / "evals" / "LIVE_REPORT.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    usage = target.parent / "USAGE.md"
    if not usage.exists():
        usage.write_text("# Observed Second Brain source use\n\n"
                         "An entry means the final answer cited a registered original, with its wiki page when cited. "
                         "It records the answer's claim, not independent proof that the answer was correct "
                         "or better than Codex memory.\n\n"
                         "| Time (UTC) | Memory item | Source | Claim context | Source valid |\n"
                         "| --- | --- | --- | --- | --- |\n", encoding="utf-8")
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                     delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(summarize(vault))
    try:
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", type=Path, required=True)
    args = parser.parse_args()
    print(write_report(args.vault.expanduser().resolve()))
