# Reproduce the workflow with your own data

This guide builds a private Obsidian vault beside a clone of this public engine. The included demo data is fictional. Use Python 3.10+ with SQLite FTS5, Codex for the live connection, and Obsidian if you want the visual file and graph interface. No cloud database or embedding service is required.

## 1. Clone and create a private vault

```bash
git clone https://github.com/hibaa8/ai-second-brain.git
cd ai-second-brain
export BRAIN_REPO="$PWD"
export BRAIN_VAULT="$HOME/Documents/my-second-brain-vault"
python3 brain.py --vault "$BRAIN_VAULT" init
python3 brain.py --vault "$BRAIN_VAULT" check
python3 brain.py --vault "$BRAIN_VAULT" index
```

`init` creates `raw/`, `wiki/`, `evals/`, and `ops/` plus navigation notes. It preserves existing files if run again. Keep the vault outside this Git checkout and back it up separately. Open `BRAIN_VAULT` as a vault in Obsidian; its native Graph view will display links between Markdown notes as you add them. To focus the graph on curated pages, use Obsidian's graph filter for `path:wiki/`.

## 2. Add originals

For a document you have permission to store:

```bash
python3 "$BRAIN_REPO/brain.py" --vault "$BRAIN_VAULT" ingest /absolute/path/to/document.pdf
```

The command prints a `src-...` ID. It copies exact bytes into `raw/objects/`; importing the same bytes again reuses the copy. The default per-file cap is 50 MB. Use `source` only when the original is kept in a separately backed-up private archive; a reference is not a backup.

For a ChatGPT data export ZIP, including exports split into `conversations-000.json` parts:

```bash
python3 "$BRAIN_REPO/tools/chatgpt_export.py" /absolute/path/to/export.zip --vault "$BRAIN_VAULT"
python3 "$BRAIN_REPO/brain.py" --vault "$BRAIN_VAULT" index
```

The importer stores user and assistant text turns as immutable `raw/chats/` sources, retains conversation titles for search, and skips reasoning, tool, and non-text content. Repeating an import deduplicates messages by stable export IDs; conflicting content for the same ID stops with an error for review. It does not import attachment bytes. Use `ingest` for selected attached files, and keep large media in a separately backed-up private archive if needed. The ZIP itself is not copied into the vault; retain or back it up separately if you need the original export package.

For another chat source, normalize messages to JSONL with `thread_id`, `turn_id`, `role`, and `text`, then run `brain.py chat-import`. See [the schema](SCHEMA.md).

## 3. Build a small, sourced wiki

Ask Codex to read relevant originals, select durable facts or decisions, and write one Markdown page per topic under `wiki/`. Run Codex with this repo as its workspace to use the included `brain-capture`, `brain-recall`, and `brain-review` skills. You can also follow [the schema](SCHEMA.md) directly. Each page declares the registered `src-...` originals behind its claims. A relationship row links two existing wiki pages and cites a source; Obsidian will show the link in its graph.

```bash
python3 "$BRAIN_REPO/brain.py" --vault "$BRAIN_VAULT" check
python3 "$BRAIN_REPO/brain.py" --vault "$BRAIN_VAULT" index
python3 "$BRAIN_REPO/brain.py" --vault "$BRAIN_VAULT" search "your topic"
python3 "$BRAIN_REPO/graph_view.py" --vault "$BRAIN_VAULT" --output "$BRAIN_VAULT/graph-current.svg"
```

`graph-current.svg` is a static picture of the typed graph. Obsidian's Graph view is live. A raw chat becomes searchable after import, but only a deliberate, source-backed wiki edit creates a durable topic node or typed relationship.

## 4. Connect new local Codex chats

```bash
python3 "$BRAIN_REPO/integrations/codex/install.py" --vault "$BRAIN_VAULT" --dry-run
python3 "$BRAIN_REPO/integrations/codex/install.py" --vault "$BRAIN_VAULT"
```

Review and trust the two new hooks in Codex **Settings → Hooks** or `/hooks`, then start a new local chat. The installer adds global guidance plus prompt and Stop hooks, preserving unrelated guidance and hooks. It does not change Codex's own memory settings or store. Supported local prompts and final answers are captured as bounded, deduplicated raw sources; the prompt hook also offers relevant evidence, and the Stop hook records citation and source-integrity signals. The hooks do not capture uploads, tool output, or every client. Follow [the verification steps](integrations/codex/README.md) before relying on automatic capture.

## 5. Evaluate and monitor

```bash
python3 "$BRAIN_REPO/brain.py" --vault "$BRAIN_VAULT" stats
python3 "$BRAIN_REPO/evals/run.py"
python3 -m unittest discover -s "$BRAIN_REPO/tests" -v
```

The included evaluation uses fictional demo cases. For your own wiki, keep private retrieval cases in `$BRAIN_VAULT/evals/cases.json` and run `evals/run.py --vault "$BRAIN_VAULT" --cases "$BRAIN_VAULT/evals/cases.json"`. The live hook writes telemetry under your private `evals/`; it records what was offered and explicitly cited, not whether an answer was correct or better than Codex alone. For an effectiveness claim, use [the paired answer evaluation protocol](evals/README.md).

The video’s aggregate snapshot and measurement definitions are in [VIDEO_CLAIMS.md](VIDEO_CLAIMS.md). Your counts will depend on your own data.
