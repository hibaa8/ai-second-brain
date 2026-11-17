---
name: brain-recall
description: Answer a question using the personal Second Brain Ledger vault with source citations and optional typed relationship traversal.
---

Find the vault path from the current project context. Read its `wiki/now.md` only when recent context matters. Run `brain.py --vault <vault> context <question>` for a bounded pack of search hits, one-hop typed graph neighbors, and matching original chats. Inspect its source hash checks, then open the originals needed to verify concrete claims. Use `search` or `walk` for a narrower or deeper follow-up, with at most two hops initially. Synthesize a direct answer with page and original-source citations. State missing, stale, or conflicting evidence. A graph edge is a retrieval clue; verify it against its cited source before presenting it as fact. Do not write to the vault during recall unless the user asks to keep the result.

Inspect several search hits before choosing a seed page; the top-ranked page may describe the question's subject rather than contain its answer. Treat the vault as additional evidence alongside Codex's existing memory, and prefer an explicit user correction when the two conflict.
