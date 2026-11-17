#!/usr/bin/env python3
"""Import text turns from a ChatGPT data export into a private Second Brain vault."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import tempfile
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import brain  # noqa: E402


PART_RE = re.compile(r"(?:^|/)conversations-(\d+)\.json$")


def export_members(names: list[str]) -> list[str]:
    parts = sorted(((int(match.group(1)), name) for name in names
                    if (match := PART_RE.search(name))))
    if parts:
        return [name for _, name in parts]
    single = [name for name in names if name == "conversations.json"
              or name.endswith("/conversations.json")]
    if len(single) == 1:
        return single
    raise ValueError("No conversations.json or conversations-000.json parts found")


def timestamp(value: object) -> str | None:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="seconds")
    return value if isinstance(value, str) and value else None


def text_parts(content: dict) -> str:
    if content.get("content_type") not in {"text", "multimodal_text"}:
        return ""
    return "\n".join(part for part in content.get("parts", []) if isinstance(part, str)).strip()


def messages_from_conversation(conversation: dict) -> list[dict]:
    thread_id = conversation.get("id") or conversation.get("conversation_id")
    if not isinstance(thread_id, str) or not thread_id:
        return []
    messages = []
    for node_id, node in (conversation.get("mapping") or {}).items():
        message = node.get("message") or {}
        role = (message.get("author") or {}).get("role")
        if role not in {"user", "assistant"}:
            continue
        body = text_parts(message.get("content") or {})
        if not body:
            continue
        record = {"thread_id": thread_id,
                  "turn_id": str(message.get("id") or node_id),
                  "item_id": str(node_id), "role": role, "text": body,
                  "origin": "chatgpt-export"}
        created = timestamp(message.get("create_time"))
        if created:
            record["created_at"] = created
        messages.append(record)
    return messages


def import_export(vault: Path, archive: Path) -> dict:
    if not (vault / "wiki").is_dir():
        raise ValueError("Initialize the private vault with `brain.py init` first")
    totals = {"conversations": 0, "text_messages": 0, "added_messages": 0,
              "already_present": 0, "non_text_messages_skipped": 0}
    titles_path = vault / "raw" / "chat_threads.json"
    titles = json.loads(titles_path.read_text(encoding="utf-8")) if titles_path.exists() else {}
    with ZipFile(archive) as zip_file:
        for member in export_members(zip_file.namelist()):
            conversations = json.load(zip_file.open(member))
            if not isinstance(conversations, list):
                raise ValueError(f"Expected a list in {member}")
            batch = []
            for conversation in conversations:
                thread_id = conversation.get("id") or conversation.get("conversation_id")
                if not isinstance(thread_id, str) or not thread_id:
                    continue
                totals["conversations"] += 1
                title = conversation.get("title")
                if isinstance(title, str) and title.strip():
                    titles[thread_id] = {"title": title.strip(),
                                         "created_at": timestamp(conversation.get("create_time")),
                                         "origin": "chatgpt-export"}
                messages = messages_from_conversation(conversation)
                for node in (conversation.get("mapping") or {}).values():
                    message = node.get("message") or {}
                    if (message.get("author") or {}).get("role") in {"user", "assistant"} and not text_parts(message.get("content") or {}):
                        totals["non_text_messages_skipped"] += 1
                batch.extend(messages)
            if batch:
                result = brain.import_chat_messages(vault, batch)
                totals["text_messages"] += result["messages"]
                totals["added_messages"] += result["added"]
                totals["already_present"] += result["already_present"]
    titles_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=titles_path.parent,
                                     delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(titles, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    temporary.replace(titles_path)
    totals["cataloged_chat_threads"] = len(titles)
    return totals


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="ChatGPT data export ZIP")
    parser.add_argument("--vault", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = import_export(args.vault.expanduser().resolve(), args.archive.expanduser().resolve())
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
