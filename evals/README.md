# Evaluation

The index also covers registered original chat text and optional exported conversation titles. When no wiki page or dated recall matches, the prompt hook can offer up to two topical user-chat sources. A private hook case can use `expected_raw_source` or `expected_raw_thread` to protect this fallback against regressions.

Run the read-only smoke eval with `python3 evals/run.py`. It checks whether full-text search returns expected pages, whether typed graph traversal reaches expected pages within a hop limit, and whether cited source text is available with the registered hash. It builds a temporary index and leaves the selected vault and its normal index untouched. The demo is tiny and fictional; its score is a software smoke check, not a measure of personal-memory effectiveness.

Private case sets can also include `kind: "hook"` with a natural-language `query` and an `expected_page`, `expected_chat_day` plus `min_chat_count`, or `expected_none`. This exercises the prompt hook's actual candidate selection, including paraphrases and no-result controls. A fixed `now` timestamp makes relative-day cases reproducible. These cases catch retrieval regressions but do not generate or grade an agent answer.

For each supported local turn, `evals/live.jsonl` in the private vault records offered pages or raw chats, registered prompt and final-answer sources, the lightweight capture check, and any registered original cited in the final answer. `evals/usage.jsonl` and `evals/USAGE.md` retain the original source, a cited wiki page when available, its hash-integrity result, and the surrounding claim. This also covers dated raw-chat recall without a wiki page. `evals/LIVE_REPORT.md` is regenerated after each completed turn and summarizes capture, retrieval, citation, and regression counts. This is a live attribution trace: retrieval is not counted as use, and use is not scored as correct merely because a citation appears. Review the original source when scoring the claim. An answer that uses the vault without citing it will be absent from this log, so citation coverage also needs auditing.

For example, a **fictional** answer that says the team chose a small pilot and cites `wiki/decisions/orbit-pilot` beside `src-80712d1c1265accb` creates a usage row with that claim and a hash check of the original. If the prompt hook merely offered the page, no usage row is created.

To run a private case set, keep its JSON outside this public repository and pass `--vault /path/to/private-vault --cases /path/to/private-cases.json`.

## Paired answer eval

Use fresh chats with the same model and the same factual questions, while keeping Codex's existing memory settings unchanged in both conditions:

1. **Baseline:** ask the question without consulting Second Brain. Codex may use its existing memory and chat history as usual.
2. **Vault-assisted:** ask the same question and request the `brain-recall` workflow against the private vault.

Score the answers against the original source, not the wiki page. Record factual correctness, verified citations, unsupported claims, appropriate abstention, handling of corrections, latency, and retrieval effort. Randomize condition order and use held-out questions spanning direct facts, multi-hop relationships, changes over time, and facts absent from the vault. Do not use answer text from one condition as context for the other. A useful result is the **incremental benefit over Codex's existing memory**, including cases where the vault makes an answer worse.

The current CLI smoke eval does not execute Codex or assess generated answers. Local CLI and desktop turns have produced hook records in this setup; check `evals/live.jsonl` in the private vault for each completed turn. Hook telemetry and retrieval regressions still do not supply a personal-memory effectiveness score.

The public `evals/paired.py` runner collects fresh, ephemeral Codex CLI answers in two conditions. It disables only the Second Brain hooks for the no-vault condition, instructs that condition not to use files or tools, and keeps the same Codex home, model, reasoning effort, and existing memory settings. It records answer files, JSONL traces, tool-call counts, and wall time in a **private** output directory. The answer and source-grounding judgments are manual; `evals/score_paired.py` then summarizes those grades and verifies cited source hashes. Keep question sets, grades, and answers outside this repo.

```bash
python3 evals/paired.py --cases /private/path/cases.json --output /private/path/paired-results --model gpt-5.6-sol
python3 evals/score_paired.py --vault /private/path/vault --cases /private/path/cases.json --results /private/path/paired-results --grades /private/path/grades.json
```

On November 17, 2026, a private six-question pilot used five source-grounded questions not in the earlier ten fresh-chat probes, plus one unknown-fact control. Vault-assisted answers were manually judged correct and source-supported on **5/5** answerable cases, with valid hashes for the cited originals. The no-vault condition abstained on all five answerable cases; both conditions abstained correctly on the unknown control. All no-vault traces had zero tool calls. Median end-to-end CLI wall time was **41.23 s** with the vault and **11.42 s** without it, including model startup and tool use. This is a small, hand-selected pilot with one run per condition. It does not establish population-level performance, isolate every source of improvement, or prove that ephemeral CLI sessions expose the same built-in memory as Codex desktop.

OpenAI [documents local Codex memories as a separate store and set of controls](https://learn.chatgpt.com/docs/customization/memories). This project does not call those controls or edit that store. Codex may still generate its own memories from eligible chats according to the user's existing settings; the paired eval leaves those settings unchanged.
