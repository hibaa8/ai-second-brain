# Vault schema

The disposable SQLite index contains both curated wiki pages and registered original chat messages. Prompt-hook recall searches the wiki first, then offers bounded topical original user messages when no wiki or dated-chat candidate matches. Raw-chat search results retain their registered source IDs for citation and usage tracking.

An optional private `raw/chat_threads.json` maps stable thread IDs to `{ "title": "...", "created_at": "..." }`. The index uses these titles alongside original message text. Newly registered chats and edited wiki pages can refresh their portions of the index independently; a full rebuild remains available for recovery. Asset manifests can map exported attachment IDs to stored source IDs or members of a separate private archive. The archive itself needs a backup.

## Source catalog

`raw/sources.jsonl` has one JSON object per original. `brain.py ingest` copies a file into `raw/objects/` and catalogs `id`, `title`, `location`, `sha256`, `bytes`, and `registered_at`. The ID is based on the content hash, so importing identical bytes again reuses the stored source. Files already under immutable `raw/objects/` or `raw/chats/` are cataloged in place. Other files under `raw/`, including hook inbox records, are copied before registration because they may still change. If an external source was previously registered, ingestion upgrades its catalog entry to the stored copy while retaining `original_location`.

`brain.py source` is a reference-only alternative: it catalogs a file without copying it. Its absolute location can point to a separate private archive, but it is not a backup. `ingest` defaults to a 50 MB per-file limit; raise `--max-mb` deliberately for larger originals, or use a separately backed-up archive and `source`. The vault itself still needs backup.

For chats, `brain.py chat-import export.jsonl` accepts one JSON object per line with nonempty `thread_id`, `turn_id`, `role` (`user` or `assistant`), and `text`. Optional `item_id` distinguishes multiple messages of the same role in one turn; `created_at` and attachment metadata can be included. The importer stores immutable JSON under `raw/chats/`, cataloging each message as a source. Reimporting the same message is a no-op; changed content for the same message identity is a conflict that must be reviewed, rather than silently duplicated or overwritten. Store attached document bytes separately with `ingest` and link their source IDs from the wiki.

`tools/chatgpt_export.py export.zip --vault VAULT` reads `conversations.json` or split `conversations-000.json` parts directly from a ChatGPT export ZIP and feeds supported user and assistant text turns through the same importer. It also updates `raw/chat_threads.json` so conversation titles are searchable. Reasoning, tool messages, and non-text attachment bytes are outside this text import. The original ZIP is not stored by this command; keep it separately if needed.

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

For a decision page, add `## Why` and `## Alternatives considered` when the originals support them. A missing reason is an evidence gap, not permission to infer one. `brain.py graph-audit` lists isolated pages and decision pages lacking a rationale section so the agent can review them. The audit does not require arbitrary links or change validation status.

## Answer contract

Codex answers from the retrieved page and source evidence. It cites source IDs or page links for concrete statements, distinguishes a source claim from its own inference, and says when evidence is absent, stale, or contradictory. A graph path is a retrieval clue, not sufficient proof of an answer.

`brain.py context '<question>'` packages the top wiki hits, up to one hop of active typed relationships, and up to two matching original chats. It reports why each page was selected and checks the registered hashes of cited originals. It is a bounded navigation aid; the agent still reads the original before stating a personal fact.

## Storage

The Obsidian vault holds Markdown, stored raw documents and chat messages, and a catalog. Large uploads may instead be referenced in a separate private archive. The SQLite index resides beside the vault and can be deleted and rebuilt. Use `brain.py size` to watch growth. Whole-file hashes deduplicate identical documents; stable message IDs deduplicate overlapping chat imports. Similar but nonidentical files remain separate until deliberately reviewed.

`brain.py stats` reports the count of title-cataloged threads, registered chat messages, wiki pages, typed relationship rows, registered sources, vault bytes, and disposable index bytes. The title-cataloged count comes from optional `raw/chat_threads.json`; it is zero for vaults that only contain local hook chats without an imported title catalog.
