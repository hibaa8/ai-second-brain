from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from integrations.codex import install, live_hook


ROOT = Path(__file__).resolve().parents[1]


class LiveHookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.vault = self.base / "vault"
        shutil.copytree(ROOT / "examples" / "demo-vault", self.vault)

    def test_prompt_recall_and_turn_capture(self):
        event = {"session_id": "session-1", "turn_id": "turn-1",
                 "prompt": "What was the Orbit pilot decision?"}
        out = StringIO()
        with redirect_stdout(out):
            live_hook.on_prompt(self.vault, event)
        context = json.loads(out.getvalue())["hookSpecificOutput"]["additionalContext"]
        self.assertIn("wiki/decisions/orbit-pilot", context)
        self.assertIn("verify any recalled claim", context)
        path = live_hook.event_file(self.vault, event)
        self.assertTrue(path.is_file())
        self.assertEqual(live_hook.read_gzip(path)["prompt"]["text"], event["prompt"])

        out = StringIO()
        with redirect_stdout(out):
            live_hook.on_stop(self.vault, {**event, "last_assistant_message": "A pilot was chosen."})
        self.assertEqual(json.loads(out.getvalue()), {})
        self.assertEqual(live_hook.read_gzip(path)["assistant"]["text"], "A pilot was chosen.")
        telemetry = json.loads((self.vault / "evals" / "live.jsonl").read_text().strip())
        self.assertIn("wiki/decisions/orbit-pilot", telemetry["retrieved_pages"])

    def test_vault_change_triggers_private_regression_eval(self):
        cases = self.vault / "evals" / "cases.json"
        cases.parent.mkdir()
        shutil.copy2(ROOT / "evals" / "demo.json", cases)
        event = {"session_id": "session-2", "turn_id": "turn-2",
                 "prompt": "What was the Orbit pilot decision?"}
        with redirect_stdout(StringIO()):
            live_hook.on_prompt(self.vault, event)
        page = self.vault / "wiki" / "now.md"
        page.write_text(page.read_text() + "\nA navigation update.\n")
        with redirect_stdout(StringIO()):
            live_hook.on_stop(self.vault, {**event, "last_assistant_message": "Pilot."})
        latest = json.loads((self.vault / "evals" / "latest.json").read_text())
        self.assertTrue(latest["ok"])
        self.assertEqual(latest["cases_passed"], 8)

    def test_installer_preserves_existing_global_guidance_and_hooks(self):
        codex_home = self.base / "codex-home"
        codex_home.mkdir()
        (codex_home / "AGENTS.md").write_text("# Existing guidance\n")
        (codex_home / "hooks.json").write_text(json.dumps({"hooks": {"Stop": [
            {"hooks": [{"type": "command", "command": "echo existing"}]}]}}))
        install.install(self.vault, codex_home, Path("/usr/bin/python3"))
        install.install(self.vault, codex_home, Path("/usr/bin/python3"))
        guidance = (codex_home / "AGENTS.md").read_text()
        hooks = json.loads((codex_home / "hooks.json").read_text())
        self.assertIn("# Existing guidance", guidance)
        self.assertEqual(guidance.count(install.START), 1)
        self.assertEqual(len(hooks["hooks"]["Stop"]), 2)
        self.assertEqual(len(hooks["hooks"]["UserPromptSubmit"]), 1)
        self.assertFalse((codex_home / "config.toml").exists())

    def test_common_secret_is_redacted_from_inbox_text(self):
        item = live_hook.clipped("my api_key=abc123longsecretvalue and project notes")
        self.assertTrue(item["redacted"])
        self.assertNotIn("abc123longsecretvalue", item["text"])
        self.assertIn("project notes", item["text"])


if __name__ == "__main__":
    unittest.main()
