#!/usr/bin/env python3
"""Small, rebuildable index for an Obsidian second brain. Standard library only."""

from __future__ import annotations

import argparse
from collections import deque
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import tempfile


LINK = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
REL_TYPES = {"works_on", "part_of", "decided", "supersedes", "related_to"}
STATUSES = {"active", "superseded", "withdrawn"}
REQUIRED = {"id", "title", "kind", "updated", "sources"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_records(vault: Path) -> list[dict]:
    catalog = vault / "raw" / "sources.jsonl"
    if not catalog.exists():
        return []
    return [json.loads(line) for line in catalog.read_text().splitlines() if line.strip()]


def source_path(vault: Path, location: str) -> Path:
    path = Path(location)
    return path if path.is_absolute() else vault / path


def add_source(vault: Path, file: Path, title: str | None) -> dict:
    file = file.expanduser().resolve()
    if not file.is_file():
        raise ValueError(f"No such file: {file}")
    if file.is_relative_to((vault.expanduser().resolve() / "raw" / "inbox")):
        raise ValueError("Do not register a mutable hook inbox file directly. "
                         "After the turn completes, use `ingest` for an immutable copy.")
    digest = sha256(file)
    records = source_records(vault)
    for record in records:
        if record["sha256"] == digest:
            return {**record, "already_registered": True}
    try:
        location = str(file.relative_to(vault))
    except ValueError:
        location = str(file)
    record = {
        "id": f"src-{digest[:16]}",
        "title": title or file.name,
        "location": location,
        "sha256": digest,
        "bytes": file.stat().st_size,
        "registered_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    catalog = vault / "raw" / "sources.jsonl"
    catalog.parent.mkdir(parents=True, exist_ok=True)
    with catalog.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def write_source_records(vault: Path, records: list[dict]) -> None:
    catalog = vault / "raw" / "sources.jsonl"
    catalog.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=catalog.parent,
                                     delete=False) as stream:
        temporary = Path(stream.name)
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    try:
        os.replace(temporary, catalog)
    finally:
        temporary.unlink(missing_ok=True)


def ingest_file(vault: Path, file: Path, title: str | None = None,
                max_bytes: int = 50 * 1024 * 1024) -> dict:
    """Store one original in the private vault, reusing identical content."""
    vault = vault.expanduser().resolve()
    file = file.expanduser().resolve()
    if not file.is_file():
        raise ValueError(f"No such file: {file}")
    size = file.stat().st_size
    if size > max_bytes:
        raise ValueError(f"File is {size} bytes, above the {max_bytes} byte import limit. "
                         "Use --max-mb to raise it or `source` to reference an external archive.")
    digest = sha256(file)
    records = source_records(vault)
    existing = next((r for r in records if r["sha256"] == digest), None)
    raw = vault / "raw"
    immutable = (raw / "objects", raw / "chats")
    if existing and any(source_path(vault, existing["location"]).resolve().is_relative_to(root)
                        for root in immutable):
        if source_path(vault, existing["location"]).is_file():
            if sha256(source_path(vault, existing["location"])) != digest:
                raise ValueError(f"Stored source {existing['id']} changed since registration")
            return {**existing, "already_stored": True}
    if any(file.is_relative_to(root) for root in immutable):
        stored = file
    else:
        suffix = file.suffix.lower()
        if not re.fullmatch(r"\.[a-z0-9]{1,10}", suffix):
            suffix = ".bin"
        stored = raw / "objects" / digest[:2] / f"{digest}{suffix}"
        stored.parent.mkdir(parents=True, exist_ok=True)
        if not stored.exists():
            with tempfile.NamedTemporaryFile(dir=stored.parent, delete=False) as stream:
                temporary = Path(stream.name)
                with file.open("rb") as original:
                    shutil.copyfileobj(original, stream)
            try:
                if sha256(temporary) != digest:
                    raise ValueError("Source changed during import")
                os.replace(temporary, stored)
            finally:
                temporary.unlink(missing_ok=True)
        if sha256(stored) != digest:
            raise ValueError(f"Stored source collision or corruption: {stored}")
    location = str(stored.relative_to(vault))
    if existing:
        previous = existing["location"]
        if previous != location:
            existing["original_location"] = previous
            existing["location"] = location
            existing["stored_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            write_source_records(vault, records)
        return {**existing, "already_registered": True, "already_stored": False}
    record = add_source(vault, stored, title or file.name)
    return {**record, "already_stored": False}


def import_chat(vault: Path, export: Path) -> dict:
    """Import JSONL chat messages with stable thread and turn IDs."""
    messages = []
    # JSONL records are delimited by LF. splitlines() also splits Unicode line
    # separators that are valid characters inside a JSON string.
    for number, line in enumerate(export.read_text(encoding="utf-8").split("\n"), 1):
        if not line.strip():
            continue
        message = json.loads(line)
        for key in ("thread_id", "turn_id", "role", "text"):
            if not isinstance(message.get(key), str) or not message[key]:
                raise ValueError(f"Line {number}: missing string {key}")
        if message["role"] not in {"user", "assistant"}:
            raise ValueError(f"Line {number}: role must be user or assistant")
        messages.append(message)
    return import_chat_messages(vault, messages)


def import_chat_messages(vault: Path, messages: list[dict]) -> dict:
    """Store validated raw chat records once per stable message identity."""
    if not messages:
        raise ValueError("Chat export has no messages")
    prepared = {}
    for message in messages:
        for key in ("thread_id", "turn_id", "role", "text"):
            if not isinstance(message.get(key), str) or not message[key]:
                raise ValueError(f"Chat message missing string {key}")
        if message["role"] not in {"user", "assistant"}:
            raise ValueError("Chat message role must be user or assistant")
        identity = "\0".join(message[k] for k in ("thread_id", "turn_id", "role"))
        if message.get("item_id"):
            identity += "\0" + str(message["item_id"])
        thread = hashlib.sha256(message["thread_id"].encode()).hexdigest()[:16]
        turn = hashlib.sha256(identity.encode()).hexdigest()[:16]
        path = vault / "raw" / "chats" / thread / f"{turn}.json"
        data = (json.dumps(message, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")) + "\n").encode("utf-8")
        if path in prepared and prepared[path] != data:
            raise ValueError(f"Conflicting duplicate chat message in export: {identity}")
        if path.exists() and path.read_bytes() != data:
            raise ValueError(f"Chat message changed since import: {identity}")
        prepared[path] = data
    records = source_records(vault)
    known_hashes = {record["sha256"] for record in records}
    new_records = []
    registered_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    added = 0
    source_ids = []
    locations = []
    for path, data in prepared.items():
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
            try:
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
            added += 1
        digest = hashlib.sha256(data).hexdigest()
        source_ids.append(f"src-{digest[:16]}")
        locations.append(str(path.relative_to(vault)))
        if digest not in known_hashes:
            new_records.append({"id": f"src-{digest[:16]}",
                                "title": f"Chat message {path.stem}",
                                "location": str(path.relative_to(vault)),
                                "sha256": digest, "bytes": len(data),
                                "registered_at": registered_at})
            known_hashes.add(digest)
    if new_records:
        catalog = vault / "raw" / "sources.jsonl"
        catalog.parent.mkdir(parents=True, exist_ok=True)
        with catalog.open("a", encoding="utf-8") as stream:
            for record in new_records:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {"messages": len(prepared), "added": added,
            "already_present": len(prepared) - added, "source_ids": source_ids,
            "locations": locations}


def parse_page(path: Path) -> tuple[dict, str, list[dict], list[str]]:
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER.match(text)
    if not match:
        raise ValueError("missing YAML frontmatter")
    meta = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"invalid frontmatter line: {line}")
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip('"')
    missing = REQUIRED - meta.keys()
    if missing:
        raise ValueError(f"missing metadata: {', '.join(sorted(missing))}")
    body = text[match.end():]
    relations = []
    in_relations = False
    for line in body.splitlines():
        if line.startswith("## "):
            in_relations = line.strip() == "## Relationships"
            continue
        if not in_relations or not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 5 or cells[0] in ("type", "---") or set(cells[0]) == {"-"}:
            continue
        target = LINK.fullmatch(cells[1])
        relations.append({
            "type": cells[0], "target": target.group(1) if target else cells[1],
            "source": cells[2], "observed": cells[3], "status": cells[4],
            "link_valid": bool(target),
        })
    return meta, body, relations, LINK.findall(body)


def read_pages(vault: Path) -> list[dict]:
    result = []
    for path in sorted((vault / "wiki").rglob("*.md")):
        if path.name in {"index.md", "now.md"}:
            continue
        meta, body, relations, links = parse_page(path)
        result.append({"path": path, "meta": meta, "body": body,
                       "relations": relations, "links": links})
    return result


def validate(vault: Path, *, verify_hashes: bool = True) -> list[str]:
    errors = []
    records = source_records(vault)
    source_ids = [r.get("id") for r in records]
    if len(source_ids) != len(set(source_ids)):
        errors.append("raw/sources.jsonl: duplicate source ID")
    source_hashes = [r.get("sha256") for r in records]
    if len(source_hashes) != len(set(source_hashes)):
        errors.append("raw/sources.jsonl: duplicate source content")
    for record in records:
        path = source_path(vault, record["location"])
        if not path.is_file() and path.resolve().is_relative_to((vault / "raw").resolve()):
            errors.append(f"raw/sources.jsonl: stored source {record['id']} is missing")
        elif verify_hashes and path.is_file() and sha256(path) != record["sha256"]:
            errors.append(f"raw/sources.jsonl: source {record['id']} changed since registration")
    pages = []
    for path in sorted((vault / "wiki").rglob("*.md")):
        if path.name in {"index.md", "now.md"}:
            continue
        try:
            meta, body, relations, links = parse_page(path)
            pages.append((path, meta, body, relations, links))
        except (ValueError, UnicodeError) as exc:
            errors.append(f"{path.relative_to(vault)}: {exc}")
    page_ids = [meta["id"] for _, meta, _, _, _ in pages]
    if len(page_ids) != len(set(page_ids)):
        errors.append("wiki: duplicate page ID")
    known = set(page_ids)
    for path, meta, body, relations, links in pages:
        label = str(path.relative_to(vault))
        expected = path.relative_to(vault).with_suffix("").as_posix()
        if meta["id"] != expected:
            errors.append(f"{label}: id should be {expected}")
        try:
            date.fromisoformat(meta["updated"])
        except ValueError:
            errors.append(f"{label}: invalid updated date")
        declared_sources = {s.strip() for s in meta["sources"].split(",") if s.strip()}
        for source in declared_sources:
            if source not in source_ids:
                errors.append(f"{label}: unknown source {source}")
        for source in set(re.findall(r"`(src-[0-9a-f]{16})`", body)):
            if source not in source_ids:
                errors.append(f"{label}: unknown cited source {source}")
            elif source not in declared_sources:
                errors.append(f"{label}: cited source {source} missing from frontmatter")
        for target in links:
            if target not in known:
                errors.append(f"{label}: broken link [[{target}]]")
        for rel in relations:
            if rel["type"] not in REL_TYPES:
                errors.append(f"{label}: unknown relation type {rel['type']}")
            if not rel["link_valid"] or rel["target"] not in known:
                errors.append(f"{label}: invalid relationship target {rel['target']}")
            if rel["source"] not in source_ids:
                errors.append(f"{label}: unknown relationship source {rel['source']}")
            if rel["status"] not in STATUSES:
                errors.append(f"{label}: invalid relationship status {rel['status']}")
            try:
                date.fromisoformat(rel["observed"])
            except ValueError:
                errors.append(f"{label}: invalid relationship date {rel['observed']}")
    return errors


def db_path(vault: Path) -> Path:
    return vault.parent / ".brain-index" / f"{vault.name}.sqlite3"


def chat_titles(vault: Path) -> dict[str, str]:
    path = vault / "raw" / "chat_threads.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {thread: item.get("title", "") for thread, item in data.items()}


def build_index(vault: Path) -> dict:
    errors = validate(vault)
    if errors:
        raise ValueError("\n".join(errors))
    pages = read_pages(vault)
    target = db_path(vault)
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(target) as db:
        db.executescript("""
            DROP TABLE IF EXISTS pages_fts;
            DROP TABLE IF EXISTS chats_fts;
            DROP TABLE IF EXISTS chats;
            DROP TABLE IF EXISTS edges;
            DROP TABLE IF EXISTS pages;
            CREATE TABLE pages(id TEXT PRIMARY KEY, title TEXT, kind TEXT, updated TEXT, path TEXT, body TEXT);
            CREATE VIRTUAL TABLE pages_fts USING fts5(id UNINDEXED, title, body);
            CREATE TABLE chats(source_id TEXT PRIMARY KEY, thread_id TEXT, title TEXT, created_at TEXT, role TEXT, path TEXT, body TEXT);
            CREATE VIRTUAL TABLE chats_fts USING fts5(source_id UNINDEXED, title, body);
            CREATE TABLE edges(origin TEXT, relation TEXT, target TEXT, source TEXT, observed TEXT, status TEXT);
            CREATE INDEX edges_origin ON edges(origin);
            CREATE INDEX edges_target ON edges(target);
        """)
        for page in pages:
            meta = page["meta"]
            row = (meta["id"], meta["title"], meta["kind"], meta["updated"],
                   str(page["path"]), page["body"])
            db.execute("INSERT INTO pages VALUES (?,?,?,?,?,?)", row)
            db.execute("INSERT INTO pages_fts VALUES (?,?,?)", (meta["id"], meta["title"], page["body"]))
            for rel in page["relations"]:
                db.execute("INSERT INTO edges VALUES (?,?,?,?,?,?)",
                           (meta["id"], rel["type"], rel["target"], rel["source"],
                            rel["observed"], rel["status"]))
        chat_count = 0
        titles = chat_titles(vault)
        for record in source_records(vault):
            if not record["location"].startswith("raw/chats/"):
                continue
            path = source_path(vault, record["location"])
            message = json.loads(path.read_text(encoding="utf-8"))
            title = titles.get(message["thread_id"], "")
            row = (record["id"], message["thread_id"], title, message.get("created_at", ""),
                   message["role"], str(path), message["text"])
            db.execute("INSERT INTO chats VALUES (?,?,?,?,?,?,?)", row)
            db.execute("INSERT INTO chats_fts VALUES (?,?,?)", (record["id"], title, message["text"]))
            chat_count += 1
        db.commit()
        edge_count = db.execute("SELECT count(*) FROM edges").fetchone()[0]
    return {"pages": len(pages), "edges": edge_count, "chats": chat_count,
            "index": str(target)}


def connect_index(vault: Path) -> sqlite3.Connection:
    target = db_path(vault)
    if not target.exists():
        raise ValueError("Index missing. Run: brain.py --vault VAULT index")
    db = sqlite3.connect(target)
    db.row_factory = sqlite3.Row
    return db


def refresh_chat_index(vault: Path) -> dict:
    """Add newly registered immutable chats without rebuilding the wiki index."""
    with connect_index(vault) as db:
        existing = {row[0] for row in db.execute("SELECT source_id FROM chats")}
        titles = chat_titles(vault)
        added = 0
        for record in source_records(vault):
            if not record["location"].startswith("raw/chats/") or record["id"] in existing:
                continue
            path = source_path(vault, record["location"])
            if not path.is_file() or sha256(path) != record["sha256"]:
                raise ValueError(f"New chat source missing or changed: {record['id']}")
            message = json.loads(path.read_text(encoding="utf-8"))
            title = titles.get(message["thread_id"], "")
            db.execute("INSERT INTO chats VALUES (?,?,?,?,?,?,?)",
                       (record["id"], message["thread_id"], title, message.get("created_at", ""),
                        message["role"], str(path), message["text"]))
            db.execute("INSERT INTO chats_fts VALUES (?,?,?)", (record["id"], title, message["text"]))
            added += 1
        db.commit()
        return {"added": added, "indexed": len(existing) + added}


def refresh_wiki_index(vault: Path) -> dict:
    """Refresh curated pages and graph edges without reindexing raw chats."""
    errors = validate(vault, verify_hashes=False)
    if errors:
        raise ValueError("\n".join(errors))
    pages = read_pages(vault)
    with connect_index(vault) as db:
        db.execute("DELETE FROM pages_fts")
        db.execute("DELETE FROM edges")
        db.execute("DELETE FROM pages")
        edge_count = 0
        for page in pages:
            meta = page["meta"]
            db.execute("INSERT INTO pages VALUES (?,?,?,?,?,?)",
                       (meta["id"], meta["title"], meta["kind"], meta["updated"],
                        str(page["path"]), page["body"]))
            db.execute("INSERT INTO pages_fts VALUES (?,?,?)",
                       (meta["id"], meta["title"], page["body"]))
            for relation in page["relations"]:
                db.execute("INSERT INTO edges VALUES (?,?,?,?,?,?)",
                           (meta["id"], relation["type"], relation["target"], relation["source"],
                            relation["observed"], relation["status"]))
                edge_count += 1
        db.commit()
    return {"pages": len(pages), "edges": edge_count}


def search(vault: Path, query: str, limit: int = 10) -> list[dict]:
    terms = re.findall(r"[\w-]+", query, re.UNICODE)
    if not terms:
        return []
    expression = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
    with connect_index(vault) as db:
        rows = db.execute("""
            SELECT p.id, p.title, p.kind, p.updated, p.path,
                   snippet(pages_fts, 2, '[', ']', ' … ', 18) AS excerpt,
                   bm25(pages_fts, 0.0, 4.0, 1.0) AS rank
            FROM pages_fts JOIN pages p ON p.id = pages_fts.id
            WHERE pages_fts MATCH ? ORDER BY rank LIMIT ?
        """, (expression, limit)).fetchall()
        return [dict(row) for row in rows]


def search_chats(vault: Path, query: str, limit: int = 10, role: str = "user") -> list[dict]:
    """Search registered original chat text, keeping role and source identity."""
    terms = re.findall(r"[^\W_]{3,}", query, re.UNICODE)
    if not terms:
        return []
    expression = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
    with connect_index(vault) as db:
        rows = db.execute("""
            SELECT c.source_id, c.thread_id, c.title, c.created_at, c.role, c.path,
                   snippet(chats_fts, 2, '[', ']', ' … ', 24) AS excerpt,
                   bm25(chats_fts, 0.0, 2.0, 4.0) AS rank
            FROM chats_fts JOIN chats c ON c.source_id = chats_fts.source_id
            WHERE chats_fts MATCH ? AND c.role = ? ORDER BY rank LIMIT ?
        """, (expression, role, limit)).fetchall()
        return [dict(row) for row in rows]


def walk(vault: Path, seed: str, hops: int = 2, limit: int = 30) -> list[dict]:
    if hops < 1 or hops > 3 or limit < 1 or limit > 100:
        raise ValueError("hops must be 1–3 and limit 1–100")
    with connect_index(vault) as db:
        if not db.execute("SELECT 1 FROM pages WHERE id=?", (seed,)).fetchone():
            raise ValueError(f"Unknown page: {seed}")
        rows = [dict(row) for row in db.execute("SELECT * FROM edges WHERE status='active'")]
        adjacent: dict[str, list[dict]] = {}
        for edge in rows:
            adjacent.setdefault(edge["origin"], []).append({**edge, "next": edge["target"], "direction": "out"})
            adjacent.setdefault(edge["target"], []).append({**edge, "next": edge["origin"], "direction": "in"})
        queue = deque([(seed, [])])
        seen = {seed}
        found = []
        while queue and len(found) < limit:
            current, path = queue.popleft()
            if len(path) >= hops:
                continue
            for edge in sorted(adjacent.get(current, []), key=lambda x: (x["next"], x["relation"])):
                nxt = edge["next"]
                if nxt in seen:
                    continue
                seen.add(nxt)
                step = {key: edge[key] for key in ("origin", "relation", "target", "source", "observed", "direction")}
                trail = path + [step]
                found.append({"page": nxt, "hops": len(trail), "path": trail})
                if len(found) >= limit:
                    break
                queue.append((nxt, trail))
        return found


def size_report(vault: Path) -> dict:
    files = [p for p in vault.rglob("*") if p.is_file() and ".git" not in p.parts]
    vault_bytes = sum(p.stat().st_size for p in files)
    external = {}
    for record in source_records(vault):
        path = source_path(vault, record["location"])
        if not path.is_relative_to(vault) and path.is_file():
            external[str(path)] = path.stat().st_size
    largest = sorted(files, key=lambda p: p.stat().st_size, reverse=True)[:5]
    return {"vault_bytes": vault_bytes, "external_source_bytes": sum(external.values()),
            "source_count": len(source_records(vault)),
            "largest_vault_files": [{"path": str(p.relative_to(vault)), "bytes": p.stat().st_size} for p in largest],
            "index_bytes": db_path(vault).stat().st_size if db_path(vault).exists() else 0}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", type=Path, required=True, help="Path to an Obsidian vault")
    commands = parser.add_subparsers(dest="command", required=True)
    source_cmd = commands.add_parser("source", help="Reference a raw source without copying it")
    source_cmd.add_argument("file", type=Path)
    source_cmd.add_argument("--title")
    ingest_cmd = commands.add_parser("ingest", help="Copy a document or chat export into the private vault, deduplicated by content")
    ingest_cmd.add_argument("file", type=Path)
    ingest_cmd.add_argument("--title")
    ingest_cmd.add_argument("--max-mb", type=int, default=50)
    chat_cmd = commands.add_parser("chat-import", help="Store JSONL chat messages once per thread/turn/role/item ID")
    chat_cmd.add_argument("file", type=Path)
    commands.add_parser("check", help="Validate pages, sources, and typed relationships")
    commands.add_parser("index", help="Rebuild the disposable SQLite search and graph index")
    find_cmd = commands.add_parser("search", help="Search wiki pages by exact words")
    find_cmd.add_argument("query")
    find_cmd.add_argument("--limit", type=int, default=10)
    walk_cmd = commands.add_parser("walk", help="Traverse active typed relationships")
    walk_cmd.add_argument("page_id")
    walk_cmd.add_argument("--hops", type=int, default=2)
    walk_cmd.add_argument("--limit", type=int, default=30)
    commands.add_parser("size", help="Report vault, archive-reference, and index size")
    args = parser.parse_args()
    vault = args.vault.expanduser().resolve()
    if not vault.is_dir():
        parser.error(f"Vault directory does not exist: {vault}")
    try:
        if args.command == "source":
            result = add_source(vault, args.file, args.title)
        elif args.command == "ingest":
            if args.max_mb < 1:
                raise ValueError("--max-mb must be positive")
            result = ingest_file(vault, args.file, args.title, args.max_mb * 1024 * 1024)
        elif args.command == "chat-import":
            result = {key: value for key, value in import_chat(vault, args.file).items()
                      if key not in {"source_ids", "locations"}}
        elif args.command == "check":
            errors = validate(vault)
            result = {"ok": not errors, "errors": errors}
        elif args.command == "index":
            result = build_index(vault)
        elif args.command == "search":
            result = search(vault, args.query, args.limit)
        elif args.command == "walk":
            result = walk(vault, args.page_id, args.hops, args.limit)
        else:
            result = size_report(vault)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1 if args.command == "check" and not result["ok"] else 0
    except (ValueError, OSError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
