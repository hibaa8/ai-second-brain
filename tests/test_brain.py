from pathlib import Path
import json
import shutil
import tempfile
import unittest

import brain


DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo-vault"


class BrainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.vault = Path(self.temp.name) / "vault"
        shutil.copytree(DEMO, self.vault)

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
