---
name: brain-recall
description: Answer a question using the personal Second Brain Ledger vault with source citations and optional typed relationship traversal.
---

Find the vault path from the current project context. Read its `wiki/now.md` only when recent context matters. Run `brain.py --vault <vault> search <question>` to find seed pages. For a relationship or multi-hop question, run `walk` from a relevant page with at most two hops initially. Open only the returned pages and the source records needed to verify concrete claims. Synthesize a direct answer with page or source citations. State missing, stale, or conflicting evidence. A graph edge is a retrieval clue; verify it against its cited source before presenting it as fact. Do not write to the vault during recall unless the user asks to keep the result.

Inspect several search hits before choosing a seed page; the top-ranked page may describe the question's subject rather than contain its answer. Treat the vault as additional evidence alongside Codex's existing memory, and prefer an explicit user correction when the two conflict.
