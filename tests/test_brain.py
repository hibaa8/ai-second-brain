from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
