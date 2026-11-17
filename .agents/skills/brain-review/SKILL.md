---
name: brain-review
description: Review a Second Brain Ledger vault for broken references, stale or conflicting claims, and storage growth.
---

Run `brain.py --vault <vault> check`, `size`, and `graph-audit`. Inspect recently changed pages and their cited sources. Report broken references, isolated wiki pages, decision pages without rationale, unsupported relationship rows, apparent contradictions, stale context, and unusual growth. Suggest specific edits with evidence; do not add filler links to satisfy the audit. Apply routine structural fixes when authorized by the task; leave uncertain factual reconciliation for user review. Rebuild the index after page changes. A sync service is not a backup, so report backup status only when it can be verified.
