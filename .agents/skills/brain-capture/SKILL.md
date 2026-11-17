---
name: brain-capture
description: Register a chosen chat or document and update source-backed pages in a private Second Brain Ledger vault.
---

Use this when the user asks to remember, ingest, or update the private vault from a particular source. Store an available original with `brain.py --vault <vault> ingest <file>`. Use `source` only when the original already lives in a separately backed-up private archive. Read the source and relevant existing pages. Propose only durable facts, corrections, decisions, preferences, and useful relationships; ordinary chat text need not become wiki content. Cite registered source IDs. For decision pages, record why the decision was made and any alternatives the original actually discusses; mark missing rationale as unknown instead of inventing it. For relationships use the table in `SCHEMA.md`, recording the observation date and status. Preserve prior claims when correcting them. Run `check`, `graph-audit`, and rebuild `index`; report the changed pages and any unresolved contradictions. Do not import other chats, accounts, or external services merely because they are available.

This skill writes only to the selected vault. It does not change Codex memory settings or saved memories. Treat an explicit user correction as newer evidence and record it with its source.

For each substantive new page or relationship, add a private retrieval or relationship case to `evals/cases.json` using a question grounded in the original source, then run `evals/run.py` and report the case count and failures. These are regression cases, not an independent measure of answer quality.
