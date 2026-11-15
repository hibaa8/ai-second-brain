# Evaluation

Run the read-only smoke eval with `python3 evals/run.py`. It checks whether full-text search returns expected pages, whether typed graph traversal reaches expected pages within a hop limit, and whether cited source text is available with the registered hash. It builds a temporary index and leaves the selected vault and its normal index untouched. The demo is tiny and fictional; its score is a software smoke check, not a measure of personal-memory effectiveness.

For each supported local turn, `evals/live.jsonl` in the private vault records offered pages and any source-backed page citations found in the final answer. `evals/usage.jsonl` and `evals/USAGE.md` retain the page, registered original, source-integrity result, and the surrounding claim. `evals/LIVE_REPORT.md` is regenerated after each completed turn and summarizes capture, retrieval, citation, and regression counts. This is a live attribution trace: retrieval is not counted as use, and use is not scored as correct merely because a citation appears. Review the original source when scoring the claim. An answer that uses the vault without citing it will be absent from this log, so citation coverage also needs auditing.

For example, a **fictional** answer that says the team chose a small pilot and cites `wiki/decisions/orbit-pilot` beside `src-80712d1c1265accb` creates a usage row with that claim and a hash check of the original. If the prompt hook merely offered the page, no usage row is created.

To run a private case set, keep its JSON outside this public repository and pass `--vault /path/to/private-vault --cases /path/to/private-cases.json`.

## Future paired answer eval

Use fresh chats with the same model and the same factual questions, while keeping Codex's existing memory settings unchanged in both conditions:

1. **Baseline:** ask the question without consulting Second Brain. Codex may use its existing memory and chat history as usual.
2. **Vault-assisted:** ask the same question and request the `brain-recall` workflow against the private vault.

Score the answers against the original source, not the wiki page. Record factual correctness, verified citations, unsupported claims, appropriate abstention, handling of corrections, latency, and retrieval effort. Randomize condition order and use held-out questions spanning direct facts, multi-hop relationships, changes over time, and facts absent from the vault. Do not use answer text from one condition as context for the other. A useful result is the **incremental benefit over Codex's existing memory**, including cases where the vault makes an answer worse.

The current CLI smoke eval does not execute Codex or assess generated answers. Local CLI and desktop turns have produced hook records in this setup; check `evals/live.jsonl` in the private vault for each completed turn. Hook telemetry and retrieval regressions still do not supply a personal-memory effectiveness score.

OpenAI [documents local Codex memories as a separate store and set of controls](https://learn.chatgpt.com/docs/customization/memories). This project does not call those controls or edit that store. Codex may still generate its own memories from eligible chats according to the user's existing settings; the paired eval leaves those settings unchanged.
