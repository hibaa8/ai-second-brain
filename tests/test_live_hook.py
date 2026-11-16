from contextlib import redirect_stdout
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from integrations.codex import install, live_hook
from evals.run import evaluate


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
        self.assertEqual(telemetry["source_use"], [])
        self.assertIn("Observed Second Brain source use",
                      (self.vault / "evals" / "USAGE.md").read_text())
        self.assertIn("Completed turns recorded | 1", (self.vault / "evals" / "LIVE_REPORT.md").read_text())
        self.assertIn("Turns with source-use instrumentation | 1",
                      (self.vault / "evals" / "LIVE_REPORT.md").read_text())

    def test_completed_turn_becomes_searchable_in_next_conversation(self):
        first = {"session_id": "session-a", "turn_id": "turn-1",
                 "prompt": "I visited the museum at dawn."}
        with redirect_stdout(StringIO()):
            live_hook.on_prompt(self.vault, first)
            live_hook.on_prompt(self.vault, first)
            live_hook.on_stop(self.vault, {**first,
                "last_assistant_message": "You visited the museum at dawn."})
            live_hook.on_stop(self.vault, {**first,
                "last_assistant_message": "You visited the museum at dawn."})
        chats = list((self.vault / "raw" / "chats").rglob("*.json"))
        self.assertEqual(len(chats), 2)
        telemetry = json.loads((self.vault / "evals" / "live.jsonl").read_text().strip())
        self.assertTrue(telemetry["raw_capture"]["user"]["source_id"])
        self.assertTrue(telemetry["raw_capture"]["assistant"]["source_id"])
        recent = (self.vault / "ops" / "RECENT_CONVERSATIONS.md").read_text()
        self.assertIn("I visited the museum at dawn", recent)
        self.assertIn(telemetry["raw_capture"]["user"]["source_id"], recent)

        next_turn = {"session_id": "session-b", "turn_id": "turn-1",
                     "prompt": "Where did I say I visited at dawn?"}
        out = StringIO()
        with redirect_stdout(out):
            live_hook.on_prompt(self.vault, next_turn)
        context = json.loads(out.getvalue())["hookSpecificOutput"]["additionalContext"]
        self.assertIn(telemetry["raw_capture"]["user"]["source_id"], context)

    def test_stop_upgrades_inbox_from_older_prompt_hook(self):
        event = {"session_id": "older-session", "turn_id": "older-turn"}
        record = {**event, "captured_at": "2026-11-16T12:00:00+00:00",
                  "prompt": live_hook.clipped("I visited the museum at dawn."),
                  "retrieval": {"page_ids": [], "chat_sources": [],
                                "milliseconds": 1.0, "error": None},
                  "vault_stamp": list(live_hook.vault_stamp(self.vault))}
        live_hook.write_gzip(live_hook.event_file(self.vault, event), record)
        with redirect_stdout(StringIO()):
            live_hook.on_stop(self.vault, {**event,
                "last_assistant_message": "You visited the museum at dawn."})
        saved = live_hook.read_gzip(live_hook.event_file(self.vault, event))
        self.assertTrue(saved["raw_capture"]["user"]["source_id"])
        self.assertTrue(saved["raw_capture"]["assistant"]["source_id"])

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
        event = {"session_id": "secret-session", "turn_id": "secret-turn",
                 "prompt": "my api_key=abc123longsecretvalue and project notes"}
        with redirect_stdout(StringIO()):
            live_hook.on_prompt(self.vault, event)
        captured = list((self.vault / "raw" / "chats").rglob("*.json"))
        self.assertEqual(len(captured), 1)
        self.assertNotIn("abc123longsecretvalue", captured[0].read_text())

    def test_only_cited_and_registered_source_is_marked_used(self):
        self.assertEqual(live_hook.cited_usage(self.vault,
                         "See wiki/decisions/orbit-pilot without an original citation."), [])
        self.assertEqual(live_hook.cited_usage(self.vault,
                         "See wiki/decisions/orbit-pilot, source src-0000000000000000."), [])
        event = {"session_id": "session-usage", "turn_id": "turn-usage",
                 "prompt": "What was the Orbit pilot decision?"}
        with redirect_stdout(StringIO()):
            live_hook.on_prompt(self.vault, event)
            live_hook.on_stop(self.vault, {**event, "last_assistant_message":
                "The small pilot was chosen before wider release. "
                "See wiki/decisions/orbit-pilot, source src-80712d1c1265accb. "
                "This supports the staged rollout decision."})
        usage = json.loads((self.vault / "evals" / "usage.jsonl").read_text().strip())
        self.assertEqual(usage["entries"][0]["page_id"], "wiki/decisions/orbit-pilot")
        self.assertEqual(usage["entries"][0]["source_id"], "src-80712d1c1265accb")
        self.assertTrue(usage["entries"][0]["source_valid"])
        self.assertIn("staged rollout", usage["entries"][0]["why"])
        self.assertIn("[[wiki/decisions/orbit-pilot]]", (self.vault / "evals" / "USAGE.md").read_text())
        self.assertIn("Turns citing a registered original | 1",
                      (self.vault / "evals" / "LIVE_REPORT.md").read_text())

    def test_cited_raw_chat_is_marked_as_source_use(self):
        chat = self.vault / "raw" / "chats" / "sample" / "turn.json"
        chat.parent.mkdir(parents=True)
        chat.write_text(json.dumps({"thread_id": "sample", "turn_id": "turn",
                                    "role": "user", "text": "I built the Orbit pilot."}))
        source = live_hook.brain.add_source(self.vault, chat, "Original chat")
        usage = live_hook.cited_usage(self.vault,
                                      f"The user built the Orbit pilot. Source: {source['id']}.")
        self.assertEqual(usage[0]["page_id"], None)
        self.assertTrue(usage[0]["memory_ref"].endswith("raw/chats/sample/turn.json"))
        self.assertTrue(usage[0]["source_valid"])

    def test_prompt_terms_split_hyphenated_topics_and_ignore_generic_words(self):
        self.assertIn("course", live_hook.key_terms("course-planning idea"))
        self.assertIn("planning", live_hook.key_terms("course-planning idea"))
        self.assertEqual(live_hook.key_terms("If evidence is not available, tell me that"), [])

    def test_hook_retrieval_cases_check_offered_pages_and_abstention(self):
        report = evaluate(self.vault, {"cases": [
            {"kind": "hook", "name": "pilot recall", "query": "What was the Orbit pilot decision?",
             "expected_page": "wiki/decisions/orbit-pilot", "top_k": 2},
            {"kind": "hook", "name": "unknown pet", "query": "What is my dog's name?",
             "expected_none": True},
        ]})
        self.assertTrue(report["ok"])
        self.assertEqual(report["cases_passed"], 2)

    def test_prompt_hook_falls_back_to_registered_raw_chat(self):
        export = Path(self.temp.name) / "raw-fallback.jsonl"
        export.write_text(json.dumps({"thread_id": "chat-c", "turn_id": "turn-1",
                                      "role": "user", "text": "I visited the museum at dawn.",
                                      "created_at": "2026-09-12T08:00:00Z"}) + "\n")
        live_hook.brain.import_chat(self.vault, export)
        matches = live_hook.recalled_raw_chats(self.vault, "Did I visit the museum at dawn?")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["thread_id"], "chat-c")
        self.assertEqual(live_hook.recalled_raw_chats(self.vault, "What is my dog's name?"), [])
        event = {"session_id": "raw-fallback", "turn_id": "turn-1",
                 "prompt": "Did I visit the museum at dawn?"}
        out = StringIO()
        with redirect_stdout(out):
            live_hook.on_prompt(self.vault, event)
        context = json.loads(out.getvalue())["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Topical original user chat", context)
        self.assertIn(matches[0]["source"], context)
        self.assertEqual(live_hook.read_gzip(live_hook.event_file(self.vault, event))
                         ["retrieval"]["raw_chat_sources"], [matches[0]["source"]])

    def test_relative_day_recall_reads_dated_original_chats(self):
        folder = self.vault / "raw" / "chats" / "fictional"
        folder.mkdir(parents=True)
        for name, at, text in [
            ("yesterday", "2026-11-14T18:00:00Z", "We built the Orbit pilot."),
            ("today", "2026-11-15T18:00:00Z", "We reviewed the Orbit pilot."),
        ]:
            (folder / f"{name}.json").write_text(json.dumps({
                "thread_id": "fictional-thread", "turn_id": name, "role": "user",
                "created_at": at, "text": text,
            }))
        now = datetime(2026, 11, 15, 20, tzinfo=timezone.utc)
        day, hits = live_hook.recalled_chats(self.vault, "What did we build yesterday?", now)
        self.assertEqual(day, "2026-11-14")
        self.assertEqual(len(hits), 1)
        self.assertIn("Orbit pilot", hits[0]["excerpt"])
        self.assertTrue(hits[0]["source"].startswith("src-"))
        day, hits = live_hook.recalled_chats(self.vault, "What did we do earlier today?", now)
        self.assertEqual(day, "2026-11-15")
        self.assertEqual(len(hits), 1)
        self.assertIn("reviewed", hits[0]["excerpt"])
        self.assertEqual(live_hook.recalled_chats(self.vault, "What is the weather today?", now), (None, []))


if __name__ == "__main__":
    unittest.main()
