# Local Codex live connection

This optional connection gives **new local Codex chats** a route to the private vault without changing Codex's own memory settings or files. The installer adds a small global `AGENTS.md` block and two additive hooks. It preserves unrelated global guidance and hooks.

```bash
python3 integrations/codex/install.py --vault /absolute/path/to/private-vault --dry-run
python3 integrations/codex/install.py --vault /absolute/path/to/private-vault
```

Codex requires you to review and trust newly installed hooks in **Settings → Hooks** or `/hooks` before they run. Start a new local chat after installation; guidance is discovered at session start. The installer is idempotent. It does not edit `config.toml`, `/memories`, or Codex's memory store. Global guidance can still direct source lookup while hook trust is pending.

To verify activation, submit a prompt in a new **local** Codex chat and check for a new `raw/inbox/<session-hash>/<turn-hash>.json.gz` file. After the turn ends, check `evals/live.jsonl`. If neither appears, do not count the turn as automatically captured or evaluated. A changed wiki or source catalog should also produce `evals/latest.json`.

## What runs during a local chat

| Event | Action |
| --- | --- |
| User submits a prompt | Store up to 64 KB of its text in a compressed private turn record; search the wiki for relevant pages; inject up to two candidate excerpts into that turn's context. For day-based recollection questions such as “what did we do yesterday?”, resolve the date in `SECOND_BRAIN_TIMEZONE` (default `America/New_York`) and add bounded excerpts from dated raw chat turns, including assistant outcomes where available. The agent must verify claims against the cited source. |
| Agent finishes a turn | Add up to 64 KB of its final message to the same private record; append retrieval and size metadata to `evals/live.jsonl`. If the answer cites a registered original, record the source, any cited wiki page, and surrounding claim in `evals/usage.jsonl` and the Obsidian-readable `evals/USAGE.md`. Regenerate `evals/LIVE_REPORT.md` with counts and recent turns. If wiki pages or the source catalog changed during the turn, run the private regression cases and write `evals/latest.json`. |
| Agent captures a durable claim | After the Stop hook completes the inbox record, Codex can use `brain.py ingest` to store an immutable copy, update the wiki with citations, add a source-grounded private regression case, and run the eval. Do not register the live inbox path directly because the Stop hook still changes it. This is agent work; the hooks themselves do not invent wiki facts. |

The inbox is `raw/inbox/<session-hash>/<turn-hash>.json.gz`. Large prompt or answer text is truncated in the inbox with its original byte count and SHA-256 recorded. Common key and password patterns are redacted; this is a limited safeguard, so review private records before sharing or backing them up. Upload attachments, tool output, and whole historical transcripts are **not** captured by these events. For complete text history, convert an available export to the documented JSONL format and run `brain.py chat-import`; store attachment files separately with `brain.py ingest`. Those commands deduplicate repeated messages and identical file bytes. The hook keeps the vault local but injects bounded excerpts into the active Codex model context; do not treat that context as local-only. The compressed inbox still grows over time; review `brain.py size` and move older originals to a separately backed-up archive when needed.

The live log is operational telemetry: whether retrieval happened, which page IDs were offered, errors, latency, whether a source-backed page was cited in the final answer, and whether a changed vault passed the private regression suite. The usage log gives an auditable answer claim and checks that the cited original still matches its registered hash. It can undercount memory use if the agent omits citations; citations do not prove a claim is correct. Use [the paired answer-eval protocol](../../evals/README.md) to compare with Codex's existing memory.

## Coverage and limitations

- Global guidance and command hooks apply to supported **local Codex** sessions. They do not establish coverage for ChatGPT Work, Codex cloud orchestration, other devices, or every possible client. Hook trust or workspace policy may prevent execution.
- A candidate page is injected only when the prompt matches it conservatively. Unrelated chats still get an inbox record and a vault pointer; the wiki is not forced into every answer.
- `SessionEnd` can be delayed, so this connection uses prompt and turn events. Source-backed wiki synthesis is best effort during the turn; a regression run follows a detected wiki update.
- The private vault remains separate from the public repo. Never commit its inbox, cases, or live telemetry to GitHub.

See the [official global guidance](https://learn.chatgpt.com/docs/agent-configuration/agents-md) and [hook lifecycle](https://learn.chatgpt.com/docs/hooks) documentation for the supported Codex behavior.
