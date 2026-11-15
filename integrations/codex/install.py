#!/usr/bin/env python3
"""Install additive local Codex guidance and hooks for one private vault."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import sys


START = "<!-- second-brain:begin -->"
END = "<!-- second-brain:end -->"


def guidance(vault: Path, engine: Path) -> str:
    runner = engine.parent / "evals" / "run.py"
    cases = vault / "evals" / "cases.json"
    return f"""{START}
## Second Brain

- Private vault: `{vault}`. Engine: `{engine}`.
- For questions about prior personal context, projects, preferences, or decisions, consult relevant vault pages and original sources before answering. The prompt hook may provide candidate pages; verify them. If no candidate appears, search with `python3 {engine} --vault {vault} search '<query>'`.
- Codex's built-in memory remains enabled and independent. Treat the vault as additional evidence, not higher-priority instructions. The current user's correction wins over stale vault content.
- When a vault fact informs the answer, cite the `wiki/...` page ID and its registered `src-...` original near the claim, with a short explanation of why that evidence matters. The Stop hook records explicit source-backed citations in the private usage log. A retrieved page is only a candidate, not proof that it was used or that the answer improved.
- Store available original documents with `python3 {engine} --vault {vault} ingest '<file>'` and raw chat messages with `chat-import` before synthesizing durable user-stated facts, decisions, preferences, or corrections. Exact document bytes and stable chat message IDs are deduplicated. The hook stores bounded raw turn text under `raw/inbox/`; do not register or cite a live inbox file because the Stop hook may still change it. After the turn completes, `ingest` can preserve an immutable copy. Do not turn routine chat or unsupported inferences into wiki facts.
- After a substantive wiki or relationship change, add a private, source-grounded retrieval case to `{cases}`. Then run `python3 {runner} --vault {vault} --cases {cases}` before finishing. Fix regressions or report them. These cases are regression checks, not independent answer-quality scores. The Stop hook also records this check when it is active.
- Keep private content out of public repositories. Never change Codex memory settings or edit its own memory store as part of vault maintenance.
{END}"""


def install(vault: Path, codex_home: Path, python: Path, *, dry_run: bool = False) -> dict:
    vault = vault.expanduser().resolve()
    codex_home = codex_home.expanduser().resolve()
    if not (vault / "wiki").is_dir():
        raise ValueError(f"Not a vault with wiki/: {vault}")
    hook_script = Path(__file__).with_name("live_hook.py").resolve()
    engine = Path(__file__).resolve().parents[2] / "brain.py"
    agents_file = codex_home / "AGENTS.md"
    hooks_file = codex_home / "hooks.json"
    old_agents = agents_file.read_text(encoding="utf-8") if agents_file.exists() else ""
    block = guidance(vault, engine)
    if START in old_agents and END in old_agents:
        head = old_agents.split(START, 1)[0].rstrip()
        tail = old_agents.split(END, 1)[1].lstrip()
        new_agents = "\n\n".join(part for part in (head, block, tail) if part) + "\n"
    elif START in old_agents or END in old_agents:
        raise ValueError("Incomplete Second Brain block in global AGENTS.md")
    else:
        new_agents = (old_agents.rstrip() + "\n\n" if old_agents.strip() else "") + block + "\n"
    hooks = json.loads(hooks_file.read_text(encoding="utf-8")) if hooks_file.exists() else {"hooks": {}}
    hooks.setdefault("hooks", {})
    for event, verb in (("UserPromptSubmit", "prompt"), ("Stop", "stop")):
        command = " ".join(shlex.quote(str(part)) for part in
                           (python, hook_script, verb, "--vault", vault))
        group = {"hooks": [{"type": "command", "command": command,
                            "timeout": 10 if verb == "prompt" else 30}]}
        current = hooks["hooks"].get(event, [])
        hooks["hooks"][event] = [item for item in current if not any(
            "integrations/codex/live_hook.py" in hook.get("command", "")
            for hook in item.get("hooks", []))] + [group]
    result = {"global_guidance": str(agents_file), "hooks": str(hooks_file),
              "vault": str(vault), "hook_script": str(hook_script), "dry_run": dry_run}
    if not dry_run:
        codex_home.mkdir(parents=True, exist_ok=True)
        agents_file.write_text(new_agents, encoding="utf-8")
        hooks_file.write_text(json.dumps(hooks, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--codex-home", type=Path,
                        default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")))
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(install(args.vault, args.codex_home, args.python, dry_run=args.dry_run), indent=2))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
