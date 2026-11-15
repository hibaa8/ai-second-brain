---
name: brain-capture
description: Register a chosen chat or document and update source-backed pages in a private Second Brain Ledger vault.
---

Use this when the user asks to remember, ingest, or update the private vault from a particular source. Register the original with `brain.py --vault <vault> source <file>` when it exists locally. Read the source and relevant existing pages. Propose only durable facts, corrections, decisions, preferences, and useful relationships; ordinary chat text need not become wiki content. Cite registered source IDs. For relationships use the table in `SCHEMA.md`, recording the observation date and status. Preserve prior claims when correcting them. Run `check` and rebuild `index`; report the changed pages and any unresolved contradictions. Do not import other chats, accounts, or external services merely because they are available.

This skill writes only to the selected vault. It does not change Codex memory settings or saved memories. Treat an explicit user correction as newer evidence and record it with its source.
