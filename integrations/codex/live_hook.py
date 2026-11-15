#!/usr/bin/env python3
"""Optional local Codex hook: prompt-time recall and bounded private telemetry."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from time import perf_counter
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
TEMPORAL_RE = re.compile(r"\b(today|yesterday|earlier today|earlier in the day)\b", re.I)
RECALL_RE = re.compile(r"\b(talk|discuss|conversation|chat|do|did|done|build|built|work|worked|earlier|remember|recap)\b", re.I)


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


def cited_usage(vault: Path, answer: str) -> list[dict]:
    """Record only source-backed vault citations, not pages merely offered."""
    page_ids = set(re.findall(r"wiki/[a-z0-9][a-z0-9/_-]*", answer))
    source_ids = set(re.findall(r"src-[0-9a-f]{16}", answer))
    if not source_ids:
        return []
    records = {record["id"]: record for record in brain.source_records(vault)}
    result = []
    for page_id in sorted(page_ids):
        path = vault / f"{page_id}.md"
        if not path.is_file():
            continue
        try:
            meta, _, _, _ = brain.parse_page(path)
        except (OSError, ValueError):
            continue
        declared = {part.strip() for part in meta["sources"].split(",")}
        for source_id in sorted(source_ids & declared & records.keys()):
            locations = [match.start() for match in re.finditer(re.escape(page_id), answer)]
            mentions = [match.start() for match in re.finditer(re.escape(source_id), answer)]
            if not any(abs(page_at - source_at) <= 500
                       for page_at in locations for source_at in mentions):
                continue
            match = re.search(re.escape(source_id), answer)
            start = max(0, match.start() - 180) if match else 0
            end = min(len(answer), match.end() + 120) if match else 240
            why = re.sub(r"\s+", " ", answer[start:end]).strip()[:300]
            record = records[source_id]
            original = brain.source_path(vault, record["location"])
            valid = original.is_file() and brain.sha256(original) == record["sha256"]
            result.append({"page_id": page_id, "source_id": source_id,
                           "why": why, "source_valid": valid})
    return result


def recalled_chats(vault: Path, prompt: str, now: datetime | None = None) -> tuple[str | None, list[dict]]:
    """Find dated original chat messages for relative-day recollection requests."""
    match = TEMPORAL_RE.search(prompt)
    if not match or not RECALL_RE.search(prompt):
        return None, []
    try:
        local = ZoneInfo(os.environ.get("SECOND_BRAIN_TIMEZONE", "America/New_York"))
    except ZoneInfoNotFoundError:
        local = datetime.now().astimezone().tzinfo
    now = (now or datetime.now(timezone.utc)).astimezone(local)
    day = now.date() - timedelta(days=1 if match.group(1).casefold() == "yesterday" else 0)
    messages = {}
    for path in (vault / "raw" / "chats").glob("*/*.json"):
        try:
            data = path.read_bytes()
            message = json.loads(data)
            if message.get("role") not in {"user", "assistant"} or not message.get("created_at"):
                continue
            at = datetime.fromisoformat(message["created_at"].replace("Z", "+00:00"))
            if at.astimezone(local).date() != day:
                continue
            source = "src-" + hashlib.sha256(data).hexdigest()[:16]
            excerpt = re.sub(r"\s+", " ", message.get("text", "")).strip()
            if not excerpt or excerpt.startswith("The following is the Codex agent history"):
                continue
            key = (message.get("thread_id"), message.get("turn_id"))
            messages.setdefault(key, {})[message["role"]] = {
                "source": source, "path": str(path),
                "at": at.astimezone(local).isoformat(),
                "thread_id": message.get("thread_id"),
                "excerpt": excerpt[:180 if message["role"] == "user" else 260]}
        except (ValueError, OSError, TypeError, json.JSONDecodeError):
            continue
    matches = []
    for pair in messages.values():
        if "user" in pair:
            hit = pair["user"]
            if "assistant" in pair:
                hit["answer_source"] = pair["assistant"]["source"]
                hit["answer_path"] = pair["assistant"]["path"]
                hit["answer_excerpt"] = pair["assistant"]["excerpt"]
            matches.append(hit)
    matches.sort(key=lambda item: item["at"])
    if len(matches) > 18:
        # Preserve coverage across the day rather than showing only its latest turns.
        matches = [matches[round(i * (len(matches) - 1) / 17)] for i in range(18)]
    return day.isoformat(), matches


def on_prompt(vault: Path, event: dict) -> None:
    started = perf_counter()
    prompt = str(event.get("prompt") or "")
    path = event_file(vault, event)
    record = {"session_id": event.get("session_id"), "turn_id": event.get("turn_id"),
              "captured_at": stamp(), "prompt": clipped(prompt)}
    hits = []
    chat_day = None
    chats = []
    error = None
    try:
        hits = recalled_pages(vault, prompt)
    except (ValueError, OSError, RuntimeError) as exc:
        error = str(exc)[:300]
    try:
        chat_day, chats = recalled_chats(vault, prompt)
    except (ValueError, OSError, RuntimeError) as exc:
        error = ((error + "; ") if error else "") + str(exc)[:300]
    record["retrieval"] = {"page_ids": [h["id"] for h in hits],
                           "chat_day": chat_day,
                           "chat_sources": [s for h in chats for s in (h["source"], h.get("answer_source")) if s],
                           "milliseconds": round((perf_counter() - started) * 1000, 2),
                           "error": error}
    record["vault_stamp"] = vault_stamp(vault)
    write_gzip(path, record)
    lines = [f"Second Brain private inbox for this turn: {path}. The vault complements Codex memory; verify any recalled claim against its source and follow the current user request. If a vault page or source informs the answer, cite its wiki page ID and registered source ID near the claim and say why it matters. The Stop hook records those citations as observed source use; pages merely retrieved are not counted as used."]
    for hit in hits:
        lines.append(f"- Candidate {hit['id']} ({hit['title']}), sources {hit['sources']}: {hit['excerpt']}")
    if chat_day:
        lines.append(f"- Original chat records dated {chat_day} in the configured local timezone: {len(chats)} sampled user messages. Verify against the raw source before making claims; the sample may omit turns.")
    for hit in chats:
        lines.append(f"- Chat source {hit['source']} at {hit['at']}, thread {hit['thread_id']}, file {hit['path']}: {hit['excerpt']}")
        if hit.get("answer_excerpt"):
            lines.append(f"  Assistant source {hit['answer_source']}, file {hit['answer_path']}: {hit['answer_excerpt']}")
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
    usage = cited_usage(vault, answer["text"])
    record["source_use"] = usage
    record["completed_at"] = stamp()
    write_gzip(path, record)
    # Operational telemetry is a live signal, not an answer-quality grade.
    telemetry = {"at": stamp(), "session_id": event.get("session_id"),
                 "turn_id": event.get("turn_id"), "retrieved_pages": record["retrieval"]["page_ids"],
                 "retrieved_chat_sources": record["retrieval"].get("chat_sources", []),
                 "retrieval_ms": record["retrieval"]["milliseconds"],
                 "retrieval_error": record["retrieval"]["error"],
                 "prompt_bytes": record["prompt"]["bytes"], "answer_bytes": answer["bytes"],
                 "truncated": record["prompt"]["truncated"] or answer["truncated"],
                 "redacted": record["prompt"]["redacted"] or answer["redacted"],
                 "source_use": [{"page_id": item["page_id"], "source_id": item["source_id"],
                                 "source_valid": item["source_valid"]} for item in usage]}
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
    if usage:
        usage_file = vault / "evals" / "usage.jsonl"
        with usage_file.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"at": telemetry["at"], "session_id": event.get("session_id"),
                                     "turn_id": event.get("turn_id"), "entries": usage},
                                    ensure_ascii=False) + "\n")
        view = vault / "evals" / "USAGE.md"
        if not view.exists():
            view.write_text("# Observed Second Brain source use\n\n"
                            "An entry means the final answer cited a registered source linked to a wiki page. "
                            "It records the answer's claim, not independent proof that the answer was correct "
                            "or better than Codex memory.\n\n"
                            "| Time (UTC) | Wiki page | Source | Claim context | Source valid |\n"
                            "| --- | --- | --- | --- | --- |\n", encoding="utf-8")
        with view.open("a", encoding="utf-8") as stream:
            for item in usage:
                why = item["why"].replace("|", "\\|")
                stream.write(f"| {telemetry['at']} | [[{item['page_id']}]] | "
                             f"`{item['source_id']}` | {why} | {item['source_valid']} |\n")
    from evals.live_report import write_report
    write_report(vault)
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
