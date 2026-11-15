# Vault schema

## Source catalog

`raw/sources.jsonl` has one JSON object per original. `brain.py source` appends records with `id`, `title`, `location`, `sha256`, `bytes`, and `registered_at`. The ID is based on the content hash, so a second registration of identical bytes reuses the same source. A relative location is resolved from the vault root; an absolute location points to an external private archive.

Registration catalogs a source; it does not move, copy, or back it up. Keep originals in an independently backed-up location.

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

The Obsidian vault holds Markdown and a catalog of originals. Large uploads and full chat exports may be kept in a private archive outside the vault. The SQLite index resides beside the vault and can be deleted and rebuilt. Use `brain.py size` to watch growth.
