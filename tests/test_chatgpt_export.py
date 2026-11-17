from pathlib import Path
import json
import tempfile
import unittest
from zipfile import ZipFile

import brain
from tools.chatgpt_export import import_export


class ChatGptExportTests(unittest.TestCase):
    def test_imports_split_export_text_and_titles_idempotently(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vault = root / "vault"
            brain.init_vault(vault)
            archive = root / "export.zip"
            conversation = {
                "id": "conversation-1", "title": "Garden planning", "create_time": 1750000000,
                "mapping": {
                    "user-node": {"message": {"id": "user-1", "author": {"role": "user"},
                                              "content": {"content_type": "text", "parts": ["Plant basil in May."]},
                                              "create_time": 1750000001}},
                    "assistant-node": {"message": {"id": "assistant-1", "author": {"role": "assistant"},
                                                   "content": {"content_type": "text", "parts": ["Noted."]},
                                                   "create_time": 1750000002}},
                    "thought-node": {"message": {"id": "thought-1", "author": {"role": "assistant"},
                                                 "content": {"content_type": "thoughts", "parts": ["private thought"]}}},
                },
            }
            with ZipFile(archive, "w") as zip_file:
                zip_file.writestr("conversations-000.json", json.dumps([conversation]))
            first = import_export(vault, archive)
            second = import_export(vault, archive)
            self.assertEqual(first["added_messages"], 2)
            self.assertEqual(first["non_text_messages_skipped"], 1)
            self.assertEqual(second["added_messages"], 0)
            self.assertEqual(second["already_present"], 2)
            self.assertEqual(brain.stats_report(vault)["cataloged_chat_threads"], 1)
            self.assertEqual(brain.validate(vault), [])
            brain.build_index(vault)
            self.assertEqual(brain.search_chats(vault, "basil")[0]["title"], "Garden planning")


if __name__ == "__main__":
    unittest.main()
