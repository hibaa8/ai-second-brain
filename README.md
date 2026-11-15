# Second Brain Ledger

An inspectable personal memory layer for Codex. Obsidian displays the Markdown vault; Codex uses three small skills to capture sources, retrieve evidence, and synthesize answers. A standard-library CLI builds a disposable full-text and typed-graph index. Codex's existing memory remains enabled and independent.

This is an original, small implementation inspired by [Karpathy's LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) and [Garry Tan's GBrain](https://github.com/garrytan/gbrain). It does not install or copy either project.

## What it does

```text
source file or chat → source catalog → source-backed wiki pages
                                          ↓
question → full-text seed → optional bounded graph walk → cited answer with gaps
```

- **Raw sources** remain original files. Registration stores a hash and path; it does not duplicate the file.
- **Wiki pages** are ordinary Markdown with a small frontmatter schema. Obsidian renders links and graph view.
- **Typed relationships** are source-backed rows in a page's `## Relationships` table. The CLI derives graph edges from the same text Obsidian shows.
- **Search** uses SQLite FTS5. Both the full-text index and graph projection are rebuilt from Markdown.
- **Synthesis** is a Codex workflow, not a second model service: it reads the retrieved pages and sources, cites concrete claims, and identifies gaps.

## Try the fictional demo

Python 3.10+ and SQLite FTS5 are required. No package installation is needed.

```bash
python3 brain.py --vault examples/demo-vault check
python3 brain.py --vault examples/demo-vault index
python3 brain.py --vault examples/demo-vault search "Orbit decision"
python3 brain.py --vault examples/demo-vault walk wiki/people/alex --hops 2
python3 brain.py --vault examples/demo-vault size
python3 -m unittest discover -s tests -v
```

The index is written beside the vault in `.brain-index/`, not inside the synced vault.

## Use with your own vault

1. Create a private folder and open it as a vault in Obsidian. Do not place private sources in this public repository.
2. Copy `SCHEMA.md` and adapt the `AGENTS.md` guidance to the private vault. Keep the initial `wiki/index.md` and `wiki/now.md` short.
3. Register a source: `python3 brain.py --vault /absolute/path/to/vault source /absolute/path/to/document --title "Document title"`.
4. Ask Codex to use the **brain-capture** skill to create or update source-backed pages, then run `check` and `index`.
5. Ask a question with the **brain-recall** skill. It searches first, traverses typed relationships only when useful, and synthesizes a cited answer.

See [SCHEMA.md](SCHEMA.md) for page and relationship conventions and [PLAN.md](PLAN.md) for scope and future work.

## Boundaries

The CLI does not import every past Codex or ChatGPT conversation automatically. Chat capture coverage must be tested for the environment before any daily ingestion is enabled. A registered external source remains wherever it was saved; the vault record is not its backup. Obsidian Sync and a separate backup can be configured independently.

For a public portfolio repository, use only synthetic examples. Keep the real vault separate and private. Generated `.brain-index/` files should not be committed.
