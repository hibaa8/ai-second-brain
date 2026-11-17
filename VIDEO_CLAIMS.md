# Video claims and how to reproduce the workflow

The video shows one private installation, not bundled demo data. Its November 17, 2026 snapshot reported **2,252 cataloged chat threads**, **42,314 registered raw sources**, **23 curated wiki pages**, **20 typed relationships**, and **1.47 GB of vault files**. The opening rounds the chat count to “2,000+”; it is a current count, not a capacity limit. The public repo contains only fictional examples, so a fresh clone starts with a small demo rather than those private totals.

The counts come from the private vault's source catalog, optional `raw/chat_threads.json` title catalog, wiki pages, relationship rows, and file sizes. A clone can measure its own state with:

```bash
python3 brain.py --vault /absolute/path/to/your-vault stats
```

The video also shows a **11.25 ms prompt-hook lookup** for one retrieval. That is the hook's lookup time in that run, not end-to-end answer latency or a guaranteed speed. The graph scene is a schematic visualization of the file-backed wiki and source-backed relationships, not a recording of every chat as a node. Raw chats are searchable originals; selected durable facts become wiki pages and typed links after review.

The live update mechanism in this repo is the [local Codex prompt and Stop hook integration](integrations/codex/README.md). It can capture supported new local turns and record retrieval offers, citations, source checks, and private regression results. It cannot automatically ingest ChatGPT cloud chats or attachments. Use the [ChatGPT export importer](GETTING_STARTED.md#2-add-originals) or normalized JSONL for history, and ingest documents separately.

The video demonstrates source-backed recall across years. It does not establish that the vault outperforms Codex's built-in memory. The [evaluation guide](evals/README.md) explains the paired test needed for that claim; this repo's automated cases measure retrieval and provenance behavior.
