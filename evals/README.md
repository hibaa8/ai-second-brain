# Evaluation

Run the read-only smoke eval with `python3 evals/run.py`. It checks whether full-text search returns expected pages, whether typed graph traversal reaches expected pages within a hop limit, and whether cited source text is available with the registered hash. It builds a temporary index and leaves the selected vault and its normal index untouched. The demo is tiny and fictional; its score is a software smoke check, not a measure of personal-memory effectiveness.

To run a private case set, keep its JSON outside this public repository and pass `--vault /path/to/private-vault --cases /path/to/private-cases.json`.

## Future paired answer eval

Use fresh chats with the same model and the same factual questions, while keeping Codex's existing memory settings unchanged in both conditions:

1. **Baseline:** ask the question without consulting Second Brain. Codex may use its existing memory and chat history as usual.
2. **Vault-assisted:** ask the same question and request the `brain-recall` workflow against the private vault.

Score the answers against the original source, not the wiki page. Record factual correctness, verified citations, unsupported claims, appropriate abstention, handling of corrections, latency, and retrieval effort. Randomize condition order and use held-out questions spanning direct facts, multi-hop relationships, changes over time, and facts absent from the vault. Do not use answer text from one condition as context for the other. A useful result is the **incremental benefit over Codex's existing memory**, including cases where the vault makes an answer worse.

The current CLI smoke eval does not execute Codex or assess generated answers. Fresh-chat access through global guidance has been verified in one local session; automatic hook capture still needs an observed trusted-hook run before a personal-memory score is meaningful.

OpenAI [documents local Codex memories as a separate store and set of controls](https://learn.chatgpt.com/docs/customization/memories). This project does not call those controls or edit that store. Codex may still generate its own memories from eligible chats according to the user's existing settings; the paired eval leaves those settings unchanged.
