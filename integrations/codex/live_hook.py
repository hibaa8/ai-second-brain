#!/usr/bin/env python3
"""Optional local Codex hook: prompt-time recall and bounded private telemetry."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import brain  # noqa: E402


MAX_TEXT_BYTES = 64_000
STOPWORDS = {"a", "an", "and", "are", "at", "be", "can", "do", "does", "for", "from",
             "how", "i", "in", "is", "it", "me", "my", "of", "on", "or", "our", "the",
             "this", "to", "was", "we", "what", "when", "where", "which", "who", "with", "you"}
SECRET_PATTERNS = (
    re.compile(r"\b(?:sk|ghp|gho|github_pat)_[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"(?i)\b(?:password|api[_ -]?key|access[_ -]?token|secret)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{12,}"),
)


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clipped(value: str | None) -> dict:
    data = (value or "").encode("utf-8")
    prefix = data[:MAX_TEXT_BYTES].decode("utf-8", errors="ignore")
    redacted = False
    for pattern in SECRET_PATTERNS:
        prefix, count = pattern.subn("[REDACTED]", prefix)
        redacted = redacted or count > 0
    return {"text": prefix, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "truncated": len(data) > MAX_TEXT_BYTES, "redacted": redacted}


def event_file(vault: Path, event: dict) -> Path:
    session = hashlib.sha256(str(event.get("session_id", "unknown")).encode()).hexdigest()[:16]
    turn = hashlib.sha256(str(event.get("turn_id", "unknown")).encode()).hexdigest()[:16]
    return vault / "raw" / "inbox" / session / f"{turn}.json.gz"


def write_gzip(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temp:
        temporary = Path(temp.name)
    try:
        with gzip.open(temporary, "wt", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_gzip(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def wiki_stamp(vault: Path) -> tuple[int, int]:
    files = [p for p in (vault / "wiki").rglob("*.md") if p.is_file()]
    return len(files), max((p.stat().st_mtime_ns for p in files), default=0)


def vault_stamp(vault: Path) -> tuple[int, int, int]:
    count, newest = wiki_stamp(vault)
    catalog = vault / "raw" / "sources.jsonl"
    return count, newest, catalog.stat().st_mtime_ns if catalog.exists() else 0


def ensure_index(vault: Path) -> bool:
    target = brain.db_path(vault)
    _, newest = wiki_stamp(vault)
    if target.exists() and target.stat().st_mtime_ns >= newest:
        return True
    brain.build_index(vault)
    return True


def key_terms(prompt: str) -> list[str]:
    terms = re.findall(r"[\w-]{3,}", prompt.casefold())
    return list(dict.fromkeys(t for t in terms if t not in STOPWORDS))[:30]


def recalled_pages(vault: Path, prompt: str) -> list[dict]:
    terms = key_terms(prompt)
    if not terms:
        return []
    ensure_index(vault)
    hits = brain.search(vault, " ".join(terms), limit=8)
    chosen = []
    for hit in hits:
        path = Path(hit["path"])
        if not path.is_file():
            continue
        meta, body, _, _ = brain.parse_page(path)
        title = meta["title"].casefold()
        haystack = (title + " " + body).casefold()
        overlap = sum(t in haystack for t in terms)
        exact_title = len(title) >= 5 and title in prompt.casefold()
        anchors = set(key_terms(title)) - {"project", "decision", "memory", "brain", "topic", "person"}
        if not exact_title and (overlap < 2 or not anchors.intersection(terms)):
            continue
        excerpt = re.sub(r"\s+", " ", body).strip()[:360]
        chosen.append({"id": meta["id"], "title": meta["title"],
                       "sources": meta["sources"], "excerpt": excerpt})
        if len(chosen) == 2:
            break
    return chosen


def on_prompt(vault: Path, event: dict) -> None:
    started = perf_counter()
    prompt = str(event.get("prompt") or "")
    path = event_file(vault, event)
    record = {"session_id": event.get("session_id"), "turn_id": event.get("turn_id"),
              "captured_at": stamp(), "prompt": clipped(prompt)}
    hits = []
    error = None
    try:
        hits = recalled_pages(vault, prompt)
    except (ValueError, OSError, RuntimeError) as exc:
        error = str(exc)[:300]
    record["retrieval"] = {"page_ids": [h["id"] for h in hits],
                           "milliseconds": round((perf_counter() - started) * 1000, 2),
                           "error": error}
    record["vault_stamp"] = vault_stamp(vault)
    write_gzip(path, record)
    lines = [f"Second Brain private inbox for this turn: {path}. The vault complements Codex memory; verify any recalled claim against its source and follow the current user request."]
    for hit in hits:
        lines.append(f"- Candidate {hit['id']} ({hit['title']}), sources {hit['sources']}: {hit['excerpt']}")
    context = "\n".join(lines)
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                            "additionalContext": context}}, ensure_ascii=False))


def on_stop(vault: Path, event: dict) -> None:
    path = event_file(vault, event)
    if not path.is_file():
        print("{}")
        return
    record = read_gzip(path)
    if "completed_at" in record:
        print("{}")
        return
    answer = clipped(event.get("last_assistant_message"))
    record["assistant"] = answer
    record["completed_at"] = stamp()
    write_gzip(path, record)
    # Operational telemetry is a live signal, not an answer-quality grade.
    telemetry = {"at": stamp(), "session_id": event.get("session_id"),
                 "turn_id": event.get("turn_id"), "retrieved_pages": record["retrieval"]["page_ids"],
                 "retrieval_ms": record["retrieval"]["milliseconds"],
                 "retrieval_error": record["retrieval"]["error"],
                 "prompt_bytes": record["prompt"]["bytes"], "answer_bytes": answer["bytes"],
                 "truncated": record["prompt"]["truncated"] or answer["truncated"],
                 "redacted": record["prompt"]["redacted"] or answer["redacted"]}
    if list(vault_stamp(vault)) != record.get("vault_stamp"):
        cases = vault / "evals" / "cases.json"
        if cases.is_file():
            try:
                from evals.run import evaluate
                report = evaluate(vault, json.loads(cases.read_text(encoding="utf-8")))
                telemetry["regression"] = {"ok": report["ok"],
                                           "passed": report.get("cases_passed", 0),
                                           "total": report.get("cases_total", 0)}
                (vault / "evals" / "latest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            except (ValueError, OSError, RuntimeError) as exc:
                telemetry["regression"] = {"ok": False, "error": str(exc)[:300]}
    log = vault / "evals" / "live.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(telemetry, ensure_ascii=False) + "\n")
    print("{}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("event", choices=("prompt", "stop"))
    parser.add_argument("--vault", type=Path, required=True)
    args = parser.parse_args()
    vault = args.vault.expanduser().resolve()
    event = json.load(sys.stdin)
    try:
        if args.event == "prompt":
            on_prompt(vault, event)
        else:
            on_stop(vault, event)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"Second Brain hook could not complete: {exc}", file=sys.stderr)
        print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
