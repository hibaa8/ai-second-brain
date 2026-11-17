#!/usr/bin/env python3
"""Collect fresh-chat Codex answers for a private, paired memory evaluation.

This runner does not grade answers. Review them against registered originals and
keep case questions, answers, and traces outside the public repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from time import perf_counter


BASELINE = ("For this evaluation, use only your existing Codex memory and the question. "
            "Do not use tools, files, the Second Brain vault, search, or external sources. "
            "If you do not know, say so. Question: ")
VAULT = ("For this evaluation, use the Second Brain vault as additional evidence. "
         "Verify any memory claim against the registered original and cite its src ID. "
         "If the vault does not establish the answer, say so. Question: ")
TOOL_ITEM_TYPES = {"command_execution", "file_change", "mcp_tool_call", "web_search"}


def command(model: str, effort: str, answer: Path, condition: str, question: str,
            workdir: Path) -> list[str]:
    args = ["codex", "exec", "--ephemeral", "--sandbox", "read-only",
            "--skip-git-repo-check", "-C", str(workdir), "-m", model,
            "-c", f'model_reasoning_effort="{effort}"', "--json", "-o", str(answer)]
    if condition == "baseline":
        args.insert(3, "--disable")
        args.insert(4, "hooks")
    return args + [(BASELINE if condition == "baseline" else VAULT) + question]


def tool_items(events: Path) -> int:
    count = 0
    for line in events.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "item.completed" and event.get("item", {}).get("type") in TOOL_ITEM_TYPES:
            count += 1
    return count


def collect(cases: list[dict], output: Path, model: str, effort: str,
            workdir: Path, timeout: int, only: set[str]) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "manifest.json"
    manifest = (json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists()
                else {"model": model, "reasoning_effort": effort,
                      "same_codex_home_and_memory_settings": True,
                      "baseline_hooks_disabled": True, "results": []})
    if manifest["model"] != model or manifest["reasoning_effort"] != effort:
        raise ValueError("Existing results use a different model or reasoning effort")
    for case in cases:
        slug = case["id"]
        if only and slug not in only:
            continue
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
            raise ValueError(f"Invalid case id: {slug}")
        order = ("vault", "baseline") if hashlib.sha256(slug.encode()).digest()[0] % 2 else ("baseline", "vault")
        for condition in order:
            previous = next((item for item in manifest["results"]
                             if item["case_id"] == slug and item["condition"] == condition), None)
            if previous and previous["exit_code"] == 0 and previous.get("answer_file") and (output / previous["answer_file"]).is_file():
                print(f"{slug} {condition}: already complete", flush=True)
                continue
            prefix = output / f"{slug}-{condition}"
            answer = prefix.with_name(prefix.name + "-answer.md")
            events = prefix.with_name(prefix.name + "-events.jsonl")
            errors = prefix.with_name(prefix.name + "-stderr.txt")
            args = command(model, effort, answer, condition, case["question"], workdir)
            started = perf_counter()
            try:
                with events.open("w", encoding="utf-8") as event_stream, errors.open("w", encoding="utf-8") as error_stream:
                    process = subprocess.run(args, stdin=subprocess.DEVNULL,
                                             stdout=event_stream, stderr=error_stream,
                                             timeout=timeout, check=False)
                exit_code = process.returncode
            except subprocess.TimeoutExpired:
                exit_code = 124
            result = {"case_id": slug, "condition": condition, "exit_code": exit_code,
                      "wall_seconds": round(perf_counter() - started, 2),
                      "tool_items": tool_items(events),
                      "answer_file": answer.name if answer.exists() else None,
                      "events_file": events.name, "stderr_file": errors.name}
            manifest["results"] = [item for item in manifest["results"]
                                   if not (item["case_id"] == slug and item["condition"] == condition)] + [result]
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            print(f"{slug} {condition}: exit={exit_code}, wall={result['wall_seconds']}s, tools={result['tool_items']}", flush=True)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True, help="Private JSON file with a cases list")
    parser.add_argument("--output", type=Path, required=True, help="Private results directory")
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--effort", default="medium")
    parser.add_argument("--workdir", type=Path, default=Path("/private/tmp"))
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--only", nargs="*", default=[])
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))["cases"]
    report = collect(cases, args.output, args.model, args.effort,
                     args.workdir, args.timeout, set(args.only))
    return 0 if all(item["exit_code"] == 0 for item in report["results"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
