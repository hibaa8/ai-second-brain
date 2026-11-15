# Vault schema

## Source catalog

`raw/sources.jsonl` has one JSON object per original. `brain.py ingest` copies a file into `raw/objects/` and catalogs `id`, `title`, `location`, `sha256`, `bytes`, and `registered_at`. The ID is based on the content hash, so importing identical bytes again reuses the stored source. Files already under `raw/` are cataloged in place. If an external source was previously registered, ingestion upgrades its catalog entry to the stored copy while retaining `original_location`.

`brain.py source` is a reference-only alternative: it catalogs a file without copying it. Its absolute location can point to a separate private archive, but it is not a backup. `ingest` defaults to a 50 MB per-file limit; raise `--max-mb` deliberately for larger originals, or use a separately backed-up archive and `source`. The vault itself still needs backup.

For chats, `brain.py chat-import export.jsonl` accepts one JSON object per line with nonempty `thread_id`, `turn_id`, `role` (`user` or `assistant`), and `text`. Optional `item_id` distinguishes multiple messages of the same role in one turn; `created_at` and attachment metadata can be included. The importer stores immutable JSON under `raw/chats/`, cataloging each message as a source. Reimporting the same message is a no-op; changed content for the same message identity is a conflict that must be reviewed, rather than silently duplicated or overwritten. Store attached document bytes separately with `ingest` and link their source IDs from the wiki.

## Wiki pages

One durable topic per page, under `wiki/`. The `id` is its vault-relative path without `.md`. Use simple scalar frontmatter so the standard-library checker can parse it:

```markdown
---
id: wiki/projects/orbit
title: Project Orbit
kind: project
updated: 2026-11-15
sources: src-0123456789abcdef
---

# Project Orbit

A sourced summary. Cite the source ID near concrete claims.

## Relationships

| type | target | source | observed | status |
| --- | --- | --- | --- | --- |
| decided | [[wiki/decisions/orbit-launch]] | src-0123456789abcdef | 2026-11-15 | active |
```

`sources` is a comma-separated list of source IDs. The initial kinds are `person`, `project`, `topic`, and `decision`. `index.md` and `now.md` are navigation/context pages and do not need frontmatter.

## Relationship meaning

Allowed types initially: `works_on`, `part_of`, `decided`, `supersedes`, `related_to`. Allowed statuses: `active`, `superseded`, `withdrawn`. `observed` records when the relationship was learned, not necessarily when it became true. Record actual validity dates in prose until a real temporal query justifies more fields.

An Obsidian link alone means navigation, not a factual relationship. A typed row asserts a relationship and must cite a registered source. A correction should mark the earlier row `superseded` or `withdrawn` and add the current row. `walk` traverses only active rows. The original source and old row remain visible for review.

## Answer contract

Codex answers from the retrieved page and source evidence. It cites source IDs or page links for concrete statements, distinguishes a source claim from its own inference, and says when evidence is absent, stale, or contradictory. A graph path is a retrieval clue, not sufficient proof of an answer.

## Storage

The Obsidian vault holds Markdown, stored raw documents and chat messages, and a catalog. Large uploads may instead be referenced in a separate private archive. The SQLite index resides beside the vault and can be deleted and rebuilt. Use `brain.py size` to watch growth. Whole-file hashes deduplicate identical documents; stable message IDs deduplicate overlapping chat imports. Similar but nonidentical files remain separate until deliberately reviewed.
