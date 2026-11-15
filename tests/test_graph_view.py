from pathlib import Path
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET

from graph_view import render


DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo-vault"


class GraphViewTests(unittest.TestCase):
    @staticmethod
    def edge_count(svg: str) -> int:
        root = ET.fromstring(svg)
        return sum("marker-end" in element.attrib for element in root.iter())

    def test_demo_graph_shows_active_typed_edges_only(self):
        with tempfile.TemporaryDirectory() as temp:
            vault = Path(temp) / "demo"
            shutil.copytree(DEMO, vault)
            original = render(vault, "Fictional demo")
            self.assertIn("4 pages  ·  3 active relationships", original)
            self.assertEqual(self.edge_count(original), 3)
            self.assertIn("Alex Example", original)

            page = vault / "wiki" / "people" / "alex.md"
            page.write_text(page.read_text().replace("| active |", "| withdrawn |"))
            updated = render(vault, "Fictional demo")
            self.assertIn("4 pages  ·  2 active relationships", updated)
            self.assertEqual(self.edge_count(updated), 2)


if __name__ == "__main__":
    unittest.main()
