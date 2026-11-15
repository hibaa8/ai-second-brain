# Second Brain Ledger project guidance

- This is the public engine and synthetic demo. Do not add real conversations, names, personal documents, credentials, or private vault content here.
- Read `SCHEMA.md` before changing the vault format or CLI.
- Run `python3 -m unittest discover -s tests -v` after changing `brain.py`.
- Keep the public demo fictional. The private Obsidian vault is a separate directory.
- Retrieval order: search for seed pages, traverse typed edges only for relationship questions, then verify claims in sources before synthesis.
