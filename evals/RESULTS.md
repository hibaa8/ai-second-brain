# Retrieval smoke results — 2026-11-15

Command: `python3 evals/run.py` from the repository root.

| Measure | Result |
| --- | ---: |
| Expected cases passed | 8 / 8 |
| Search cases with expected page in top 3 | 4 / 4 |
| Search cases with expected page ranked first | 3 / 4 |
| Typed graph paths found within expected hops | 3 / 3 |
| Source text and registered hash verified | 1 / 1 |

The question “Who joined Project Orbit?” ranked the Orbit project page first and the Alex person page second. The recall skill therefore inspects several search hits instead of assuming the first is the answer. The current search uses OR terms and BM25; it is a candidate-page finder.

This is a four-page fictional vault, so these numbers are only a software smoke check. The runner does not ask Codex to generate answers, measure hallucinations, test stale facts, or compare against Codex's existing memory. The [paired eval protocol](README.md) describes that next step. The runner builds a temporary index; it does not update the vault or Codex memory settings.
