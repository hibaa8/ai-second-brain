from pathlib import Path
import json
import shutil
import tempfile
import unittest

import brain
from integrations.codex.live_hook import capture_chat_message


DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo-vault"


class BrainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.vault = Path(self.temp.name) / "vault"
        shutil.copytree(DEMO, self.vault)

    def test_init_creates_new_vault_and_preserves_existing_notes(self):
        fresh = Path(self.temp.name) / "fresh-vault"
        first = brain.init_vault(fresh)
        self.assertEqual(len(first["created"]), 3)
        self.assertEqual(brain.validate(fresh), [])
        self.assertEqual(brain.build_index(fresh)["pages"], 0)
        note = fresh / "wiki" / "now.md"
        note.write_text("# Now\n\nMy own note.\n", encoding="utf-8")
        second = brain.init_vault(fresh)
        self.assertEqual(second["created"], [])
        self.assertIn("My own note", note.read_text(encoding="utf-8"))

    def test_stats_reports_cataloged_vault_content(self):
        (self.vault / "raw" / "chat_threads.json").write_text(
            json.dumps({"chat-a": {"title": "A chat"}}), encoding="utf-8")
        report = brain.stats_report(self.vault)
        self.assertEqual(report["cataloged_chat_threads"], 1)
        self.assertEqual(report["wiki_pages"], 4)
        self.assertEqual(report["typed_relationships"], 3)
        self.assertEqual(report["registered_raw_sources"], 1)

    def test_source_registration_deduplicates_identical_content(self):
        original = self.vault / "raw" / "orbit-brief.md"
        duplicate = self.vault / "raw" / "same-brief.md"
        shutil.copy2(original, duplicate)
        before = len(brain.source_records(self.vault))
        result = brain.add_source(self.vault, duplicate, None)
        self.assertTrue(result["already_registered"])
        self.assertEqual(len(brain.source_records(self.vault)), before)

    def test_ingest_stores_one_copy_and_upgrades_external_reference(self):
        external = Path(self.temp.name) / "report.pdf"
        external.write_bytes(b"%PDF-test document")
        reference = brain.add_source(self.vault, external, "Report")
        imported = brain.ingest_file(self.vault, external)
        self.assertEqual(imported["id"], reference["id"])
        self.assertEqual(imported["original_location"], str(external.resolve()))
        stored = self.vault / imported["location"]
        self.assertEqual(stored.read_bytes(), external.read_bytes())
        duplicate = Path(self.temp.name) / "renamed.pdf"
        duplicate.write_bytes(external.read_bytes())
        again = brain.ingest_file(self.vault, duplicate)
        self.assertTrue(again["already_stored"])
        self.assertEqual(len(list((self.vault / "raw" / "objects").rglob("*.pdf"))), 1)
        self.assertEqual(brain.validate(self.vault), [])
        stored.unlink()
        self.assertTrue(any("stored source" in error for error in brain.validate(self.vault)))

    def test_chat_import_is_idempotent_and_rejects_changed_turn(self):
        export = Path(self.temp.name) / "chat.jsonl"
        first = {"thread_id": "chat-a", "turn_id": "turn-1", "role": "user",
                 "text": "Remember the original document.", "created_at": "2026-11-15"}
        second = {"thread_id": "chat-a", "turn_id": "turn-1", "role": "assistant",
                  "text": "I will catalog it.", "created_at": "2026-11-15"}
        export.write_text("\n".join(json.dumps(item) for item in (first, second)) + "\n")
        self.assertEqual(brain.import_chat(self.vault, export)["added"], 2)
        self.assertEqual(brain.import_chat(self.vault, export)["already_present"], 2)
        self.assertEqual(len(list((self.vault / "raw" / "chats").rglob("*.json"))), 2)
        self.assertEqual(brain.validate(self.vault), [])
        first["text"] = "A conflicting edit."
        export.write_text(json.dumps(first) + "\n")
        with self.assertRaisesRegex(ValueError, "changed since import"):
            brain.import_chat(self.vault, export)

    def test_chat_import_preserves_unicode_line_separator_inside_json_string(self):
        export = Path(self.temp.name) / "unicode-chat.jsonl"
        message = {"thread_id": "chat-b", "turn_id": "turn-1", "role": "user",
                   "text": "First paragraph\u2028second paragraph"}
        export.write_text(json.dumps(message, ensure_ascii=False) + "\n", encoding="utf-8")
        result = brain.import_chat(self.vault, export)
        self.assertEqual(result["added"], 1)
        stored = next((self.vault / "raw" / "chats").rglob("*.json"))
        self.assertEqual(json.loads(stored.read_text())["text"], message["text"])

    def test_hook_capture_keeps_distinct_messages_under_one_turn(self):
        record = {"session_id": "session-a", "turn_id": "turn-a",
                  "captured_at": "2026-11-17T00:00:00Z"}
        def bounded(text):
            return {"text": text, "bytes": len(text.encode()), "truncated": False,
                    "redacted": False}
        first = capture_chat_message(self.vault, record, "user", bounded("First prompt."))
        second = capture_chat_message(self.vault, record, "user", bounded("Follow-up prompt."))
        retry = capture_chat_message(self.vault, record, "user", bounded("Follow-up prompt."))
        self.assertNotEqual(first["source_id"], second["source_id"])
        self.assertFalse(retry["added"])
        self.assertEqual(second["source_id"], retry["source_id"])
        self.assertEqual(len(list((self.vault / "raw" / "chats").rglob("*.json"))), 2)

    def test_registered_raw_chats_are_searchable_after_indexing(self):
        export = Path(self.temp.name) / "chat-search.jsonl"
        export.write_text(json.dumps({"thread_id": "chat-c", "turn_id": "turn-1",
                                      "role": "user", "text": "I visited the museum at dawn.",
                                      "created_at": "2026-09-12T08:00:00Z"}) + "\n")
        brain.import_chat(self.vault, export)
        brain.build_index(self.vault)
        hits = brain.search_chats(self.vault, "museum dawn")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["thread_id"], "chat-c")
        self.assertEqual(hits[0]["role"], "user")

    def test_incremental_chat_and_wiki_refresh(self):
        brain.build_index(self.vault)
        export = Path(self.temp.name) / "incremental-chat.jsonl"
        export.write_text(json.dumps({"thread_id": "chat-d", "turn_id": "turn-1",
                                      "role": "user", "text": "I visited the museum at dawn."}) + "\n")
        (self.vault / "raw" / "chat_threads.json").write_text(
            json.dumps({"chat-d": {"title": "Museum at sunrise"}}))
        brain.import_chat(self.vault, export)
        refreshed = brain.refresh_chat_index(self.vault)
        self.assertEqual(refreshed["added"], 1)
        self.assertEqual(brain.refresh_chat_index(self.vault)["added"], 0)
        self.assertEqual(len(brain.search_chats(self.vault, "museum dawn")), 1)
        self.assertEqual(brain.search_chats(self.vault, "sunrise")[0]["title"], "Museum at sunrise")

        page = self.vault / "wiki" / "projects" / "orbit.md"
        page.write_text(page.read_text() + "\nThe museum trip informed the pilot.\n")
        brain.refresh_wiki_index(self.vault)
        self.assertIn("wiki/projects/orbit", [hit["id"] for hit in brain.search(self.vault, "museum")])
        self.assertEqual(len(brain.search_chats(self.vault, "museum dawn")), 1)

    def test_ingest_copies_mutable_inbox_before_cataloging(self):
        inbox = self.vault / "raw" / "inbox" / "turn.json.gz"
        inbox.parent.mkdir(parents=True)
        inbox.write_bytes(b"prompt")
        with self.assertRaisesRegex(ValueError, "mutable hook inbox"):
            brain.add_source(self.vault, inbox, None)
        stored = brain.ingest_file(self.vault, inbox)
        self.assertIn("raw/objects/", stored["location"])
        inbox.write_bytes(b"prompt and final answer")
        self.assertEqual((self.vault / stored["location"]).read_bytes(), b"prompt")
        self.assertEqual(brain.validate(self.vault), [])

    def test_search_and_bounded_relationship_walk(self):
        brain.build_index(self.vault)
        hits = brain.search(self.vault, "pilot")
        self.assertIn("wiki/decisions/orbit-pilot", [hit["id"] for hit in hits])
        one_hop = brain.walk(self.vault, "wiki/people/alex", hops=1)
        self.assertEqual([item["page"] for item in one_hop], ["wiki/projects/orbit"])
        two_hops = brain.walk(self.vault, "wiki/people/alex", hops=2)
        self.assertIn("wiki/decisions/orbit-pilot", [item["page"] for item in two_hops])
        self.assertTrue(all(len(item["path"]) <= 2 for item in two_hops))

    def test_withdrawn_relationship_is_not_traversed(self):
        person = self.vault / "wiki" / "people" / "alex.md"
        person.write_text(person.read_text().replace("| active |", "| withdrawn |"))
        self.assertEqual(brain.validate(self.vault), [])
        brain.build_index(self.vault)
        self.assertEqual(brain.walk(self.vault, "wiki/people/alex"), [])

    def test_broken_source_and_link_are_reported(self):
        person = self.vault / "wiki" / "people" / "alex.md"
        person.write_text(person.read_text().replace("src-80712d1c1265accb", "src-missing")
                          .replace("[[wiki/projects/orbit]]", "[[wiki/projects/missing]]"))
        errors = brain.validate(self.vault)
        self.assertTrue(any("unknown source" in error for error in errors))
        self.assertTrue(any("broken link" in error for error in errors))
        with self.assertRaises(ValueError):
            brain.build_index(self.vault)

    def test_changed_registered_source_is_reported(self):
        source = self.vault / "raw" / "orbit-brief.md"
        source.write_text(source.read_text() + "\nAn unregistered edit.\n")
        self.assertTrue(any("changed since registration" in error
                            for error in brain.validate(self.vault)))

    def test_cited_source_must_be_declared(self):
        person = self.vault / "wiki" / "people" / "alex.md"
        person.write_text(person.read_text() + "\nSource: `src-80712d1c1265accb`.\n")
        self.assertEqual(brain.validate(self.vault), [])
        person.write_text(person.read_text().replace("sources: src-80712d1c1265accb", "sources: src-missing"))
        self.assertTrue(any("cited source" in error for error in brain.validate(self.vault)))


if __name__ == "__main__":
    unittest.main()
